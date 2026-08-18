import json
import re
from pathlib import Path

from .stage_base import StageBase
from ..models import Requirement

# 版本号格式校验（vX.Y 或 vX.Y.Z），不预设具体版本方案，由模型按迭代需求动态规划
_VERSION_RE = re.compile(r"^v\d+(\.\d+){1,2}$")

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


def priority_from_stats(f) -> str:
    """规则定优先级初值：频次 + 影响。"""
    if f.sample_count >= 10 and f.kind == "statistical":
        return "P0"
    if f.sample_count >= 5:
        return "P1"
    return "P2"


def build_requirements_with_llm(findings, llm, meta) -> list[Requirement]:
    # 假设（assumption）类结论无实证支撑，不得作为需求依据（只能列入风险与假设）
    valid_f = {x.finding_id for x in findings if x.kind != "assumption"}
    valid_r = set(meta.get("valid_review_ids", []))
    user = (PROMPT_DIR / "s5_prd.txt").read_text(encoding="utf-8").format(
        findings_json=json.dumps([f.model_dump() for f in findings], ensure_ascii=False),
        app_name=meta.get("app_name", "(应用)"),
        version_stats=json.dumps(meta.get("version_stats", {}), ensure_ascii=False))
    data = llm.chat_json(
        "你是资深产品经理。基于已验证结论撰写 PRD 需求，只输出 JSON。", user,
        {"requirements": []})
    out: list[Requirement] = []
    if not data or not isinstance(data.get("requirements"), list):
        return out
    for i, r in enumerate(data["requirements"]):
        if not isinstance(r, dict):
            continue
        refs = [x for x in r.get("evidence_refs", []) if x in valid_f or x in valid_r]
        if not refs or not any(x in valid_f for x in refs):
            continue  # 无有效证据引用 → 丢弃
        pri = r.get("priority") if r.get("priority") in ("P0", "P1", "P2") else "P1"
        ver = str(r.get("version") or "")
        if not _VERSION_RE.match(ver):  # 动态版本方案，仅校验格式，不绑定具体版本
            ver = "v1.0"
        out.append(Requirement(
            req_id=f"PRD-{i + 1}",
            title=r.get("title", "未命名需求")[:80],
            description=r.get("description", "")[:500],
            priority=pri, version=ver,
            rationale=r.get("rationale", "")[:300],
            evidence_refs=refs,
            acceptance_criteria=r.get("acceptance_criteria", [])[:8],
        ))
    return out


def fallback_requirements(findings) -> list[Requirement]:
    """降级模板：从统计结论生成。明确标记 degraded。"""
    out = []
    for i, f in enumerate([x for x in findings if x.kind != "assumption"][:6]):
        out.append(Requirement(
            req_id=f"PRD-{i + 1}",
            title=f"改进『{(f.statement or '')[:40]}』",
            description="降级模式生成，请结合人工判断",
            priority=priority_from_stats(f), version="v1.0",
            rationale="degraded: rule-based",
            evidence_refs=[f.finding_id] + f.supporting_review_ids[:5],
            acceptance_criteria=["验证相关评论问题得到解决"],
        ))
    return out


class S5PRD(StageBase):
    name = "s5"

    def run(self):
        rec = self.stage("s5")
        rec.status = "running"
        self.emit("stage.started", {})
        try:
            if self.mode == "llm" and self.llm.available and self.snapshot.findings:
                self.snapshot.requirements = build_requirements_with_llm(
                    self.snapshot.findings, self.llm,
                    {"valid_review_ids": [r.review_id for r in self.snapshot.reviews]})
                rec.model_used = self.llm.mode
                if not self.snapshot.requirements:
                    rec.status = "degraded"
                    rec.summary = "模型需求全部未通过证据校验，使用模板需求"
                    self.snapshot.requirements = fallback_requirements(self.snapshot.findings)
                else:
                    rec.summary = f"生成 {len(self.snapshot.requirements)} 条需求（模型驱动）"
            else:
                self.snapshot.requirements = fallback_requirements(self.snapshot.findings)
                rec.status = "degraded"
                rec.summary = "降级模式：模板需求"
            self.emit("stage.output", {
                "requirements": [r.model_dump() for r in self.snapshot.requirements]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"
