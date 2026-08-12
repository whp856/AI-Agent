"""JSON/CSV 评论数据导入。缺 review_id 时生成稳定哈希 ID 并如实标注。"""
import csv
import hashlib
import io
import json

from ..models import Review


def _norm(r: dict) -> Review:
    try:
        rating = int(r.get("rating", 3) or 3)
    except (TypeError, ValueError):
        rating = 3
    rating = max(1, min(5, rating))
    rid = str(r.get("review_id", "") or "").strip()
    if not rid:
        rid = "generated:" + hashlib.md5(
            f"{r.get('author', '')}|{r.get('body', '')}|{r.get('rating', '')}".encode()
        ).hexdigest()[:12]
    return Review(
        review_id=rid,
        title=str(r.get("title", "") or ""),
        body=str(r.get("body", "") or ""),
        rating=rating,
        author=str(r.get("author", "") or ""),
        version=str(r.get("version", "") or "") or None,
        updated=str(r.get("updated", "") or ""),
        source="import",
    )


def parse_json_data(text: str) -> tuple[list[Review], str]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("reviews", data.get("entries", []))
    if not isinstance(data, list):
        raise ValueError("JSON 顶层应为数组或含 reviews/entries 数组的对象")
    rows = [d for d in data if isinstance(d, dict) and (d.get("body") or d.get("title"))]
    return [_norm(r) for r in rows], f"JSON 导入 {len(rows)} 条"


def parse_csv_data(text: str) -> tuple[list[Review], str]:
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return [_norm(r) for r in rows], f"CSV 导入 {len(rows)} 条"


async def import_file(file) -> tuple[list[Review], str]:
    content = (await file.read()).decode("utf-8", errors="replace")
    if file.filename and file.filename.lower().endswith(".csv"):
        return parse_csv_data(content)
    return parse_json_data(content)
