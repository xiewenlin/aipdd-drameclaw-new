from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai.models.test import TestModel

from novelvideo import config
from novelvideo.freezone.vision_gateway import (
    VisionInput,
    call_freezone_vision_model,
    image_media_type,
)
from novelvideo import model_catalog


@pytest.mark.asyncio
async def test_vision_gateway_uses_global_feature_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get_model(*, feature_id: str):
        captured["feature_id"] = feature_id
        return TestModel(custom_output_text="??????")

    monkeypatch.setattr(config, "get_pydantic_model", fake_get_model)
    monkeypatch.setattr(
        model_catalog.model_runtime_resolver,
        "resolve",
        lambda feature_id: SimpleNamespace(model_id="global-vision-model"),
    )
    monkeypatch.setenv("FREEZONE_VISION_MODEL", "stale-env-model")

    model, output = await call_freezone_vision_model(
        prompt="????",
        images=[VisionInput(data=b"image", media_type="image/png")],
        model_override="request-model",
    )

    assert model == "global-vision-model"
    assert output == "??????"
    assert captured == {"feature_id": "vision_analysis_llm"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("frame.png", "image/png"),
        ("frame.jpg", "image/jpeg"),
        ("frame.JPEG", "image/jpeg"),
        ("frame.webp", "image/webp"),
        ("frame.gif", "image/gif"),
        ("frame", "image/png"),
    ],
)
def test_image_media_type(path: str, expected: str) -> None:
    assert image_media_type(path) == expected
