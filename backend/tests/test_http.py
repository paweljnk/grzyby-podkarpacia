import httpx
import pytest

from grzyby.etl.http import HttpClient, SourceUnavailable


def make_client(tmp_path, handler, **kw):
    sleeps = []
    c = HttpClient(cache_dir=tmp_path, min_interval_s=0, sleep=sleeps.append,
                   transport=httpx.MockTransport(handler), **kw)
    return c, sleeps


def test_retry_with_exponential_backoff_then_success(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    c, sleeps = make_client(tmp_path, handler, backoff_base_s=1.0)
    assert c.get("https://x.test/a").json() == {"ok": True}
    assert len(calls) == 3
    # opóźnienia rosną wykładniczo (z losowym rozrzutem ±20%)
    assert 0.8 <= sleeps[0] <= 1.2 and 1.6 <= sleeps[1] <= 2.4


def test_retry_after_header_respected(tmp_path):
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"}) if len(n) == 1 else httpx.Response(200, text="x")

    c, sleeps = make_client(tmp_path, handler)
    c.get("https://x.test/b")
    assert sleeps == [7.0]


def test_denied_is_not_retried(tmp_path):
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(403)

    c, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceUnavailable):
        c.get("https://x.test/c")
    assert len(n) == 1


def test_gives_up_after_max_retries(tmp_path):
    c, sleeps = make_client(tmp_path, lambda r: httpx.Response(500), max_retries=2)
    with pytest.raises(SourceUnavailable):
        c.get("https://x.test/d")
    assert len(sleeps) == 2


def test_cache_hit_avoids_second_request(tmp_path):
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(200, json={"v": len(n)})

    c, _ = make_client(tmp_path, handler)
    a = c.get("https://x.test/e", params={"q": 1})
    b = c.get("https://x.test/e", params={"q": 1})
    assert a.json() == b.json() == {"v": 1} and b.from_cache and len(n) == 1
    assert c.get("https://x.test/e", params={"q": 2}).json() == {"v": 2}
