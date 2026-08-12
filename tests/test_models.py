from backend.models import Review, Finding, TopicCluster


def test_review_rating_range():
    r = Review(review_id="1", rating=3)
    assert r.country == "US"
    assert r.source == "rss"


def test_review_invalid_rating_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Review(review_id="2", rating=8)


def test_finding_defaults():
    f = Finding(finding_id="F1", statement="s", kind="statistical")
    assert f.confidence == "medium"
    assert f.conflicting_evidence == []
    assert f.supporting_review_ids == []


def test_topic_defaults():
    t = TopicCluster(topic_id="T1", topic_name="订阅")
    assert t.confidence == "medium"
