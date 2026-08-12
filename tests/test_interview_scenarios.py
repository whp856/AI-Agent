"""面试官测试场景验证（对应技能测试.md 重要提示 #7）。

场景覆盖：
1. 全新链接/全新应用（无硬编码，动态分析）
2. 多语言评论（中/英/日/西语混合）
3. 重复评论 / 矛盾评论
4. 样本不足（少量评论 → assumption 降级）
5. 模型调用故障（LLM 返回 None → 规则兜底 + 如实标注）
6. JSON/CSV 导入
7. 全新分析目标（不绑定特定目标）
"""
import json
import pytest

from backend.models import AnalyzeRequest, Review
from backend.llm.client import FakeLLM
from backend.workflow.orchestrator import Orchestrator


def _reviews_from_bodies(bodies, ratings=None, start=0, lang_hint=None):
    revs = []
    for i, b in enumerate(bodies):
        revs.append(Review(review_id=f"r{start + i}", body=b,
                           rating=(ratings[i] if ratings else 3),
                           author=f"a{start + i}", source="import"))
    return revs


# ---------- 场景 1：全新应用（不同数据，模型动态归纳，不依赖任何预设） ----------

def test_new_app_generic_analysis_no_hardcoding():
    """全新应用数据：LLM 动态分类，产出必须有证据引用，无硬编码痕迹。"""
    bodies = [
        "the meditation timer stops randomly", "session history lost after update",
        "背景音乐无法更换", "premium price too high for monthly",
        "love the breathing exercises", "great app overall",
        "timer freezes during session", "audio quality is poor",
    ]
    reviews = _reviews_from_bodies(bodies, ratings=[1, 1, 2, 2, 5, 5, 1, 3])
    # 响应主题完全由模型"自拟"（测试数据是冥想应用，与示例健身应用完全不同领域）
    llm = FakeLLM([
        {"focus_areas": ["计时器稳定性", "内容价格"], "constraints": [],
         "analysis_plan": "聚焦计时器与订阅"},
        {"topics": [
            {"topic_id": "T1", "topic_name": "计时器冻结问题", "description": "d",
             "member_ids": ["r0", "r6", "r7"], "evidence": ["timer freezes during session"],
             "opposing_feedback": [], "confidence": "high", "confidence_reason": "n=3"}]},
        {"topics": [
            {"topic_id": "T1", "topic_name": "计时器冻结问题", "member_ids": ["r0", "r6", "r7"],
             "evidence": ["timer freezes"], "opposing_feedback": [],
             "confidence": "high", "confidence_reason": "n=3"}],
         "merge_log": []},
        {"findings": [
            {"kind": "model_derived", "statement": "计时器冻结是高频问题",
             "supporting_review_ids": ["r0", "r6"], "confidence": "high",
             "uncertainty": "n=2", "conflicting_evidence": [], "topic_refs": ["T1"]}]},
        {"requirements": [
            {"req_id": "PRD-1", "title": "修复计时器冻结", "description": "d",
             "priority": "P0", "version": "v8.1", "rationale": "r",
             "evidence_refs": ["F-T1-s", "r0", "r6"], "acceptance_criteria": ["c"]}]},
        {"test_cases": [
            {"case_id": "TC-1", "title": "计时器运行 30 分钟不冻结", "preconditions": "p",
             "steps": ["s"], "expected_results": ["e"], "req_refs": ["PRD-1"]}]},
    ])
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(goal="计时器稳定性"), reviews=reviews)
    assert snap.status == "done"
    assert any("计时器" in t.topic_name for t in snap.topics)
    assert any(r.req_id == "PRD-1" for r in snap.requirements)
    # 关键：所有引用必须真实存在（无硬编码/无虚构）
    valid_ids = {r.review_id for r in snap.reviews}
    for f in snap.findings:
        assert set(f.supporting_review_ids) <= valid_ids
    for r in snap.requirements:
        assert any(x in {f.finding_id for f in snap.findings} for x in r.evidence_refs)


# ---------- 场景 2：多语言评论 ----------

