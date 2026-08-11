"""Cognee gateway changes use the process-local hot-reload coordinator."""

import pytest


def test_cognee_gateway_never_requires_process_restart(monkeypatch):
    from novelvideo.cognee import config as nv_config

    monkeypatch.setenv("ST_EDITION", "ce")
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
    monkeypatch.setattr(nv_config, "_active_gateway_fingerprint", "old")
    monkeypatch.setattr(nv_config, "_current_gateway_fingerprint", lambda: "new")

    assert nv_config.cognee_gateway_restart_required() is False

def test_strict_llm_cache_reset_propagates_failure(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from novelvideo.cognee import config as nv_config

    def fail_cache_clear() -> None:
        raise RuntimeError("cache reset failed")

    getter = lambda: None
    getter.cache_clear = fail_cache_clear
    module_name = "cognee.infrastructure.llm.config"
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(get_llm_config=getter))

    nv_config._clear_cognee_llm_config_cache()
    with pytest.raises(RuntimeError, match="cache reset failed"):
        nv_config._clear_cognee_llm_config_cache(strict=True)

def test_restart_required_only_when_hot_reload_disabled(monkeypatch) -> None:
    from novelvideo.cognee import config as nv_config

    monkeypatch.setenv("MODEL_RUNTIME_HOT_RELOAD_ENABLED", "false")
    assert nv_config.cognee_gateway_restart_required() is True


def test_locked_cognee_and_litellm_cache_hooks_are_supported() -> None:
    from importlib.metadata import version

    import cognee.infrastructure.databases.vector.embeddings.config as embedding_config
    import cognee.infrastructure.llm.config as llm_config
    import litellm

    assert version("cognee") == "1.0.5"
    assert version("litellm")
    assert callable(getattr(llm_config.get_llm_config, "cache_clear", None))
    assert callable(getattr(embedding_config.get_embedding_config, "cache_clear", None))
    assert callable(
        getattr(litellm.in_memory_llm_clients_cache, "flush_cache", None)
    )


def test_litellm_client_cache_reset(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from novelvideo.cognee import config as nv_config

    calls: list[str] = []
    cache = SimpleNamespace(flush_cache=lambda: calls.append("flush"))
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(in_memory_llm_clients_cache=cache))

    nv_config._clear_litellm_client_cache(strict=True)

    assert calls == ["flush"]


def test_strict_litellm_client_cache_reset_propagates_failure(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from novelvideo.cognee import config as nv_config

    def fail_cache_clear() -> None:
        raise RuntimeError("litellm cache reset failed")

    cache = SimpleNamespace(flush_cache=fail_cache_clear)
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(in_memory_llm_clients_cache=cache))

    with pytest.raises(RuntimeError, match="litellm cache reset failed"):
        nv_config._clear_litellm_client_cache(strict=True)

def _runtime_snapshot(*, api_key: str = "new-secret"):
    from novelvideo.model_runtime_hot_reload import ModelRuntimeSnapshot

    return ModelRuntimeSnapshot(
        runtime_revision=2,
        base_url="https://newapi.example/v1",
        api_key=api_key,
        llm_model="knowledge-llm",
        embedding_model="knowledge-embedding",
        embedding_dimensions=1536,
        send_embedding_dimensions=True,
        fingerprint="runtime-v2",
        embedding_base_url="https://ark.example/api/v3",
        embedding_api_key="ark-secret",
    )


def _stub_runtime_adapter(monkeypatch, nv_config, fake_config) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(nv_config, "COGNEE_AVAILABLE", True)
    monkeypatch.setattr(nv_config, "cognee", SimpleNamespace(config=fake_config))
    monkeypatch.setattr(nv_config, "_clear_cognee_llm_config_cache", lambda **_kwargs: None)
    monkeypatch.setattr(nv_config, "_clear_cognee_embedding_config_cache", lambda **_kwargs: None)
    monkeypatch.setattr(nv_config, "_clear_litellm_client_cache", lambda **_kwargs: None)
    monkeypatch.setattr(nv_config, "_apply_cognee_runtime_defaults", lambda: None)
    monkeypatch.setattr(nv_config, "_patch_cognee_embedding_timeout", lambda: None)
    monkeypatch.setattr(nv_config, "_install_insufficient_credits_log_filter", lambda: None)
    monkeypatch.setattr(nv_config, "_patch_cognee_embedding_gateway", lambda: None)
    monkeypatch.setattr(nv_config, "_install_cognee_pipeline_concurrency", lambda: None)


