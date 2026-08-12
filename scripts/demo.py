"""无网络演示：使用内置真实样例数据跑通全流程。

用法:  python -m scripts.demo [--json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.llm.client import LLMClient
from backend.models import AnalyzeRequest, Review
from backend.workflow.orchestrator import Orchestrator

SAMPLE_CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "839285684.json"


def main():
    settings = get_settings()
    llm = LLMClient(settings)
    reviews = []
    note = ""
    if SAMPLE_CACHE.exists():
        reviews = [Review(**r) for r in json.loads(SAMPLE_CACHE.read_text(encoding="utf-8"))]
        note = f"使用内置样例缓存（{len(reviews)} 条真实评论）"
    else:
        note = "未找到样例缓存，以空数据运行"
    print(f"[demo] {note}")
    print(f"[demo] LLM 模式: {llm.mode}")

    orch = Orchestrator(llm, settings)
    snap = orch.execute(
        AnalyzeRequest(goal="重点关注订阅转化与训练易用性",
                       constraints=["低分评论优先"]),
        reviews=reviews or None)

    print(f"\n===== 运行结果: status={snap.status} mode={snap.meta.get('model_mode')} =====")
    print(f"数据来源: {snap.meta.get('collect_note', '')}")
    print(f"评论 {len(snap.reviews)} 条 | 主题 {len(snap.topics)} 个 | "
          f"结论 {len(snap.findings)} 条 | 需求 {len(snap.requirements)} 条 | "
          f"用例 {len(snap.test_cases)} 条")
    print(f"校验: {'通过' if snap.validation_report.get('passed') else '存在未决问题'}"
          f" | 修正 {len(snap.corrections)} 项")
    for s in snap.stages:
        if s.status != "pending":
            print(f"  [{s.status:8s}] {s.name} - {s.summary}")
    if snap.requirements:
        print("\n----- PRD 需求 -----")
        for r in snap.requirements:
            print(f"  {r.req_id} [{r.priority}] {r.title} -> {r.version}  证据: {r.evidence_refs[:3]}")
    if snap.test_cases:
        print("\n----- 测试用例 -----")
        for c in snap.test_cases[:5]:
            print(f"  {c.case_id} {c.title} 关联 {c.req_refs} 评论 {c.review_refs[:3]}")
    if "--json" in sys.argv:
        from backend.run_manager import RUNS_DIR
        out = RUNS_DIR / f"{snap.run_id}.json"
        print(f"\n完整快照: {out}")


if __name__ == "__main__":
    main()
