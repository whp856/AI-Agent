import json
from pathlib import Path

from .stage_base import StageBase
from ..models import TestCase

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


def build_testcases_with_llm(requirements, llm, review_map) -> list[TestCase]:
    """用例生成。review_refs 强制继承需求证据链，不允许模型编造评论 ID。"""
    user = (PROMPT_DIR / "s6_testcases.txt").read_text(encoding="utf-8").format(
        requirements_json=json.dumps([r.model_dump() for r in requirements], ensure_ascii=False))
    data = llm.chat_json(
        "你是测试工程师。基于 PRD 需求生成测试用例，只输出 JSON。", user, {"test_cases": []})
    out: list[TestCase] = []
    if not data or not isinstance(data.get("test_cases"), list):
        return out
    valid_reqs = {r.req_id for r in requirements}
    for i, c in enumerate(data["test_cases"]):
        if not isinstance(c, dict):
            continue
        reqs = [x for x in c.get("req_refs", []) if x in valid_reqs]
        if not reqs:
            continue
        refs: list[str] = []
        for r in reqs:
            refs.extend(review_map.get(r, []))
        refs = list(dict.fromkeys(refs))[:10]
        out.append(TestCase(
            case_id=f"TC-{i + 1}",
            title=c.get("title", "未命名用例")[:80],
            preconditions=c.get("preconditions", "")[:200],
            steps=c.get("steps", [])[:12],
            expected_results=c.get("expected_results", [])[:8],
            req_refs=reqs, review_refs=refs,
        ))
    return out


def fallback_testcases(requirements) -> list[TestCase]:
    """降级模板：每条需求一条正向 + 一条异常。"""
    out = []
    for i, r in enumerate(requirements):
        review_refs = [x for x in r.evidence_refs if not x.startswith("F-")][:5]
        out.append(TestCase(
            case_id=f"TC-{i + 1}", title=f"验证『{r.title}』- 正向",
            preconditions="应用处于可测试环境",
            steps=["进入需求对应功能入口", "按验收标准执行操作", "记录结果"],
            expected_results=["需求验收标准全部满足", "对应评论问题不再出现"],
            req_refs=[r.req_id], review_refs=review_refs))
        out.append(TestCase(
            case_id=f"TC-{i + 1}b", title=f"验证『{r.title}』- 异常/边界",
            preconditions="应用处于可测试环境",
            steps=["网络断开/异常输入/重复操作等边界条件", "执行操作"],
            expected_results=["应用不崩溃且有合理提示"],
            req_refs=[r.req_id], review_refs=review_refs))
    return out


class S6Testcases(StageBase):
    name = "s6"

    def run(self):
        rec = self.stage("s6")
        rec.status = "running"
        try:
            if self.mode == "llm" and self.llm.available and self.snapshot.requirements:
                review_map = {}
                for r in self.snapshot.requirements:
                    review_map[r.req_id] = [x for x in r.evidence_refs
                                            if not x.startswith("F-") and not x.startswith("PRD-")]
                self.snapshot.test_cases = build_testcases_with_llm(
                    self.snapshot.requirements, self.llm, review_map)
                rec.model_used = self.llm.mode
                if not self.snapshot.test_cases:
                    rec.status = "degraded"
                    rec.summary = "模型用例未通过校验，使用模板用例"
                    self.snapshot.test_cases = fallback_testcases(self.snapshot.requirements)
                else:
                    rec.summary = f"生成 {len(self.snapshot.test_cases)} 条用例（模型驱动）"
            else:
                self.snapshot.test_cases = fallback_testcases(self.snapshot.requirements)
                rec.status = "degraded"
                rec.summary = "降级模式：模板用例"
            self.emit("stage.output", {
                "test_cases": [c.model_dump() for c in self.snapshot.test_cases]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"
