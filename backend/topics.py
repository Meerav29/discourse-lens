"""
Topic modelling for one analysis: BERTopic's recipe without its PyTorch dependency.

Articles (not chunks) are the unit: chunks of one article are so similar that
chunk-level clustering groups text by source instead of by argument.

  article vectors (mean of chunk embeddings, L2-normalised)
    → UMAP to 5D → HDBSCAN (leaf selection: the finest stable clusters)
    → merge topics that members can't tell apart (leaf selection over-splits)
    → noise articles join their nearest topic only if they'd pass as a member
    → topics merged down to MAX_TOPICS (the number of distinct map colours)
    → c-TF-IDF over each topic's text for its key terms

All functions here are pure (numpy in, numpy/py out) so they're unit-tested
without LanceDB, SQLite or the network.
"""

from __future__ import annotations

import re

import numpy as np
from sklearn.cluster import HDBSCAN, AgglomerativeClustering
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

NOISE = -1
MAX_TOPICS = 8
RANDOM_STATE = 42


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def article_vectors(
    chunk_vectors: np.ndarray, chunk_article_ids: list[str]
) -> tuple[list[str], np.ndarray]:
    """Mean of each article's chunk vectors, normalised. Returns (ids, vectors)."""
    order: dict[str, list[int]] = {}
    for i, aid in enumerate(chunk_article_ids):
        order.setdefault(aid, []).append(i)
    ids = list(order)
    X = np.stack([chunk_vectors[idx].mean(axis=0) for idx in order.values()])
    return ids, normalize(X.astype(np.float32))


def reduce(
    X: np.ndarray, dims: int, min_dist: float, neighbors: int = 10, spread: float = 1.0
) -> np.ndarray:
    """UMAP with cosine distance; neighbourhood size adapts to small corpora."""
    from umap import UMAP  # slow import (numba); keep it out of module import

    n = len(X)
    if n <= dims + 1:
        # Too few points for UMAP's spectral init; pad with zeros (degenerate but valid).
        return np.pad(X[:, :dims], ((0, 0), (0, max(0, dims - X.shape[1]))))
    reducer = UMAP(
        n_components=dims,
        n_neighbors=max(2, min(neighbors, n - 1)),
        min_dist=min_dist,
        spread=spread,
        metric="cosine",
        random_state=RANDOM_STATE,
        n_jobs=1,  # implied by random_state; explicit to avoid a warning
    )
    return reducer.fit_transform(X)


def find_topics(Z: np.ndarray) -> np.ndarray:
    """
    HDBSCAN with leaf selection on the reduced space; label -1 is noise.
    Minimum cluster size grows slowly with corpus size (3 for ~50 articles,
    8 for ~120). If density finds fewer than two topics (tiny or very uniform
    corpora), fall back to Ward clustering into three.
    """
    n = len(Z)
    if n < 6:
        return np.zeros(n, dtype=int)
    min_size = max(3, round(n / 15))
    labels = HDBSCAN(min_cluster_size=min_size, cluster_selection_method="leaf").fit_predict(Z)
    if len(set(labels) - {NOISE}) < 2:
        labels = AgglomerativeClustering(n_clusters=min(3, n), linkage="ward").fit_predict(Z)
    return relabel(labels)


def relabel(labels: np.ndarray) -> np.ndarray:
    """Renumber topics 0..k-1 by descending size (noise stays -1)."""
    ids = [t for t in set(labels.tolist()) if t != NOISE]
    ids.sort(key=lambda t: (-int(np.sum(labels == t)), t))
    mapping = {old: new for new, old in enumerate(ids)}
    return np.array([mapping.get(t, NOISE) for t in labels.tolist()], dtype=int)


