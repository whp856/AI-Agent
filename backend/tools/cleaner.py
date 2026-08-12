import hashlib
import html
import re

from ..models import Review

_WS = re.compile(r"\s+")

# Unicode 区间启发式语言检测（规则实现）
_LANG_RANGES = [
    ("zh", [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)]),
    ("ja", [(0x3040, 0x30FF)]),
    ("ko", [(0xAC00, 0xD7AF)]),
    ("ru", [(0x0400, 0x04FF)]),
    ("ar", [(0x0600, 0x06FF)]),
    ("el", [(0x0370, 0x03FF)]),
    ("th", [(0x0E00, 0x0E7F)]),
    ("he", [(0x0590, 0x05FF)]),
    ("hi", [(0x0900, 0x097F)]),
]

# 西语/葡萄牙语特有的重音与标点（ñ á é í ó ú ü ¿ ¡ ç），命中 >=2 判定为 es
_ES_CHARS = "ñáéíóúüÑÁÉÍÓÚÜ¿¡ç"


def detect_language(text: str) -> str | None:
    """启发式语言检测：Unicode 区间 + 拉丁字母兜底。混合/少见语言返回 unknown。"""
    if not text or not text.strip():
        return "unknown"
    scores = {lang: 0 for lang, _ in _LANG_RANGES}
    for ch in text:
        cp = ord(ch)
        for lang, ranges in _LANG_RANGES:
            for lo, hi in ranges:
                if lo <= cp <= hi:
                    scores[lang] += 1
    if any(v > 0 for v in scores.values()):
        top = max(scores, key=scores.get)
        return top if scores[top] >= 2 else "unknown"
    es_hits = sum(1 for ch in text if ch in _ES_CHARS)
    if es_hits >= 2:
        return "es"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return "unknown"


def clean_reviews(reviews: list[Review]) -> tuple[list[Review], list[dict]]:
    """清洗 + 去重 + 语言检测。全确定性规则。返回（清洗后列表, 清洗日志）。"""
    log: list[dict] = []
    out: list[Review] = []
    seen: dict[str, str] = {}  # dedup_key -> 首个 review_id
    for r in reviews:
        body = html.unescape(r.body or "")
        body = _WS.sub(" ", body).strip()
        if not body:
            log.append({"step": "empty_filter", "count": 1, "note": r.review_id})
            continue
        title = _WS.sub(" ", html.unescape(r.title or "")).strip()
        lang = detect_language(body)
        try:
            rating = int(r.rating)
        except (TypeError, ValueError):
            rating = 3
        rating = max(1, min(5, rating))
        key = hashlib.md5(f"{r.author}|{body}|{rating}".encode()).hexdigest()
        if key in seen:
            for o in out:
                if o.dedup_key == key:
                    o.original_ids.append(r.review_id)
                    break
            log.append({"step": "dedup", "count": 1, "note": f"{r.review_id}->{seen[key]}"})
            r2 = r.model_copy(deep=True)
            r2.is_duplicate = True
            r2.dedup_key = key
            r2.body_cleaned = body
            out.append(r2)
            continue
        seen[key] = r.review_id
        r.body_cleaned = body
        r.title = title
        r.language = lang
        r.dedup_key = key
        r.rating = rating
        out.append(r)
    return out, log
