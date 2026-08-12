import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .llm.client import LLMClient
from .models import AnalyzeRequest
from .run_manager import RUNS_DIR, load_snapshot
from .workflow.orchestrator import Orchestrator

app = FastAPI(title="App Store Review Analyzer")

_settings = get_settings()
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient(_settings)
    return _llm


# 运行态：run_id -> 事件缓冲 / 完成标记
_events: dict[str, list[dict]] = {}
_active: dict[str, dict] = {}


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": get_llm().mode}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    from .tools.collector import parse_appstore_url
    if not req.url and not req.use_cache_only:
        raise HTTPException(400, "请输入 App Store 链接")
    if req.url:
        try:
            info = parse_appstore_url(req.url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        req.app_id = info["app_id"]
    run_id = _start(req)
    return {"run_id": run_id}


def _start(req: AnalyzeRequest) -> str:
    run_id = f"run_{len(_events) + 1}"
    _events[run_id] = []
    _active[run_id] = {"done": False}

    def worker():
        try:
            orch = Orchestrator(get_llm(), _settings,
                                on_event=lambda e: _events[run_id].append(e))
            snap = orch.execute(req, run_id=run_id)
            _events[run_id].append({
                "type": "run.complete", "run_id": run_id,
                "data": {"status": snap.status, "run_id": snap.run_id},
            })
        except Exception as e:  # 兜底：线程内任何异常都要通知前端
            _events[run_id].append({"type": "run.failed", "run_id": run_id,
                                    "data": {"error": str(e)}})
        finally:
            _active[run_id]["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return run_id


@app.get("/api/status/{run_id}")
async def status(run_id: str):
    async def gen():
        idx = 0
        while True:
            evs = _events.get(run_id, [])
            while idx < len(evs):
                e = evs[idx]
                idx += 1
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if _active.get(run_id, {}).get("done"):
                yield "data: {\"type\":\"sse.end\"}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/results/{run_id}")
def results(run_id: str):
    snap = load_snapshot(run_id)
    if not snap:
        raise HTTPException(404, "run not found")
    return JSONResponse(snap.model_dump())


@app.get("/api/runs")
def list_runs():
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    return [{"run_id": p.stem} for p in files]


@app.post("/api/import")
async def import_data(file: UploadFile):
    from .tools.importer import import_file
    reviews, note = await import_file(file)
    return {"count": len(reviews), "note": note,
            "preview": [r.model_dump() for r in reviews[:5]]}


@app.post("/api/analyze-import")
async def analyze_import(file: UploadFile, goal: str = "", constraints: str = ""):
    """上传文件后直接以导入数据启动完整工作流。"""
    from .tools.importer import import_file
    reviews, note = await import_file(file)
    if not reviews:
        raise HTTPException(400, "导入数据为空")
    req = AnalyzeRequest(goal=goal,
                         constraints=[c for c in constraints.split(",") if c.strip()])
    run_id = _start_imported(req, reviews)
    return {"run_id": run_id, "note": note, "count": len(reviews)}


def _start_imported(req: AnalyzeRequest, reviews) -> str:
    run_id = f"run_{len(_events) + 1}"
    _events[run_id] = []
    _active[run_id] = {"done": False}

    def worker():
        try:
            orch = Orchestrator(get_llm(), _settings,
                                on_event=lambda e: _events[run_id].append(e))
            snap = orch.execute(req, reviews=reviews, run_id=run_id)
            _events[run_id].append({"type": "run.complete", "run_id": run_id,
                                    "data": {"status": snap.status, "run_id": snap.run_id}})
        except Exception as e:
            _events[run_id].append({"type": "run.failed", "run_id": run_id,
                                    "data": {"error": str(e)}})
        finally:
            _active[run_id]["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return run_id


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
