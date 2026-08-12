import json
from pathlib import Path

from .stage_base import StageBase
from ..models import AnalysisPlan

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


class S0Plan(StageBase):
    name = "s0"

    def run(self):
        rec = self.stage("s0")
        rec.status = "running"
        try:
            if self.mode == "degraded" or not self.llm.available:
                self.snapshot.plan = AnalysisPlan(degraded=True)
                rec.status = "degraded"
                rec.summary = "无模型可用，使用默认分析计划"
                self.emit("stage.output", {"plan": self.snapshot.plan.model_dump()})
                return
            system = "你是产品分析系统的规划模块。将分析目标解析为结构化计划。只输出 JSON。"
            user = (PROMPT_DIR / "s0.txt").read_text(encoding="utf-8").format(
                analysis_goal=self.snapshot.request.goal or "(未指定，使用通用分析)",
                constraints=json.dumps(self.snapshot.request.constraints, ensure_ascii=False),
            )
            data = self.llm.chat_json(system, user, {})
            if data:
                self.snapshot.plan = AnalysisPlan(
                    focus_areas=data.get("focus_areas", []),
                    constraints=data.get("constraints", []),
                    analysis_plan=data.get("analysis_plan", ""),
                )
                rec.model_used = self.llm.mode
                rec.summary = f"计划: {self.snapshot.plan.analysis_plan or '通用分析'}"
            else:
                self.snapshot.plan = AnalysisPlan(degraded=True)
                rec.status = "degraded"
                rec.summary = "模型未返回计划，使用默认计划"
            self.emit("stage.output", {"plan": self.snapshot.plan.model_dump()})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"
