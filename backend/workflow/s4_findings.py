import json
from pathlib import Path

from .stage_base import StageBase
from ..models import Finding
from ..tools.stats import topic_stats, rating_distribution, version_stats

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


def build_statistical_findings(topics, reviews, min_sample=3) -> list[Finding]:
    """统计结论：程序直接生成，kind=statistical；样本不足降级 assumption。"""
    stats = topic_stats(topics, reviews)
    findings = []
    for s in stats:
        if s["count"] < min_sample:
            findings.append(Finding(
                finding_id=f"F-{s['topic_id']}-a", kind="assumption",
                statement=f"主题『{s['topic_name']}』样本仅 {s['count']} 条，不足以下结论（假设）",
                supporting_review_ids=s["member_ids"], sample_count=s["count"],
                confidence="low", uncertainty="样本量不足", topic_refs=[s["topic_id"]]))
            continue
        findings.append(Finding(
            finding_id=f"F-{s['topic_id']}-s", kind="statistical",
            statement=(f"主题『{s['topic_name']}』共 {s['count']} 条评论，"
                       f"平均评分 {s['avg_rating']}，低分占比 {s['low_ratio']}"),
            supporting_review_ids=s["member_ids"], sample_count=s["count"],
            confidence="high" if s["count"] >= 10 else "medium",
            uncertainty=f"数据窗口为最近评论，样本 n={s['count']}",
            topic_refs=[s["topic_id"]]))
    return findings


class S4Findings(StageBase):
    name = "s4"

    def run(self):
        rec = self.stage("s4")
        rec.status = "running"
        self.emit("stage.started", {})
        active = self.active_reviews()
        min_sample = self.snapshot.meta.get("min_sample", 3)
        try:
            stats_f = build_statistical_findings(self.snapshot.topics, active, min_sample)
            self.snapshot.findings = stats_f
            self.emit("stage.progress", {"stats": {
                "rating": rating_distribution(active),
                "versions": version_stats(active),
                "topics": topic_stats(self.snapshot.topics, active)}})
            if self.mode == "llm" and self.llm.available and self.snapshot.topics:
                derived = self._llm_derive(active, min_sample)
                self.snapshot.findings.extend(derived)
                rec.model_used = self.llm.mode
                rec.summary = f"统计结论 {len(stats_f)} 条 + 模型推导 {len(derived)} 条"
            else:
                if self.snapshot.topics:
                    rec.status = "degraded"
                rec.summary = "降级模式：仅统计结论（模型未参与推导）"
            self.emit("stage.output", {
                "findings": [f.model_dump() for f in self.snapshot.findings]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"

    def _llm_derive(self, active, min_sample):
        stats = {
            "topic_stats": topic_stats(self.snapshot.topics, active),
            "rating": rating_distribution(active),
            "versions": version_stats(active),
        }
        topics = [t.model_dump() for t in self.snapshot.topics]
        user = (PROMPT_DIR / "s4_findings.txt").read_text(encoding="utf-8").format(
            stats_json=json.dumps(stats, ensure_ascii=False),
            topics_json=json.dumps(topics, ensure_ascii=False),
            analysis_goal=self.snapshot.plan.analysis_plan or "通用",
            min_sample=min_sample)
        data = self.llm.chat_json(
            "你是严谨的产品分析师。基于证据产出结论，只输出 JSON。", user, {"findings": []})
        out: list[Finding] = []
        if not data or not isinstance(data.get("findings"), list):
            return out
        valid = {r.review_id for r in active}
        for i, f in enumerate(data["findings"]):
            if not isinstance(f, dict):
                continue
            # 统计事实只能由确定性规则生成（build_statistical_findings）。
            # 模型输出的 statistical 一律改判为 model_derived，杜绝"模型伪装统计事实"。
            kind = f.get("kind") if f.get("kind") in (
                "model_derived", "assumption") else "model_derived"
            members = [m for m in f.get("supporting_review_ids", []) if m in valid]
            if not members:
                # 无任何评论引用 → 无实证支撑，强制降级为假设
                kind = "assumption"
            conf = f.get("confidence") if f.get("confidence") in ("high", "medium", "low") else "medium"
            out.append(Finding(
                finding_id=f"F-{len(self.snapshot.findings) + i + 1}-m", kind=kind,
                statement=f.get("statement", "")[:300],
                supporting_review_ids=members, sample_count=len(members),
                confidence=conf, uncertainty=f.get("uncertainty", "")[:200],
                conflicting_evidence=f.get("conflicting_evidence", [])[:3],
                topic_refs=[t for t in f.get("topic_refs", []) if t.startswith("T")],
            ))
        return out
