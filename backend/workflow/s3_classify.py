import json
from pathlib import Path

from .stage_base import StageBase
from ..models import TopicCluster, AnalysisPlan

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"

# 规则兜底主题词表：仅用于无模型时的降级演示，产出明确标记 degraded
KEYWORDS = {
    "订阅/付费问题": ["subscri", "订阅", "payment", "charge", "退款", "refund", "price", "价格", "free trial", "试用", "扣费", "续费"],
    "崩溃/故障": ["bug", "crash", "闪退", "崩溃", "freeze", "卡死", "error", "failed", "not working", "无法使用", "白屏", "卡住"],
    "易用性/界面": ["hard to use", "confusing", "不好用", "复杂", "difficult", "难用", "界面", "usability", "confusing"],
    "更新问题": ["update", "更新", "new version", "最新版", "broke", "变差", "upgrade"],
    "广告/弹窗": ["ad", "广告", "popup", "弹窗", "ads"],
    "数据丢失/进度": ["lost", "丢失", "data", "进度", "progress", "disappear", "消失", "没了", "删掉"],
    "训练内容/计划": ["workout", "训练", "exercise", "plan", "计划", "exercise plan", "强度"],
}


def _batch(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def classify_with_llm(reviews, plan: AnalysisPlan, llm) -> list[TopicCluster]:
    """分批调用 LLM 归纳主题 → 合并相似主题 → ID 合法性过滤。"""
    valid_ids = {r.review_id for r in reviews}
    sys_cls = "你是资深产品分析师。从评论中自行归纳语义主题，只输出 JSON。"
    batches = list(_batch(reviews, 40))
    batch_topics: list[dict] = []
    for b in batches:
        items = json.dumps(
            [{"review_id": r.review_id, "rating": r.rating,
              "body": (r.body_cleaned or r.body)[:500]} for r in b],
            ensure_ascii=False)
        user = (PROMPT_DIR / "s3_classify.txt").read_text(encoding="utf-8").format(
            app_name="(应用)", n=len(b),
            analysis_goal=plan.analysis_plan or "通用",
            constraints=json.dumps(plan.constraints, ensure_ascii=False),
            comments=items)
        data = llm.chat_json(sys_cls, user, {"topics": []})
        if data and isinstance(data.get("topics"), list):
            batch_topics.extend(data["topics"])
    if not batch_topics:
        return []
    sys_merge = "你是产品分析师。合并语义相似的主题，只输出 JSON。"
    user_merge = (PROMPT_DIR / "s3_merge.txt").read_text(encoding="utf-8").format(
        topics=json.dumps(batch_topics, ensure_ascii=False))
    merged = llm.chat_json(sys_merge, user_merge, {"topics": []})
    raw = merged.get("topics", batch_topics) if merged else batch_topics
    topics: list[TopicCluster] = []
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            continue
        members = [m for m in t.get("member_ids", []) if m in valid_ids]
        if not members:
            continue
        conf = t.get("confidence", "medium")
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        topics.append(TopicCluster(
            topic_id=f"T{i + 1}",
            topic_name=t.get("topic_name", "未命名主题")[:60],
            description=t.get("description", "")[:200],
            member_ids=members,
            evidence=t.get("evidence", [])[:3],
            opposing_feedback=t.get("opposing_feedback", [])[:3],
            confidence=conf,
            confidence_reason=t.get("confidence_reason", ""),
        ))
    return topics


def keyword_fallback_topics(reviews) -> list[TopicCluster]:
    """规则兜底：关键词聚类。仅降级模式使用。"""
    clusters: dict[str, list] = {}
    for r in reviews:
        text = (r.body_cleaned or r.body or "").lower()
        for label, kws in KEYWORDS.items():
            if any(k in text for k in kws):
                clusters.setdefault(label, []).append(r)
    topics = []
    for i, (label, members) in enumerate(clusters.items()):
        topics.append(TopicCluster(
            topic_id=f"T{i + 1}", topic_name=label,
            description="degraded: rule-based",
            member_ids=[m.review_id for m in members],
            evidence=[(m.body_cleaned or m.body)[:120] for m in members[:3]],
            confidence="low",
            confidence_reason="degraded: rule-based",
        ))
    return topics


class S3Classify(StageBase):
    name = "s3"

    def run(self):
        rec = self.stage("s3")
        rec.status = "running"
        active = self.active_reviews()
        try:
            if self.mode == "llm" and self.llm.available:
                self.snapshot.topics = classify_with_llm(active, self.snapshot.plan, self.llm)
                rec.model_used = self.llm.mode
                if not self.snapshot.topics:
                    rec.summary = "模型未产出有效主题，使用规则兜底"
                    self.snapshot.topics = keyword_fallback_topics(active)
                    rec.status = "degraded"
                else:
                    rec.summary = f"模型归纳 {len(self.snapshot.topics)} 个主题"
            else:
                self.snapshot.topics = keyword_fallback_topics(active)
                rec.status = "degraded"
                rec.summary = "降级模式：规则关键词主题（非语义）"
            self.emit("stage.output", {
                "topics": [t.model_dump() for t in self.snapshot.topics],
                "review_count": len(active)})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"
