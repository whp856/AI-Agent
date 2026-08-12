import json
import re
import time
import uuid
from pathlib import Path

import httpx

from ..models import Review

APP_ID_RE = re.compile(r"id(\d{5,10})")
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"


def parse_appstore_url(url: str) -> dict:
    """从 App Store 链接解析 appId 与地区。规则实现，不经过模型。"""
    if "apps.apple.com" not in url:
        raise ValueError("仅支持 apps.apple.com 链接")
    m = APP_ID_RE.search(url)
    if not m:
        raise ValueError("链接中未找到 appId")
    country = "us"
    cm = re.search(r"apps\.apple\.com/([a-z]{2})/", url)
    if cm:
        country = cm.group(1)
    return {"app_id": m.group(1), "country": country}


def _entry_to_review(e: dict) -> Review:
    rid = e.get("id", {}).get("label", "") if isinstance(e.get("id"), dict) else e.get("id", "")
    rid = str(rid).split("?")[0] or uuid.uuid4().hex
    try:
        rating = int(e.get("im:rating", {}).get("label", "0") or 0)
    except (TypeError, ValueError):
        rating = 0
    title = e.get("title", {}).get("label", "") if isinstance(e.get("title"), dict) else e.get("title", "")
    content = e.get("content", {}).get("label", "") if isinstance(e.get("content"), dict) else e.get("content", "")
    author = e.get("author", {}).get("name", {}).get("label", "")
    version = e.get("im:version", {}).get("label", "") if isinstance(e.get("im:version"), dict) else e.get("im:version", "")
    updated = e.get("updated", {}).get("label", "") if isinstance(e.get("updated"), dict) else e.get("updated", "")
    return Review(
        review_id=rid, title=str(title), body=str(content),
        rating=max(1, min(5, rating)) if rating else 3,
        author=str(author), version=str(version) or None,
        updated=str(updated), source="rss",
    )


def fetch_reviews(app_id: str, max_pages: int = 5, rate_limit: float = 2.0,
                  client: httpx.Client | None = None) -> list[Review]:
    """iTunes 官方 RSS 评论接口采集。限速、分页、失败即停。"""
    own_client = client is None
    client = client or httpx.Client(
        timeout=15, headers={"User-Agent": "ReviewAnalyzer/1.0 (educational analysis)"},
    )
    reviews: list[Review] = []
    seen: set[str] = set()
    try:
        for page in range(1, max_pages + 1):
            url = f"https://itunes.apple.com/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except Exception:
                break  # 网络失败/页面不存在 → 停止分页
            try:
                data = resp.json()
            except ValueError:
                break
            entries = data.get("feed", {}).get("entry", [])
            if isinstance(entries, dict):  # 单条时 API 返回 dict
                entries = [entries]
            if not entries:
                break
            new = 0
            for e in entries:
                if not isinstance(e, dict):
                    continue
                rev = _entry_to_review(e)
                if rev.review_id in seen:
                    continue
                seen.add(rev.review_id)
                reviews.append(rev)
                new += 1
            if new == 0:
                break
            if rate_limit > 0:
                time.sleep(rate_limit)
    finally:
        if own_client and client:
            client.close()
    return reviews


def cache_path(app_id: str) -> Path:
    return CACHE_DIR / f"{app_id}.json"


def load_cache(app_id: str) -> list[Review] | None:
    p = cache_path(app_id)
    if p.exists():
        try:
            return [Review(**r) for r in json.loads(p.read_text(encoding="utf-8"))]
        except Exception:
            return None
    return None


def save_cache(app_id: str, reviews: list[Review]) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path(app_id)
    p.write_text(
        json.dumps([r.model_dump() for r in reviews], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return str(p)
