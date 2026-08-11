from __future__ import annotations

from types import SimpleNamespace

from novelvideo import model_catalog
from novelvideo.director_world import staging_prop_ai


def _global_scene_runtime():
    return SimpleNamespace(
        model_id="global-scene-model",
        api_key="global-key",
        base_url="https://global.example/v1",
    )



def test_generate_ai_staging_prop_uses_director_world_shape_hints(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_staging_prop_agent(request, **kwargs):
        captured.update(kwargs)
        captured["task"] = staging_prop_ai.build_user_prompt(request)
        return {
            "prop_id": "horse_mount",
            "name": "可骑的马",
            "semantic_label": "horse",
            "shape_hint": "quadruped_mount",
            "position": [1, 0, 2],
            "scale": [1.4, 1.25, 2.2],
            "relation_intent": "mount_actor",
        }

    monkeypatch.setattr(staging_prop_ai, "run_staging_prop_agent", fake_run_staging_prop_agent)
    monkeypatch.setattr(
        model_catalog.model_runtime_resolver,
        "resolve",
        lambda feature_id: _global_scene_runtime(),
    )

    result = staging_prop_ai.generate_ai_staging_prop(
        {
            "api_key": "test-key",
            "base_url": "http://example.test/v1",
            "model": "test-model",
            "scene_id": "面馆",
            "user_hint": "让男青年骑一匹马",
            "crosshair_target": {"position": [1, 0, 2]},
        }
    )

    assert result["ok"] is True
    assert result["model"] == "global-scene-model"
    assert result["prop"]["shape_hint"] == "quadruped_mount"
    assert result["prop"]["attachment_points"][0]["kind"] == "mount"
    assert captured["model"] == "global-scene-model"
    assert "让男青年骑一匹马" in captured["task"]


def test_generate_ai_staging_prop_falls_back_to_shape_hint_inference(monkeypatch) -> None:
    monkeypatch.setattr(
        model_catalog.model_runtime_resolver,
        "resolve",
        lambda feature_id: _global_scene_runtime(),
    )
    async def fake_run_staging_prop_agent(_request, **_kwargs):
        return {"name": "一匹马"}

    monkeypatch.setattr(staging_prop_ai, "run_staging_prop_agent", fake_run_staging_prop_agent)

    result = staging_prop_ai.generate_ai_staging_prop(
        {"api_key": "test-key", "user_hint": "让他骑马", "crosshair_target": {}}
    )

    assert result["prop"]["semantic_label"] == "horse"
    assert result["prop"]["shape_hint"] == "quadruped_mount"
    assert result["prop"]["relation_intent"] == "mount_actor"


def test_resolve_model_config_ignores_request_and_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("STAGING_PROP_MODEL", "stale-env-model")
    monkeypatch.setattr(
        model_catalog.model_runtime_resolver,
        "resolve",
        lambda feature_id: _global_scene_runtime(),
    )

    model, api_key, base_url = staging_prop_ai.resolve_model_config(
        {"model": "request-model", "api_key": "request-key", "base_url": "https://request.example"}
    )

    assert (model, api_key, base_url) == (
        "global-scene-model",
        "global-key",
        "https://global.example/v1",
    )
