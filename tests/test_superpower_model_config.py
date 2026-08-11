from __future__ import annotations

import importlib

import pytest


class FakeAgent:
    def __init__(self, model, **kwargs):
        self.model = model
        self.kwargs = kwargs


@pytest.mark.parametrize(
    ("module_name", "factory_name", "feature_id"),
    [
        (
            "novelvideo.agents.global_video_optimizer",
            "create_global_video_reviewer_agent",
            "vision_analysis_llm",
        ),
        (
            "novelvideo.agents.video_prompt_builder",
            "create_video_prompt_builder_agent",
            "video_prompt_optimizer_llm",
        ),
        (
            "novelvideo.agents.keyframe_prompt_builder",
            "create_keyframe_prompt_builder_agent",
            "video_prompt_optimizer_llm",
        ),
    ],
)
def test_prompt_agents_use_global_feature_binding(
    monkeypatch,
    module_name,
    factory_name,
    feature_id,
):
    from novelvideo import config

    calls: list[str] = []

    def fake_get_pydantic_model(*, feature_id: str):
        calls.append(feature_id)
        return object()

    monkeypatch.setattr(config, "get_pydantic_model", fake_get_pydantic_model)
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "Agent", FakeAgent)
    monkeypatch.setenv("GLOBAL_VIDEO_PROVIDER", "openrouter")
    monkeypatch.setenv("GLOBAL_VIDEO_MODEL", "stale-env-model")
    monkeypatch.setenv("SUPERPOWER_MODEL_NAME", "request-style-model")

    getattr(module, factory_name)()

    assert calls == [feature_id]
