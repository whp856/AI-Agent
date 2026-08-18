import pytest
import httpx

from backend.tools.collector import parse_appstore_url, fetch_reviews

JSON_BODY = """{"feed": {"entry": [
  {"id": {"label": "rid-1"}, "title": {"label": "Great app"},
   "content": {"label": "I love it!"}, "im:rating": {"label": "5"},
   "author": {"name": {"label": "Alice"}}, "updated": {"label": "2026-08-01T10:00:00-07:00"},
   "im:version": {"label": "8.4"}},
  {"id": {"label": "rid-2"}, "title": {"label": "Bad"},
   "content": {"label": "It crashed"}, "im:rating": {"label": "1"},
   "author": {"name": {"label": "Bob"}}, "updated": {"label": "2026-07-30T10:00:00-07:00"},
   "im:version": {"label": "8.4"}}
]}}"""


def test_parse_valid_url():
    info = parse_appstore_url(
        "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684")
    assert info["app_id"] == "839285684"
    assert info["country"] == "us"


def test_parse_cn_url():
    info = parse_appstore_url(
        "https://apps.apple.com/cn/app/workout-for-women-home-gym/id839285684")
    assert info["country"] == "cn"


def test_parse_invalid_url():
    with pytest.raises(ValueError):
        parse_appstore_url("https://evil.com/not-an-app")
    with pytest.raises(ValueError):
        parse_appstore_url("https://apps.apple.com/us/app/some-app-without-id")


def test_fetch_reviews_json_mock():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=JSON_BODY))
    with httpx.Client(transport=transport) as client:
        reviews = fetch_reviews("839285684", max_pages=1, rate_limit=0, client=client)
    assert len(reviews) == 2
    assert reviews[0].rating == 5
    assert reviews[0].body == "I love it!"
    assert reviews[1].rating == 1
    assert reviews[0].version == "8.4"


def test_fetch_stops_on_empty_page():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, text='{"feed": {}}')

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        reviews = fetch_reviews("1", max_pages=5, rate_limit=0, client=client)
    assert reviews == []
    assert len(calls) == 1


def test_fetch_breaks_on_http_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    with httpx.Client(transport=transport) as client:
        reviews = fetch_reviews("1", max_pages=3, rate_limit=0, client=client)
    assert reviews == []


def test_fetch_reports_http_error_reason():
    """采集失败原因必须透出到 errors 列表，不能静默吞掉。"""
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    errors = []
    with httpx.Client(transport=transport) as client:
        reviews = fetch_reviews("1", max_pages=3, rate_limit=0, client=client, errors=errors)
    assert reviews == []
    assert errors and "404" not in errors[0] and errors[0].startswith("page 1")


def test_fetch_reports_empty_feed_reason():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text='{"feed": {}}'))
    errors = []
    with httpx.Client(transport=transport) as client:
        fetch_reviews("1", max_pages=5, rate_limit=0, client=client, errors=errors)
    assert errors and "无评论条目" in errors[0]
