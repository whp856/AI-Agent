from backend.models import Review, TopicCluster
from backend.workflow.s4_findings import build_statistical_findings


def _setup(n=6, low_ids=("r0", "r1", "r2")):
    reviews = [Review(review_id=f"r{i}", body=f"b{i}",
                      rating=1 if f"r{i}" in low_ids else 5) for i in range(n)]
    t = TopicCluster(topic_id="T1", topic_name="订阅", member_ids=list(low_ids))
    return reviews, [t]


def test_statistical_findings_have_kind():
    reviews, topics = _setup()
    findings = build_statistical_findings(topics, reviews, min_sample=3)
    assert all(f.kind == "statistical" for f in findings)
    assert findings[0].sample_count == 3
    assert findings[0].confidence in ("high", "medium", "low")


def test_insufficient_sample_becomes_assumption():
    reviews, topics = _setup(n=4, low_ids=("r0",))
    findings = build_statistical_findings(topics, reviews, min_sample=3)
    assert findings[0].kind == "assumption"
    assert findings[0].confidence == "low"


def test_high_confidence_for_large_sample():
    reviews, topics = _setup(n=20, low_ids=tuple(f"r{i}" for i in range(12)))
    findings = build_statistical_findings(topics, reviews, min_sample=3)
    assert findings[0].confidence == "high"
