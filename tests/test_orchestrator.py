from backend.models import AnalyzeRequest, Review
from backend.llm.client import FakeLLM
from backend.workflow.orchestrator import Orchestrator

BODIES = [
    "subscription charged twice and no refund", "订阅扣了两次钱",
    "the app keeps crashing on startup", "闪退",
    "hard to find the pause button", "不好用",
    "I love this app", "great workout", "nice", "ok",
    "update broke my progress", "data disappeared",
]


def _imported_reviews(n=12):
    return [Review(review_id=f"r{i}", body=BODIES[i % len(BODIES)],
                   rating=1 if i % 3 == 0 else 5, source="import") for i in range(n)]


def _llm_responses():
    plan = {"focus_areas": ["订阅", "易用性"], "constraints": [],
            "analysis_plan": "关注订阅与易用性"}
    topics = {"topics": [
        {"topic_id": "T1", "topic_name": "订阅扣款问题", "description": "d",
         "member_ids": ["r0", "r1"], "evidence": ["subscription charged twice"],
         "opposing_feedback": [], "confidence": "high", "confidence_reason": "n=2"},
        {"topic_id": "T2", "topic_name": "崩溃问题", "description": "d",
         "member_ids": ["r2", "r3"], "evidence": ["crashing"],
         "opposing_feedback": [], "confidence": "medium", "confidence_reason": "n=2"}]}
    merge = {"topics": topics["topics"], "merge_log": []}
    s4 = {"findings": [
        {"kind": "model_derived", "statement": "订阅扣款问题影响严重",
         "supporting_review_ids": ["r0", "r1"], "confidence": "high",
         "uncertainty": "n=2", "conflicting_evidence": [], "topic_refs": ["T1"]}]}
    s5 = {"requirements": [
        {"req_id": "PRD-1", "title": "修复订阅扣款问题", "description": "d",
         "priority": "P0", "version": "v8.1", "rationale": "r",
         "evidence_refs": ["F-T1-s", "r0", "r1"], "acceptance_criteria": ["c"]}]}
    s6 = {"test_cases": [
        {"case_id": "TC-1", "title": "订阅支付一次", "preconditions": "p",
         "steps": ["s"], "expected_results": ["e"], "req_refs": ["PRD-1"]}]}
    return [plan, topics, merge, s4, s5, s6]


def test_full_workflow_degraded_ok():
    orch = Orchestrator(llm=None)
    snap = orch.execute(AnalyzeRequest(goal="订阅转化"),
                        reviews=_imported_reviews())
    assert snap.status in ("done", "degraded")
    assert len(snap.reviews) >= 12
    assert snap.meta.get("model_mode") == "degraded"
    report = snap.validation_report
    assert report  # 校验报告必须存在


def test_full_workflow_with_llm():
    llm = FakeLLM(_llm_responses())
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(goal="订阅转化"),
                        reviews=_imported_reviews())
    assert snap.status == "done"
    assert snap.plan.focus_areas == ["订阅", "易用性"]
    assert len(snap.topics) >= 2
    assert any(r.req_id == "PRD-1" for r in snap.requirements)
    assert len(snap.test_cases) >= 1
    # 全链路引用完整
    assert snap.validation_report.get("passed") is True


def test_events_published():
    events = []
    orch = Orchestrator(llm=None, on_event=events.append)
    orch.execute(AnalyzeRequest(), reviews=_imported_reviews(6))
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "run.finished" in types
    assert any(t == "stage.output" for t in types)


def test_workflow_cleans_and_dedups():
    reviews = _imported_reviews(4)
    # 制造重复：与 r0 完全相同的 作者+正文+评分
    reviews.append(Review(review_id="dup1", body=BODIES[0], rating=1, source="import"))
    orch = Orchestrator(llm=None)
    snap = orch.execute(AnalyzeRequest(), reviews=reviews)
    assert any(r.is_duplicate for r in snap.reviews)
