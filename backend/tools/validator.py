"""追溯校验器（S7）：确定性规则，检查 评论→结论→需求→用例 全链路引用。"""

from ..models import RunSnapshot


def _orphans(items, valid_review_ids, field, valid_non_review=()) -> list[str]:
    """找出引用列表中既不是评论 ID、也不是其它有效实体引用的孤儿值。"""
    out = []
    for it in items:
        for ref in getattr(it, field, []) or []:
            if ref in valid_non_review:
                continue
            if ref not in valid_review_ids:
                out.append(ref)
    return list(dict.fromkeys(out))


def validate_chain(snap: RunSnapshot) -> dict:
    valid_rids = {r.review_id for r in snap.reviews}
    valid_fids = {f.finding_id for f in snap.findings}
    valid_reqs = {r.req_id for r in snap.requirements}
    valid_non_review = valid_fids | valid_reqs

    orphan_findings = _orphans(snap.findings, valid_rids, "supporting_review_ids")
    orphan_reqs = _orphans(snap.requirements, valid_rids, "evidence_refs",
                          valid_non_review=valid_non_review)
    req_missing_evidence = [r.req_id for r in snap.requirements
                            if not any(x in valid_fids for x in r.evidence_refs)]
    test_missing_req = [c.case_id for c in snap.test_cases
                        if not any(x in valid_reqs for x in c.req_refs)]
    reqs_without_cases = [r.req_id for r in snap.requirements
                          if not any(r.req_id in c.req_refs for c in snap.test_cases)]
    assumptions = [f.finding_id for f in snap.findings if f.kind == "assumption"]

    orphan_review_refs = {"findings": orphan_findings, "requirements": orphan_reqs}
    passed = not (orphan_findings or orphan_reqs or req_missing_evidence
                  or test_missing_req or reqs_without_cases)
    return {
        "passed": passed,
        "orphan_review_refs": orphan_review_refs,
        "requirements_missing_evidence": req_missing_evidence,
        "test_cases_missing_requirements": test_missing_req,
        "requirements_without_cases": reqs_without_cases,
        "assumption_findings": assumptions,
        "stats": {"findings": len(snap.findings), "requirements": len(snap.requirements),
                  "test_cases": len(snap.test_cases), "corrections": len(snap.corrections)},
    }