def test_multilingual_reviews_classified_together():
    """中/英/日/西语描述同一问题（订阅扣款），模型归入同一主题。"""
    bodies = [
        "subscription charged twice and no refund",   # en
        "订阅扣了两次钱，退款没反应",                    # zh
        "サブスクリプションが二重請求された",            # ja
        "me cobraron dos veces, ¡qué estafa!",       # es
        "the app crashes on startup",                # en 其它问题
    ]
    reviews = _reviews_from_bodies(bodies, ratings=[1, 1, 1, 1, 1])
    llm = FakeLLM([
        {"focus_areas": [], "constraints": [], "analysis_plan": "通用"},
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅重复扣款", "description": "d",
             "member_ids": ["r0", "r1", "r2", "r3"],
             "evidence": ["subscription charged twice", "订阅扣了两次钱",
                          "二重請求された", "cobraron dos veces"],
             "opposing_feedback": [], "confidence": "high", "confidence_reason": "n=4"}]},
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅重复扣款", "member_ids": ["r0", "r1", "r2", "r3"],
             "evidence": [], "opposing_feedback": [], "confidence": "high",
             "confidence_reason": "n=4"}],
         "merge_log": []},
        {"findings": []},
        {"requirements": [
            {"req_id": "PRD-1", "title": "修复订阅重复扣款", "description": "d",
             "priority": "P0", "version": "v8.1", "rationale": "r",
             "evidence_refs": ["F-T1-s", "r0", "r1", "r2", "r3"],
             "acceptance_criteria": ["c"]}]},
        {"test_cases": [
            {"case_id": "TC-1", "title": "订阅只扣款一次", "preconditions": "p",
             "steps": ["s"], "expected_results": ["e"], "req_refs": ["PRD-1"]}]},
    ])
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(), reviews=reviews)
    assert snap.status == "done"
    # 语言检测正确
    langs = {r.review_id: r.language for r in snap.reviews}
    assert langs["r0"] == "en" and langs["r1"] == "zh" and langs["r2"] == "ja"
    assert langs["r3"] == "es"
    # 4 种语言同一问题归入同一主题（member_ids 完整）
    assert len(snap.topics) >= 1
    assert snap.topics[0].member_ids == ["r0", "r1", "r2", "r3"]


# ---------- 场景 3：重复评论 / 矛盾评论 ----------

def test_duplicate_reviews_deduped():
    """完全重复的评论被规则去重，近似重复由模型合并引用。"""
    revs = [
        Review(review_id="a", body="app crashes on launch", rating=1, author="u1", source="import"),
        Review(review_id="b", body="app crashes on launch", rating=1, author="u1", source="import"),
    ]
    orch = Orchestrator(llm=None)  # 去重是确定性规则，与模型无关
    snap = orch.execute(AnalyzeRequest(), reviews=revs)
    dup = [r for r in snap.reviews if r.is_duplicate]
    assert len(dup) == 1
    assert dup[0].review_id == "b"


def test_conflicting_feedback_surfaced():
    """矛盾评论：结论必须带 opposing/conflicting 证据（模型输出契约强制）。"""
    bodies = ["subscription is a scam, charged twice", "subscription is fair and good value"]
    reviews = _reviews_from_bodies(bodies, ratings=[1, 5])
    llm = FakeLLM([
        {"focus_areas": [], "constraints": [], "analysis_plan": "通用"},
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅体验", "member_ids": ["r0", "r1"],
             "evidence": ["charged twice"], "opposing_feedback": ["subscription is fair and good value"],
             "confidence": "medium", "confidence_reason": "存在对立意见"}]},
        {"topics": [{"topic_id": "T1", "topic_name": "订阅体验", "member_ids": ["r0", "r1"],
                     "evidence": [], "opposing_feedback": ["fair and good value"],
                     "confidence": "medium", "confidence_reason": "存在对立意见"}],
         "merge_log": []},
        {"findings": [
            {"kind": "model_derived", "statement": "订阅存在负面评价但亦有正面反馈",
             "supporting_review_ids": ["r0", "r1"], "confidence": "medium",
             "uncertainty": "n=2 且存在对立意见",
             "conflicting_evidence": ["subscription is fair and good value"],
             "topic_refs": ["T1"]}]},
        {"requirements": [], "risks_and_assumptions": "样本少"},
        {"test_cases": []},
    ])
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(), reviews=reviews)
    # 主题必须保留对立反馈（不搞单一叙事）
    assert snap.topics[0].opposing_feedback != []
    # 推导结论必须带矛盾证据
    derived = [f for f in snap.findings if f.kind == "model_derived"]
    assert derived and derived[0].conflicting_evidence != []