def centroids(X: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    return {
        int(t): normalize(X[labels == t].mean(axis=0, keepdims=True))[0]
        for t in sorted(set(labels.tolist()) - {NOISE})
    }


def merge_indistinct(X: np.ndarray, labels: np.ndarray, tolerance: float = 0.01) -> np.ndarray:
    """
    Merge pairs of topics whose centroids are as similar to each other as the
    topics' own members are to their centroids (median, less a small tolerance
    for noise in that estimate): such a split carries no information. Leaf
    selection otherwise cuts evenly spread groups into arbitrary sub-leaves.
    """
    labels = labels.copy()
    while True:
        cents = centroids(X, labels)
        ids = list(cents)
        if len(ids) < 2:
            return relabel(labels)
        cohesion = {t: float(np.median(X[labels == t] @ cents[t])) for t in ids}
        best, pair = -np.inf, None
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                margin = float(cents[a] @ cents[b]) - min(cohesion[a], cohesion[b])
                if margin > best:
                    best, pair = margin, (a, b)
        if best < -tolerance:
            return relabel(labels)
        labels[labels == pair[1]] = pair[0]


def assign_noise(X: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """
    A noise article joins its most similar topic if it's at least as similar
    to that topic's centroid as the topic's least-typical member. Otherwise it
    stays unclustered.
    """
    labels = labels.copy()
    cents = centroids(X, labels)
    if not cents:
        return labels
    floor = {t: float((X[labels == t] @ c).min()) for t, c in cents.items()}
    topic_ids = list(cents)
    C = np.stack([cents[t] for t in topic_ids])
    for i in np.where(labels == NOISE)[0]:
        sims = C @ X[i]
        best = int(np.argmax(sims))
        if sims[best] >= floor[topic_ids[best]]:
            labels[i] = topic_ids[best]
    return labels


def cap_topics(X: np.ndarray, labels: np.ndarray, max_topics: int = MAX_TOPICS) -> np.ndarray:
    """Merge the two most similar topics (by centroid) until at most max_topics remain."""
    labels = labels.copy()
    while len(set(labels.tolist()) - {NOISE}) > max_topics:
        cents = centroids(X, labels)
        ids = list(cents)
        C = np.stack([cents[t] for t in ids])
        sim = C @ C.T
        np.fill_diagonal(sim, -np.inf)
        a, b = np.unravel_index(int(np.argmax(sim)), sim.shape)
        labels[labels == ids[b]] = ids[a]
    return relabel(labels)


def distances(X: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Cosine distance of each article to its topic centroid (nearest one for noise)."""
    cents = centroids(X, labels)
    if not cents:
        return np.zeros(len(X))
    ids = list(cents)
    C = np.stack([cents[t] for t in ids])
    sims = X @ C.T
    out = np.empty(len(X))
    for i, t in enumerate(labels.tolist()):
        out[i] = 1 - (sims[i, ids.index(t)] if t != NOISE else sims[i].max())
    return out


def representatives(X: np.ndarray, labels: np.ndarray, k: int = 3) -> dict[int, list[int]]:
    """Indices of the k articles closest to each topic centroid."""
    out = {}
    for t, c in centroids(X, labels).items():
        members = np.where(labels == t)[0]
        out[t] = members[np.argsort(-(X[members] @ c))][:k].tolist()
    return out


_URL = re.compile(r"\b(?:https?://|www\.)\S+")

# Web-page and citation boilerplate that survives text extraction.
BOILERPLATE = frozenset(
    """
    abstract accessed al archive archived article articles bibcode cite cited citation
    click cookie cookies copyright doi download edit et fig figure figures html http
    https isbn issn journal menu new opens original page pages pdf pmc pmid pp press
    privacy published publisher read retrieved share site subscribe tab table vol
    volume website wikipedia www
    acad biol chem curr econ environ int lett med natl nat proc res rev sci soc
    january february march april may june july august september october november december
    """.split()
)


def topic_terms(
    texts: list[str], labels: np.ndarray, top_n: int = 10
) -> dict[int, list[tuple[str, float]]]:
    """
    c-TF-IDF (BERTopic): treat each topic's text as one document. A term's
    weight is its frequency in the topic times log(1 + A / f), where A is the
    average word count per topic and f the term's frequency across all topics,
    so words common everywhere sink and words particular to a topic rise.

    `texts` holds one string per article. A term must also appear in at least
    two of a topic's articles, so one page's menus, references or author names
    can't define a topic.
    """
    topics_ = sorted(set(labels.tolist()) - {NOISE})
    if not topics_:
        return {}
    vectorizer = CountVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | BOILERPLATE),
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z-]+[a-zA-Z]\b",  # no apostrophes: "it's" isn't a term
        lowercase=True,
    )
    per_article = vectorizer.fit_transform([_URL.sub(" ", t) for t in texts]).tocsr()
    vocab = vectorizer.get_feature_names_out()

    counts = np.vstack([np.asarray(per_article[labels == t].sum(axis=0)) for t in topics_])
    spread = np.vstack([np.asarray((per_article[labels == t] > 0).sum(axis=0)) for t in topics_])

    tf = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
    avg_words = counts.sum() / len(topics_)
    idf = np.log(1 + avg_words / np.maximum(counts.sum(axis=0), 1))
    scores = tf * idf
    if len(topics_) > 1:
        # A term used by every topic can't tell them apart.
        scores[:, (counts > 0).all(axis=0)] = 0
    for row, t in enumerate(topics_):
        min_articles = min(2, int(np.sum(labels == t)))
        scores[row, spread[row] < min_articles] = 0

    out = {}
    for row, t in enumerate(topics_):
        picked: list[tuple[str, float]] = []
        for j in np.argsort(-scores[row])[: top_n * 3]:
            if scores[row, j] <= 0:
                break
            term = str(vocab[j])
            # Skip a unigram already covered by a stronger bigram, and vice versa.
            if any(term in p or p in term for p, _ in picked):
                continue
            picked.append((term, float(scores[row, j])))
            if len(picked) == top_n:
                break
        out[t] = picked
    return out


def model_topics(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    The full topic model for normalised article vectors.
    Returns (labels, 2D map coordinates, distance to topic centroid).
    """
    Z5 = reduce(X, dims=5, min_dist=0.0)
    labels = find_topics(Z5)
    labels = merge_indistinct(X, labels)
    labels = assign_noise(X, labels)
    labels = cap_topics(X, labels)
    # Map layout: a wider neighbourhood and looser packing than the clustering
    # space, so topics get room on screen instead of crowding into a few islands
    # (measured on real corpora: ~2.5x larger topic areas, still clearly separated).
    coords = reduce(X, dims=2, min_dist=0.8, neighbors=20, spread=1.5)
    return labels, coords, distances(X, labels)
