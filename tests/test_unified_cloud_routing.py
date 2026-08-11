from __future__ import annotations

import pytest

from novelvideo.model_catalog import ResolvedFeatureModel, model_runtime_resolver


def _resolved(feature_id: str, model_id: str) -> ResolvedFeatureModel:
    return ResolvedFeatureModel(
        feature_id=feature_id,
        model_id=model_id,
        base_url="https://newapi.example/v1",
        api_key="gateway-key",
    )


@pytest.mark.parametrize("legacy_backend", ["seedance_fast", "wan26", "grok_720", "huimeng_seedance-2.0-fast"])
def test_cloud_video_backends_route_through_global_newapi_binding(
    monkeypatch: pytest.MonkeyPatch, legacy_backend: str
) -> None:
    from novelvideo.generators.video_generator import (
        NewApiVideoGenerator,
        create_video_generator,
    )

    monkeypatch.setattr(
        model_runtime_resolver,
        "resolve",
        lambda feature_id: _resolved(feature_id, "global-video"),
    )

    generator = create_video_generator(backend=legacy_backend)

    assert isinstance(generator, NewApiVideoGenerator)
    assert generator.api_key == "gateway-key"
    assert generator.base_url == "https://newapi.example/v1"
    assert generator.model == "global-video"


def test_text_to_video_uses_its_own_global_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    from novelvideo.generators.video_generator import create_video_generator

    requested: list[str] = []

    def resolve(feature_id: str) -> ResolvedFeatureModel:
        requested.append(feature_id)
        return _resolved(feature_id, "text-video-model")

    monkeypatch.setattr(model_runtime_resolver, "resolve", resolve)

    generator = create_video_generator(backend="seedance_fast", feature_id="text_to_video")

    assert requested == ["text_to_video"]
    assert generator.model == "text-video-model"


def test_image_generator_rejects_direct_credentials_and_uses_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from novelvideo.generators.image_generator import VolcengineImageGenerator

    monkeypatch.setattr(
        model_runtime_resolver,
        "resolve",
        lambda feature_id: _resolved(feature_id, "global-image"),
    )

    generator = VolcengineImageGenerator()

    assert generator.api_key == "gateway-key"
    assert generator.endpoint == "https://newapi.example/v1"
    assert generator.seedream_model == "global-image"
    with pytest.raises(ValueError, match="overrides are not supported"):
        VolcengineImageGenerator(api_key="direct-provider-key")


def test_grid_generator_rejects_non_newapi_provider() -> None:
    from novelvideo.generators.nanobanana_grid import NanoBananaGridGenerator

    config = {
        "provider": "openai",
        "api_key": "direct-provider-key",
        "model": "legacy-image-model",
        "rows": 1,
        "cols": 1,
        "total_panels": 1,
    }

    with pytest.raises(ValueError, match="All image generation must use the NewAPI gateway"):
        NanoBananaGridGenerator(config=config)
