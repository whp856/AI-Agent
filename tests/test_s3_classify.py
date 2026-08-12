from backend.models import Review, AnalysisPlan
from backend.llm.client import FakeLLM
from backend.workflow.s3_classify import classify_with_llm, keyword_fallback_topics


def _reviews(n=5):
    return [Review(review_id=f"r{i}", body=f"评论内容 {i}",
                   rating=1 if i % 2 else 5) for i in range(n)]


def test_classify_with_llm_merges_and_validates():
    # 5 条评论 = 1 批（≤40），调用顺序：分类批次 → 合并
    llm = FakeLLM([
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅问题", "description": "d",
             "member_ids": ["r0", "r1"], "evidence": ["评论内容 0"],
             "opposing_feedback": [], "confidence": "high", "confidence_reason": "n=2"}]},
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅问题", "description": "d",
             "member_ids": ["r0", "r1", "r2"], "evidence": ["评论内容 0"],
             "opposing_feedback": [], "confidence": "high", "confidence_reason": "n=3"}],
         "merge_log": [{"merged": ["T1", "T1"], "into": "T1", "reason": "same"}]},
    ])
    topics = classify_with_llm(_reviews(), AnalysisPlan(), llm)
    assert len(topics) == 1
    assert set(topics[0].member_ids) == {"r0", "r1", "r2"}


def test_classify_filters_invalid_ids():
    llm = FakeLLM([
        {"topics": [
            {"topic_id": "T1", "topic_name": "x", "member_ids": ["r0", "GHOST-1"],
             "evidence": [], "opposing_feedback": [], "confidence": "high"}]},
        {"topics": [
            {"topic_id": "T1", "topic_name": "x", "member_ids": ["r0", "GHOST-1"],
             "evidence": [], "opposing_feedback": [], "confidence": "high"}],
         "merge_log": []},
    ])
    topics = classify_with_llm(_reviews(3), AnalysisPlan(), llm)
    assert len(topics) == 1
    assert topics[0].member_ids == ["r0"]


def test_classify_llm_none_falls_back_to_batch():
    llm = FakeLLM([])
    topics = classify_with_llm(_reviews(5), AnalysisPlan(), llm)
    assert topics == []


def test_keyword_fallback():
    reviews = _reviews(3)
    reviews[0].body_cleaned = "subscription charged twice, refund please"
    reviews[1].body_cleaned = "the app crashed on startup"
    topics = keyword_fallback_topics(reviews)
    names = " ".join(t.topic_name for t in topics)
    assert "订阅" in names
    assert "崩溃" in names
    assert all(t.confidence == "low" for t in topics)
