from backend.models import Review
from backend.tools.cleaner import clean_reviews, detect_language


def _rev(rid, body, rating=4):
    return Review(review_id=rid, body=body, rating=rating, author="a")


def test_html_decode_and_norm():
    out, log = clean_reviews([_rev("1", "Great&amp; nice  app\n\nExtra")])
    assert out[0].body_cleaned == "Great& nice app Extra"
    assert "&" in out[0].body_cleaned


def test_dedup_keeps_first():
    out, log = clean_reviews([_rev("1", "same text"), _rev("2", "same text")])
    active = [r for r in out if not r.is_duplicate]
    dup = [r for r in out if r.is_duplicate]
    assert len(active) == 1
    assert len(dup) == 1
    assert dup[0].original_ids == []


def test_original_ids_merge_on_primary():
    # 第三条与前两条同文本，合并进主记录
    out, log = clean_reviews([_rev("1", "dup text"), _rev("2", "dup text")])
    for o in out:
        if o.review_id == "1":
            assert "2" in o.original_ids


def test_empty_body_filtered():
    out, log = clean_reviews([_rev("1", "   ")])
    assert len(out) == 0
    assert any(x["step"] == "empty_filter" for x in log)


def test_language_detection():
    assert detect_language("这款应用很好用") == "zh"
    assert detect_language("This app is great") == "en"
    assert detect_language("Прекрасное приложение") == "ru"
    assert detect_language("") == "unknown"


def test_rating_clamped():
    r = _rev("1", "hello", rating=5)
    r.rating = 9  # Pydantic v2 默认不校验赋值，模拟脏数据
    out, log = clean_reviews([r])
    assert out[0].rating == 5