# ---------- 场景 4：样本不足 ----------

def test_insufficient_sample_downgraded_to_assumption():
    """样本不足：统计结论自动降级为 assumption，且不进入 PRD。"""
    bodies = ["one complaint about pricing", "fine app", "works ok"]
    reviews = _reviews_from_bodies(bodies, ratings=[1, 4, 4])
    orch = Orchestrator(llm=None)  # 统计路径即可验证降级规则
    snap = orch.execute(AnalyzeRequest(), reviews=reviews)
    assert snap.status in ("done", "degraded")
    # 样本 < MIN_SAMPLE(3) 的主题（若形成）→ assumption
    for f in snap.findings:
        if f.kind == "assumption":
            assert "不足" in f.statement or f.uncertainty
    # 校验报告必须列出 assumption
    assert "assumption_findings" in snap.validation_report


# ---------- 场景 5：模型调用故障 ----------

def test_model_failure_falls_back_and_marks_degraded():
    """模型配置了但全部调用失败（返回 None）：自动规则兜底，快照如实标注降级。"""
    reviews = _reviews_from_bodies(["crash on launch", "battery drain", "nice app"], [1, 1, 5])
    llm = FakeLLM([])  # 模拟模型调用全部失败
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(), reviews=reviews)
    assert snap.status == "degraded"
    assert snap.meta["model_mode"] == "llm"  # 已配置模型，但执行降级
    # 降级产出必须标记
    for t in snap.topics:
        assert "degraded" in (t.confidence_reason or "")
    # 无模型时也必须有校验报告（流程不崩）
    assert snap.validation_report


# ---------- 场景 6：全新分析目标 ----------

def test_fresh_goal_accepted_without_binding():
    """任意分析目标（不绑定示例目标）：目标被解析并注入后续阶段。"""
    bodies = ["first workout too hard", "love the beginner plan", "rest day missing"]
    reviews = _reviews_from_bodies(bodies)
    llm = FakeLLM([
        {"focus_areas": ["新手引导"], "constraints": [{"type": "other", "value": "新手友好"}],
         "analysis_plan": "聚焦新手首次体验"},
        {"topics": [
            {"topic_id": "T1", "topic_name": "新手难度", "member_ids": ["r0"],
             "evidence": ["too hard"], "opposing_feedback": [],
             "confidence": "low", "confidence_reason": "n=1"}]},
        {"topics": [{"topic_id": "T1", "topic_name": "新手难度", "member_ids": ["r0"],
                     "evidence": [], "opposing_feedback": [], "confidence": "low",
                     "confidence_reason": "n=1"}],
         "merge_log": []},
        {"findings": []},
        {"requirements": []},
        {"test_cases": []},
    ])
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(goal="新手引导优化", constraints=["新手友好"]),
                        reviews=reviews)
    assert snap.plan.focus_areas == ["新手引导"]
    assert snap.request.goal == "新手引导优化"


# ---------- 场景 7：JSON/CSV 导入 ----------

def test_json_import_roundtrip():
    from backend.tools.importer import parse_json_data
    data = [{"review_id": "x1", "body": "hello", "rating": 4}]
    reviews, note = parse_json_data(json.dumps(data))
    assert reviews[0].review_id == "x1"
    assert "JSON" in note


def test_csv_import_roundtrip():
    from backend.tools.importer import parse_csv_data
    csv_text = "review_id,title,body,rating\n1,t,hello,3\n2,t,world,5\n"
    reviews, note = parse_csv_data(csv_text)
    assert len(reviews) == 2
    assert reviews[1].rating == 5


def test_import_missing_id_generated():
    from backend.tools.importer import parse_json_data
    reviews, note = parse_json_data(json.dumps([{"body": "hi", "rating": 4}]))
    assert reviews[0].review_id.startswith("generated:")
