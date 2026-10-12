import numpy as np
import pytest

from backend import topics
from backend.topics import NOISE


def blobs(n_per=12, centers=4, dim=32, spread=0.05, seed=0):
    """Well-separated groups of unit vectors."""
    rng = np.random.default_rng(seed)
    C = topics.normalize(rng.normal(size=(centers, dim)))
    X = np.concatenate([C[c] + rng.normal(scale=spread, size=(n_per, dim)) for c in range(centers)])
    truth = np.repeat(np.arange(centers), n_per)
    return topics.normalize(X), truth


def same_partition(a, b):
    """True if two labelings group the items identically (ids may differ)."""
    pairs = {(x, y) for x, y in zip(a.tolist(), b.tolist(), strict=True)}
    return len({x for x, _ in pairs}) == len(pairs) == len({y for _, y in pairs})


def test_article_vectors_average_and_normalise():
    v = np.array([[2.0, 0], [0, 2.0], [3.0, 0]])
    ids, X = topics.article_vectors(v, ["a", "a", "b"])
    assert ids == ["a", "b"]
    np.testing.assert_allclose(X[0], [np.sqrt(0.5), np.sqrt(0.5)])
    np.testing.assert_allclose(np.linalg.norm(X, axis=1), 1)


def test_model_recovers_separated_topics():
    X, truth = blobs()
    labels, coords, dist = topics.model_topics(X)
    assert set(labels.tolist()) == {0, 1, 2, 3}
    assert same_partition(labels, truth)
    assert coords.shape == (len(X), 2)
    assert np.all(dist >= -1e-6) and np.all(dist < 0.2)


def test_relabel_orders_by_size_and_keeps_noise():
    out = topics.relabel(np.array([5, 5, 2, 2, 2, NOISE, 9]))
    assert out.tolist() == [1, 1, 0, 0, 0, NOISE, 2]


def test_noise_joins_topic_only_when_typical():
    X, truth = blobs(centers=2)
    labels = truth.copy()
    # The most typical member of topic 0, wrongly marked noise.
    typical = int(np.argmax(X[truth == 0] @ topics.centroids(X, truth)[0]))
    labels[typical] = NOISE
    stray = topics.normalize(np.random.default_rng(1).normal(size=(1, X.shape[1])))
    X = np.vstack([X, stray])
    labels = np.append(labels, NOISE)

    out = topics.assign_noise(X, labels)
    assert out[typical] == 0  # rejoined
    assert out[-1] == NOISE  # unlike anything: stays unclustered


def test_cap_merges_most_similar_topics():
    X, truth = blobs(centers=5, n_per=6)
    # Make topics 3 and 4 nearly identical so they're the pair to merge.
    X[truth == 4] = X[truth == 3][: (truth == 4).sum()] + 1e-3
    X = topics.normalize(X)
    out = topics.cap_topics(X, truth, max_topics=4)
    assert len(set(out.tolist())) == 4
    assert len(set(out[(truth == 3) | (truth == 4)].tolist())) == 1


def test_tiny_corpus_is_one_topic():
    X, _ = blobs(n_per=1, centers=4)
    assert topics.find_topics(X).tolist() == [0, 0, 0, 0]


def test_topic_terms_prefer_distinctive_words():
    texts = [
        "cool roofs reflect sunlight; white roofs lower city heat",
        "green roofs and cool roofs cut rooftop heat in the city",
        "heat equity: redlining and gentrification shape city heat exposure",
        "gentrification and redlining concentrate heat in poorer city blocks",
    ]
    labels = np.array([0, 0, 1, 1])
    terms = topics.topic_terms(texts, labels, top_n=4)
    zero = [t for t, _ in terms[0]]
    one = [t for t, _ in terms[1]]
    assert any("roofs" in t for t in zero)
    assert any("gentrification" in t or "redlining" in t for t in one)
    assert "city" not in zero + one  # in every topic: no signal
    assert all("http" not in t for t in zero + one)


def test_topic_terms_ignore_noise_and_urls():
    terms = topics.topic_terms(
        ["see https://example.com/page about tariffs and tariffs", "unrelated words here"],
        np.array([0, NOISE]),
    )
    assert list(terms) == [0]
    assert all("example" not in t for t, _ in terms[0])


@pytest.mark.parametrize("k", [1, 3])
def test_representatives_are_closest_members(k):
    X, truth = blobs(centers=2)
    reps = topics.representatives(X, truth, k=k)
    assert set(reps) == {0, 1}
    for t, idx in reps.items():
        assert len(idx) == k
        assert all(truth[i] == t for i in idx)


def test_merge_indistinct_joins_arbitrary_splits_only():
    X, truth = blobs(centers=3)
    split = truth.copy()
    split[(truth == 0) & (np.arange(len(truth)) % 2 == 0)] = 7  # cut topic 0 in half
    out = topics.merge_indistinct(X, split)
    assert same_partition(out, truth)
