import httpx

from weather_layers.http import HttpClient, HttpError


def test_user_agent_retry_after_and_cache(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, content=b"payload")

    sleeps = []
    c = HttpClient(
        "test-agent/1.0 (+contact)",
        transport=httpx.MockTransport(handler),
        cache_dir=tmp_path,
        sleep=sleeps.append,
    )
    r = c.get("https://example.test/data", cache=True)
    assert r.content == b"payload"
    assert all(req.headers["User-Agent"] == "test-agent/1.0 (+contact)" for req in calls)
    assert len(calls) == 3
    assert sleeps[0] >= 7.0  # honours Retry-After
    # cached: no further network calls
    r2 = c.get("https://example.test/data", cache=True)
    assert r2.from_cache and r2.content == b"payload" and len(calls) == 3


def test_gives_up_after_max_retries():
    c = HttpClient(
        "t",
        transport=httpx.MockTransport(lambda r: httpx.Response(500)),
        max_retries=2,
        sleep=lambda s: None,
    )
    try:
        c.get("https://example.test/x")
    except HttpError as e:
        assert e.status == 500
    else:
        raise AssertionError("expected HttpError")
