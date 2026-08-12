from backend.models import (RunSnapshot, Review, TopicCluster, Finding,
                            Requirement, TestCase)
from backend.tools.validator import validate_chain


def _snapshot():
    snap = RunSnapshot(run_id="r1")
    snap.reviews = [Review(review_id="r0", body="b", rating=5)]
    snap.findings = [Finding(finding_id="F1", kind="model_derived", statement="s",
                             supporting_review_ids=["r0", "ghost"])]
    snap.requirements = [Requirement(req_id="PRD-1", title="t",
                                     evidence_refs=["F1", "ghost2"], version="v8.1")]
    snap.test_cases = [TestCase(case_id="TC-1", title="t", steps=["s"],
                                expected_results=["e"], req_refs=["PRD-1"], review_refs=["r0"])]
    return snap


def test_orphan_reference_detected():
    snap = _snapshot()
    report = validate_chain(snap)
    assert report["orphan_review_refs"]["findings"] == ["ghost"]
    assert report["orphan_review_refs"]["requirements"] == ["ghost2"]
    assert report["passed"] is False


def test_clean_chain_passes():
    snap = _snapshot()
    snap.findings[0].supporting_review_ids = ["r0"]
    snap.requirements[0].evidence_refs = ["F1", "r0"]
    report = validate_chain(snap)
    assert report["passed"] is True
    assert report["orphan_review_refs"] == {"findings": [], "requirements": []}


def test_requirement_without_finding_ref_detected():
    snap = _snapshot()
    snap.requirements[0].evidence_refs = ["r0"]   # 无 finding 引用
    report = validate_chain(snap)
    assert report["requirements_missing_evidence"] == ["PRD-1"]


def test_requirement_without_cases_detected():
    snap = _snapshot()
    snap.test_cases = []
    report = validate_chain(snap)
    assert report["requirements_without_cases"] == ["PRD-1"]


def test_assumptions_listed():
    snap = _snapshot()
    snap.findings.append(Finding(finding_id="F2", kind="assumption",
                                 statement="s", supporting_review_ids=["r0"]))
    report = validate_chain(snap)
    assert "F2" in report["assumption_findings"]