def test_atomic_runtime_application_updates_environment_and_cognee(monkeypatch) -> None:
    from types import SimpleNamespace

    from novelvideo.cognee import config as nv_config

    fake_config = SimpleNamespace(
        llm_provider="old-provider",
        llm_model="old-llm",
        llm_api_key="old-key",
        embedding_provider="old-provider",
        embedding_model="old-embedding",
        embedding_dimensions=1024,
        embedding_api_key="old-key",
    )
    _stub_runtime_adapter(monkeypatch, nv_config, fake_config)

    nv_config._apply_runtime_snapshot(_runtime_snapshot())

    assert nv_config.os.environ["LLM_API_KEY"] == "new-secret"
    assert nv_config.os.environ["EMBEDDING_API_KEY"] == "ark-secret"
    assert nv_config.os.environ["EMBEDDING_ENDPOINT"] == "https://ark.example/api/v3"
    assert fake_config.llm_model == "openai/knowledge-llm"
    assert fake_config.embedding_model == "openai/knowledge-embedding"
    assert fake_config.embedding_dimensions == 1536


def test_ce_embedding_request_routes_to_temporary_volcengine(monkeypatch) -> None:
    from novelvideo.cognee import config as nv_config
    from novelvideo.embedding_models import embedding_model_scope

    monkeypatch.setattr("novelvideo.embedding_models.is_ce_effective", lambda: True)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-secret")

    with embedding_model_scope() as spec:
        routed = nv_config._project_embedding_request_kwargs(
            {
                "model": "openai/newapi-embedding",
                "api_key": "newapi-secret",
                "api_base": "https://newapi.example/v1",
            }
        )

    assert spec.gateway == "volcengine-test"
    assert routed["model"] == "openai/doubao-embedding-vision"
    assert routed["api_key"] == "ark-test-secret"
    assert routed["api_base"] == "https://ark.cn-beijing.volces.com/api/coding/v3"
    assert routed["custom_llm_provider"] == "openai"
    assert routed["dimensions"] == 2048

def test_atomic_runtime_application_rolls_back_on_cache_failure(monkeypatch) -> None:
    from types import SimpleNamespace

    from novelvideo.cognee import config as nv_config

    fake_config = SimpleNamespace(
        llm_provider="old-provider",
        llm_model="old-llm",
        llm_api_key="old-key",
        embedding_provider="old-provider",
        embedding_model="old-embedding",
        embedding_dimensions=1024,
        embedding_api_key="old-key",
    )
    _stub_runtime_adapter(monkeypatch, nv_config, fake_config)
    monkeypatch.setenv("LLM_API_KEY", "old-key")
    calls = 0

    def fail_first_strict_reset(*, strict: bool = False) -> None:
        nonlocal calls
        calls += 1
        if strict:
            raise RuntimeError("client cache reset failed")

    monkeypatch.setattr(nv_config, "_clear_cognee_llm_config_cache", fail_first_strict_reset)

    with pytest.raises(RuntimeError, match="client cache reset failed"):
        nv_config._apply_runtime_snapshot(_runtime_snapshot(api_key="never-expose-this"))

    assert nv_config.os.environ["LLM_API_KEY"] == "old-key"
    assert fake_config.llm_model == "old-llm"
    assert fake_config.llm_api_key == "old-key"
    assert calls >= 2


def test_runtime_compatibility_installers_remain_idempotent(monkeypatch) -> None:
    import logging

    from novelvideo.cognee import config as nv_config

    handler = logging.StreamHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        nv_config._install_insufficient_credits_log_filter()
        nv_config._install_insufficient_credits_log_filter()
        filters = [
            item
            for item in handler.filters
            if getattr(item, "_novelvideo_insufficient_credits_filter", False)
        ]
        assert len(filters) == 1
    finally:
        root_logger.removeHandler(handler)
