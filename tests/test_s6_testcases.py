from backend.models import Requirement
from backend.llm.client import FakeLLM
from backend.workflow.s6_testcases import build_testcases_with_llm, fallback_testcases


def test_review_refs_inherited_not_fabricated():
    req = Requirement(req_id="PRD-1", title="修复订阅支付失败", priority="P0",
                      evidence_refs=["F-T1-s", "r0", "r1"], version="v8.1")
    llm = FakeLLM([{"test_cases": [
        {"case_id": "TC-1", "title": "订阅成功支付", "preconditions": "p",
         "steps": ["s1"], "expected_results": ["e1"], "req_refs": ["PRD-1"],
         "review_refs": ["FAKE-999"]}]}])   # 模型编造的 ID 应被替换为证据链 ID
    cases = build_testcases_with_llm([req], llm, {"PRD-1": ["r0", "r1"]})
    assert len(cases) == 1
    assert "FAKE-999" not in cases[0].review_refs
    assert set(cases[0].review_refs) <= {"r0", "r1"}


def test_case_with_unknown_req_dropped():
    req = Requirement(req_id="PRD-1", title="t", evidence_refs=["F1", "r0"], version="v8.1")
    llm = FakeLLM([{"test_cases": [
        {"case_id": "TC-1", "title": "x", "steps": ["s"], "expected_results": ["e"],
         "req_refs": ["PRD-GHOST"]}]}])
    cases = build_testcases_with_llm([req], llm, {"PRD-1": ["r0"]})
    assert cases == []


def test_fallback_cases_positive_and_negative():
    req = Requirement(req_id="PRD-1", title="t", evidence_refs=["F1", "r0"], version="v8.1")
    cases = fallback_testcases([req])
    assert len(cases) == 2
    assert "b" in cases[1].case_id
    assert "r0" in cases[0].review_refs
