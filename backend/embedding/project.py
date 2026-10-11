"""
UMAP projection + k-means clustering + cluster labelling.

Steps:
1. Load the analysis's vectors from LanceDB.
2. Run UMAP (2D).
3. Try k-means for k in {5, 7, 10}; pick best silhouette score.
4. For each chunk compute Euclidean distance to its cluster centroid.
5. Call Claude once per cluster (top-10 central chunks) to get a 2-3 word label.
6. Write (chunk_id, x, y, cluster_id, cluster_label, distance_from_centroid)
   to the SQLite projections table.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from umap import UMAP

from backend.config import settings
from backend.db import connect
from backend.embedding.store import read_all_embeddings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _best_k(vectors: np.ndarray) -> int:
    if settings.kmeans_k != "auto":
        return int(settings.kmeans_k)

    candidates = [k for k in (5, 7, 10) if k < len(vectors)]
    if not candidates:
        return max(2, len(vectors) // 10)

    best_k, best_score = candidates[0], -1.0
    for k in candidates:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(vectors)
        score = silhouette_score(vectors, labels)
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def _euclidean(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def _label_cluster(cluster_id: int, top_chunks: list[str]) -> str:
    """Ask Claude for a 2-3 word label for this cluster."""
    from backend.claude_client import complete

    excerpts = "\n\n".join(f"- {t[:300]}" for t in top_chunks)
    prompt = (
        f"Below are excerpts from articles in a semantic cluster (cluster {cluster_id}).\n\n"
        f"{excerpts}\n\n"
        "Give a 2-3 word descriptive label that captures the main theme of this cluster. "
        "Respond with ONLY the label, nothing else."
    )
    return complete(prompt, max_tokens=2048, effort="low")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_projection(analysis_id: str) -> None:
    """
    Full projection pipeline. Writes rows to the SQLite projections table.
    """
    # 1. Load embeddings
    rows = read_all_embeddings(analysis_id)
    if not rows:
        raise RuntimeError("No embeddings found in LanceDB — run embedding step first.")

    chunk_ids = [r["chunk_id"] for r in rows]
    vectors = np.array([r["vector"] for r in rows], dtype=np.float32)
    child_texts = {r["chunk_id"]: r["child_text"] for r in rows}

    # 2. UMAP
    n_neighbors = min(settings.umap_n_neighbors, len(vectors) - 1)
    reducer = UMAP(n_components=2, n_neighbors=n_neighbors, min_dist=0.1, random_state=42)
    coords_2d = reducer.fit_transform(vectors)   # shape (N, 2)

    # 3. K-means
    k = _best_k(vectors)
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    cluster_labels_arr = km.fit_predict(vectors)   # int labels, shape (N,)
    centroids = km.cluster_centers_               # shape (k, dim)

    # 4. Distance from centroid
    distances = np.array(
        [_euclidean(vectors[i], centroids[cluster_labels_arr[i]]) for i in range(len(vectors))]
    )

    # 5. Generate cluster text labels via Claude
    cluster_text_labels: dict[int, str] = {}
    for cid in range(k):
        mask = cluster_labels_arr == cid
        idxs = np.where(mask)[0]
        # Sort by distance (ascending = most central)
        sorted_idxs = idxs[np.argsort(distances[idxs])][:10]
        top_texts = [child_texts[chunk_ids[i]] for i in sorted_idxs]
        try:
            cluster_text_labels[cid] = _label_cluster(cid, top_texts)
        except Exception:
            cluster_text_labels[cid] = f"cluster {cid}"

    # 6. Write projections to SQLite
    conn = connect()
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO projections "
            "(chunk_id, analysis_id, x, y, cluster_id, cluster_label, distance_from_centroid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    chunk_ids[i],
                    analysis_id,
                    float(coords_2d[i, 0]),
                    float(coords_2d[i, 1]),
                    int(cluster_labels_arr[i]),
                    cluster_text_labels[int(cluster_labels_arr[i])],
                    float(distances[i]),
                )
                for i in range(len(chunk_ids))
            ],
        )
        conn.commit()
    finally:
        conn.close()
