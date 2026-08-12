from backend.models import Review, TopicCluster
from backend.tools.stats import topic_stats, rating_distribution, version_stats


def _reviews():
    return [
        Review(review_id=f"r{i}", body=f"b{i}", rating=1 if i < 3 else 5,
               version="8.4" if i < 4 else "8.5")
        for i in range(6)
    ]


def test_rating_distribution():
    d = rating_distribution(_reviews())
    assert d["low"] == 3 and d["high"] == 3
    assert d["avg_rating"] == 3.0


def test_topic_stats():
    reviews = _reviews()
    t = TopicCluster(topic_id="T1", topic_name="x", member_ids=["r0", "r1", "r2"])
    stats = topic_stats([t], reviews)
    assert stats[0]["count"] == 3
    assert stats[0]["avg_rating"] == 1.0
    assert stats[0]["low_ratio"] == 1.0


def test_topic_stats_ignores_unknown_ids():
    reviews = _reviews()
    t = TopicCluster(topic_id="T1", topic_name="x", member_ids=["r0", "ghost"])
    stats = topic_stats([t], reviews)
    assert stats[0]["count"] == 1


def test_version_stats():
    d = version_stats(_reviews())
    assert d.get("8.4") == 4
    assert d.get("8.5") == 2
