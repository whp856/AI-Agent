"""Agent 工作流编排器：8 阶段流水线 + 状态机 + 事件发布 + 快照持久化。"""
import uuid
from datetime import datetime

from ..config import get_settings
from ..models import AnalyzeRequest, RunSnapshot, StageRecord
from ..tools import cleaner
from ..tools.collector import fetch_reviews, load_cache, save_cache
from .s0_plan import S0Plan
from .s3_classify import S3Classify
from .s4_findings import S4Findings
from .s5_prd import S5PRD
from .s6_testcases import S6Testcases
from .s7_validate import S7Validate


class Orchestrator:
    def __init__(self, llm=None, settings=None, on_event=None):
        self.llm = llm
        self.settings = settings or get_settings()
        self.on_event = on_event or (lambda e: None)
        self._collect_note = ""

    def execute(self, request: AnalyzeRequest, reviews=None, on_event=None,
                run_id: str | None = None) -> RunSnapshot:
        if on_event:
            self.on_event = on_event
        snap = RunSnapshot(
            run_id=run_id or uuid.uuid4().hex[:12],
            request=request,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        for name in ("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"):
            snap.stages.append(StageRecord(name=name))
        self._event(snap, "run.started")
        model_mode = "llm" if (self.llm and getattr(self.llm, "available", False)) else "degraded"
        snap.meta["model_mode"] = model_mode
        snap.meta["min_sample"] = self.settings.min_sample
        ctx = {"snapshot": snap, "llm": self.llm, "on_event": self.on_event,
               "model_mode": model_mode}

        try:
            S0Plan(ctx).run()
            self._collect(snap, request, reviews)
            self._clean(snap)
            S3Classify(ctx).run()
            S4Findings(ctx).run()
            S5PRD(ctx).run()
            S6Testcases(ctx).run()
            S7Validate(ctx).run()
            # 任一阶段降级/失败都必须如实反映在快照状态
            if any(s.status == "failed" for s in snap.stages):
                snap.status = "failed"
            elif any(s.status == "degraded" for s in snap.stages):
                snap.status = "degraded"
            else:
                snap.status = "done"
            snap.meta["collect_note"] = self._collect_note
        except Exception as e:
            snap.status = "failed"
            snap.meta["fatal_error"] = str(e)
            self._event(snap, "run.failed", {"error": str(e)})
        finally:
            from ..run_manager import save_snapshot
            save_snapshot(snap)
        self._event(snap, "run.finished", {"status": snap.status})
        return snap

    # ---------- 内部 ----------

    def _collect(self, snap, request, reviews=None):
        rec = self._rec(snap, "s1")
        rec.status = "running"
        if reviews:  # 导入模式
            snap.reviews = reviews
            self._collect_note = f"使用导入数据 {len(reviews)} 条"
            rec.summary = self._collect_note
        elif request.use_cache_only:
            cached = load_cache(request.app_id)
            if cached:
                snap.reviews = cached
                self._collect_note = f"缓存数据 {len(cached)} 条（仅缓存模式）"
                rec.summary = self._collect_note
            else:
                self._collect_note = "无缓存可用"
                rec.summary = self._collect_note
                rec.status = "failed"
                rec.error = "use_cache_only 但无缓存"
        else:
            try:
                fresh = fetch_reviews(request.app_id, max_pages=self.settings.collect_max_pages,
                                      rate_limit=self.settings.collect_rate_limit)
                if fresh:
                    save_cache(request.app_id, fresh)
                    snap.reviews = fresh
                    self._collect_note = f"实时采集 {len(fresh)} 条（iTunes 官方 RSS）"
                    rec.summary = self._collect_note
                else:
                    cached = load_cache(request.app_id)
                    if cached:
                        snap.reviews = cached
                        self._collect_note = f"实时采集为空，使用缓存 {len(cached)} 条"
                        rec.summary = self._collect_note
                        rec.status = "degraded"
                    else:
                        self._collect_note = "采集为空且无缓存"
                        rec.summary = self._collect_note
                        rec.status = "failed"
                        rec.error = "采集为空且无缓存"
            except Exception as e:
                cached = load_cache(request.app_id)
                if cached:
                    snap.reviews = cached
                    self._collect_note = f"采集异常（{type(e).__name__}），使用缓存 {len(cached)} 条"
                    rec.summary = self._collect_note
                    rec.status = "degraded"
                else:
                    self._collect_note = f"采集异常（{type(e).__name__}），无缓存"
                    rec.summary = self._collect_note
                    rec.status = "failed"
                    rec.error = str(e)
        snap.meta["collect_note"] = self._collect_note
        if rec.status == "running":
            rec.status = "done"
        self._event(snap, "stage.output",
                    {"stage": "s1", "note": self._collect_note, "count": len(snap.reviews)})

    def _clean(self, snap):
        rec = self._rec(snap, "s2")
        rec.status = "running"
        snap.reviews, log = cleaner.clean_reviews(snap.reviews)
        active = len([r for r in snap.reviews if not r.is_duplicate])
        dup = len([r for r in snap.reviews if r.is_duplicate])
        rec.summary = f"清洗后 {len(snap.reviews)} 条（有效 {active} / 重复 {dup}）"
        snap.meta["clean_log"] = log
        self._event(snap, "stage.output",
                    {"stage": "s2", "log": log, "total": len(snap.reviews),
                     "active": active, "duplicates": dup})
        rec.status = "done"

    def _rec(self, snap, name):
        return next(s for s in snap.stages if s.name == name)

    def _event(self, snap, etype, data=None):
        data = data or {}
        self.on_event({
            "type": etype,
            "stage": data.get("stage") or etype.split(".")[0],
            "data": data, "run_id": snap.run_id,
            "time": datetime.now().isoformat(timespec="seconds"),
        })
