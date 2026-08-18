"""API 层测试：SSE 挂起、run_id 唯一性、重启后快照恢复。不依赖网络与真实 API key。"""
import json

from fastapi.testclient import TestClient

from backend import main
from backend.main import app

client = TestClient(app)


def _reset_memory_state():
    main._events.clear()
    main._active.clear()


def test_analyze_returns_unique_run_ids():
    _reset_memory_state()
    r1 = client.post("/api/analyze", json={"use_cache_only": True, "app_id": "839285684"})
    r2 = client.post("/api/analyze", json={"use_cache_only": True, "app_id": "839285684"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["run_id"] != r2.json()["run_id"]


def test_analyze_rejects_bad_url():
    _reset_memory_state()
    r = client.post("/api/analyze", json={"url": "https://example.com/not-appstore"})
    assert r.status_code == 400
    assert "apps.apple.com" in r.json()["detail"]


def test_status_unknown_run_ends_immediately():
    """无效 run_id：SSE 必须立即结束，不能无限挂起。"""
    _reset_memory_state()
    with client.stream("GET", "/api/status/run_does_not_exist") as resp:
        assert resp.status_code == 200
        body = resp.read().decode()
    assert "run.notfound" in body
    assert "sse.end" in body


def test_status_restores_completed_run_after_restart():
    """模拟服务器重启：内存无该 run 但磁盘有快照 → 直接返回完成事件。"""
    from backend.models import RunSnapshot
    from backend.run_manager import save_snapshot

    _reset_memory_state()
    run_id = "restore_test_123"
    snap = RunSnapshot(run_id=run_id, status="done")
    save_snapshot(snap)
    try:
        with client.stream("GET", f"/api/status/{run_id}") as resp:
            body = resp.read().decode()
    finally:
        from pathlib import Path
        from backend.run_manager import RUNS_DIR
        (RUNS_DIR / f"{run_id}.json").unlink(missing_ok=True)
    assert "run.complete" in body
    assert "sse.end" in body
