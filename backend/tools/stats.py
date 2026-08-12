"""确定性统计指标：不经过模型，保证可复现。"""
from collections import Counter

from ..models import Review, TopicCluster


def rating_distribution(reviews: list[Review]) -> dict:
    n = max(len(reviews), 1)
    low = sum(1 for r in reviews if r.rating <= 2)
    mid = sum(1 for r in reviews if r.rating == 3)
    high = sum(1 for r in reviews if r.rating >= 4)
    return {
        "total": len(reviews), "low": low, "mid": mid, "high": high,
        "low_ratio": round(low / n, 2),
        "avg_rating": round(sum(r.rating for r in reviews) / n, 2),
    }


def version_stats(reviews: list[Review]) -> dict:
    c = Counter((r.version or "unknown") for r in reviews)
    return dict(c.most_common(10))


def topic_stats(topics: list[TopicCluster], reviews: list[Review]) -> list[dict]:
    by_id = {r.review_id: r for r in reviews}
    out = []
    for t in topics:
        members = [by_id[m] for m in t.member_ids if m in by_id]
        if not members:
            continue
        n = len(members)
        low = sum(1 for m in members if m.rating <= 2)
        langs: dict[str, int] = {}
        versions: dict[str, int] = {}
        for m in members:
            langs[m.language or "unknown"] = langs.get(m.language or "unknown", 0) + 1
            v = m.version or "unknown"
            versions[v] = versions.get(v, 0) + 1
        out.append({
            "topic_id": t.topic_id, "topic_name": t.topic_name,
            "member_ids": [m.review_id for m in members],
            "count": n,
            "ratio": round(n / max(len(reviews), 1), 2),
            "avg_rating": round(sum(m.rating for m in members) / n, 2),
            "low_ratio": round(low / n, 2),
            "languages": langs, "versions": versions,
        })
    return out
