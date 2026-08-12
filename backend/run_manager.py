import json
from pathlib import Path

from .models import RunSnapshot

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


def save_snapshot(snap: RunSnapshot) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = RUNS_DIR / f"{snap.run_id}.json"
    p.write_text(json.dumps(snap.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)


def load_snapshot(run_id: str) -> RunSnapshot | None:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        return None
    try:
        return RunSnapshot(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None
