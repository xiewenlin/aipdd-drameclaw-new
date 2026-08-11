import asyncio
import base64

import pytest

pytestmark = pytest.mark.m04


def run_async(coro):
    return asyncio.run(coro)


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload, *, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeUsageMeter:
    def __init__(self):
        self.refunds = []
        self.confirms = []

    async def reserve_current_model_call_credit(self, **_kwargs):
        return "reservation-1"

    async def refund_model_call_credit_reservation(self, reservation_id, *, metadata=None):
        self.refunds.append({"reservation_id": reservation_id, "metadata": metadata or {}})

    async def bump_model_call(self, **kwargs):
        self.confirms.append(kwargs)


def test_newapi_image_async_task_polls_until_completed(monkeypatch):
    import httpx
    from novelvideo.generators import nanobanana_grid

    calls = []
    poll_responses = [
        {"status": "processing"},
        {
            "status": "completed",
            "data": [{"b64_json": base64.b64encode(b"async-image").decode()}],
        },
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            calls.append(("POST", url))
            return FakeResponse(
                {"id": "response-1", "status": "queued", "task_id": "image-task-1"},
                headers={"x-newapi-request-id": "request-1"},
            )

        async def get(self, url, *, headers):
            calls.append(("GET", url))
            return FakeResponse(poll_responses.pop(0))

    async def no_sleep(_seconds):
        return None

    meter = FakeUsageMeter()
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(nanobanana_grid.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(nanobanana_grid, "get_usage_meter", lambda: meter)
    trace = {}

    image_bytes, _text, error = run_async(
        nanobanana_grid._call_newapi_image_api(
            api_key="newapi-token",
            model="FLUX-GGUF-T2I-V2",
            prompt="async portrait",
            base_url="http://newapi.test/v1",
            trace=trace,
        )
    )

    assert image_bytes == b"async-image"
    assert error == ""
    assert calls == [
        ("POST", "http://newapi.test/v1/images/generations"),
        ("GET", "http://newapi.test/v1/images/generations/image-task-1"),
        ("GET", "http://newapi.test/v1/images/generations/image-task-1"),
    ]
    assert meter.refunds == []
    assert meter.confirms[0]["provider_task_id"] == "image-task-1"
    assert trace["provider_task_id"] == "image-task-1"


def test_newapi_image_async_task_failure_refunds(monkeypatch):
    import httpx
    from novelvideo.generators import nanobanana_grid

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            return FakeResponse({"status": "queued", "task_id": "image-task-failed"})

        async def get(self, url, *, headers):
            return FakeResponse({"status": "failed", "error": {"message": "upstream failed"}})

    async def no_sleep(_seconds):
        return None

    meter = FakeUsageMeter()
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(nanobanana_grid.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(nanobanana_grid, "get_usage_meter", lambda: meter)

    image_bytes, _text, error = run_async(
        nanobanana_grid._call_newapi_image_api(
            api_key="newapi-token",
            model="FLUX-GGUF-T2I-V2",
            prompt="async portrait",
            base_url="http://newapi.test/v1",
        )
    )

    assert image_bytes is None
    assert "upstream failed" in error
    assert meter.refunds[0]["metadata"]["error"] == "upstream failed"


def test_newapi_image_async_task_timeout_refunds(monkeypatch):
    import httpx
    from novelvideo.generators import nanobanana_grid

    poll_count = 0

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            return FakeResponse({"status": "queued", "task_id": "image-task-slow"})

        async def get(self, url, *, headers):
            nonlocal poll_count
            poll_count += 1
            return FakeResponse({"status": "processing"})

    async def no_sleep(_seconds):
        return None

    meter = FakeUsageMeter()
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(nanobanana_grid.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(nanobanana_grid, "NEWAPI_IMAGE_MAX_POLLS", 2)
    monkeypatch.setattr(nanobanana_grid, "get_usage_meter", lambda: meter)

    image_bytes, _text, error = run_async(
        nanobanana_grid._call_newapi_image_api(
            api_key="newapi-token",
            model="FLUX-GGUF-T2I-V2",
            prompt="async portrait",
            base_url="http://newapi.test/v1",
        )
    )

    assert image_bytes is None
    assert "Timeout waiting for DramaClawAPI image task" in error
    assert poll_count == 2
    assert meter.refunds[0]["metadata"]["error"] == "timeout"


def test_newapi_image_async_output_supports_nested_result_url():
    from novelvideo.generators import nanobanana_grid

    assert nanobanana_grid._newapi_image_output(
        {"status": "completed", "result": {"image_url": "https://images.test/result.png"}}
    ) == ("", "https://images.test/result.png")