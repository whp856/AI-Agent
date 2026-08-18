from backend.models import Finding
from backend.llm.client import FakeLLM
from backend.workflow.s5_prd import build_requirements_with_llm, fallback_requirements, priority_from_stats


def _findings():
    return [
        Finding(finding_id="F-T1-s", kind="statistical",
                statement="订阅主题 12 条评论均分 1.5",
                supporting_review_ids=["r0", "r1"], sample_count=12,
                confidence="high", topic_refs=["T1"]),
    ]


def test_prd_with_llm_keeps_valid_refs():
    llm = FakeLLM([{"requirements": [
        {"req_id": "PRD-1", "title": "修复订阅支付失败", "description": "d",
         "priority": "P0", "version": "v8.1", "rationale": "r",
         "evidence_refs": ["F-T1-s", "r0", "r1", "FAKE-ID"],
         "acceptance_criteria": ["c1"]}]}])
    reqs = build_requirements_with_llm(_findings(), llm,
                                       {"valid_review_ids": ["r0", "r1"]})
    assert len(reqs) == 1
    assert "FAKE-ID" not in reqs[0].evidence_refs
    assert reqs[0].evidence_refs == ["F-T1-s", "r0", "r1"]
    assert reqs[0].priority == "P0"


def test_prd_drops_requirement_without_finding_ref():
    llm = FakeLLM([{"requirements": [
        {"req_id": "PRD-1", "title": "凭空需求", "evidence_refs": ["r0"],
         "priority": "P1", "version": "v8.2"}]}])
    reqs = build_requirements_with_llm(_findings(), llm, {"valid_review_ids": ["r0"]})
    assert reqs == []


def test_prd_dynamic_version_kept():
    """版本方案动态化：模型自主规划的合法版本号不被白名单改写。"""
    llm = FakeLLM([{"requirements": [
        {"req_id": "PRD-1", "title": "修复订阅支付失败", "description": "d",
         "priority": "P0", "version": "v3.7", "rationale": "r",
         "evidence_refs": ["F-T1-s", "r0", "r1"],
         "acceptance_criteria": ["c1"]}]}])
    reqs = build_requirements_with_llm(_findings(), llm,
                                       {"valid_review_ids": ["r0", "r1"]})
    assert reqs[0].version == "v3.7"


def test_prd_invalid_version_fallback():
    """非法版本号（不在 vX.Y 格式）回退到 v1.0，不绑定预设版本。"""
    llm = FakeLLM([{"requirements": [
        {"req_id": "PRD-1", "title": "t", "version": "最新版", "evidence_refs": ["F-T1-s", "r0"]}]}])
    reqs = build_requirements_with_llm(_findings(), llm, {"valid_review_ids": ["r0"]})
    assert reqs[0].version == "v1.0"


def test_fallback_requirements_marked():
    reqs = fallback_requirements(_findings())
    assert len(reqs) >= 1
    assert "degraded" in reqs[0].rationale
    assert reqs[0].priority == "P0"


def test_priority_rules():
    f0 = Finding(finding_id="a", kind="statistical", statement="s", sample_count=12)
    f1 = Finding(finding_id="b", kind="statistical", statement="s", sample_count=5)
    f2 = Finding(finding_id="c", kind="statistical", statement="s", sample_count=2)
    assert priority_from_stats(f0) == "P0"
    assert priority_from_stats(f1) == "P1"
    assert priority_from_stats(f2) == "P2"
