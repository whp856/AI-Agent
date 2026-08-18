import json
from pathlib import Path

from .models import RunSnapshot

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
MAX_KEEP = 50  # 快照保留上限，防止无限累积


def save_snapshot(snap: RunSnapshot) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = RUNS_DIR / f"{snap.run_id}.json"
    p.write_text(json.dumps(snap.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    _prune_old_snapshots()
    return str(p)


def _prune_old_snapshots():
    """按修改时间保留最近 MAX_KEEP 个快照。"""
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[MAX_KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass


def load_snapshot(run_id: str) -> RunSnapshot | None:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        return None
    try:
        return RunSnapshot(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None
