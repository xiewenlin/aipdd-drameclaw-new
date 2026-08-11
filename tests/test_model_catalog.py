from __future__ import annotations

import pytest

from novelvideo import config
from novelvideo.model_catalog import (
    BoundModelUnavailable,
    FEATURE_BY_ID,
    FeatureModelUnbound,
    ModelConnectionMissing,
    ModelRuntimeResolver,
    get_bindings,
    get_connection,
    get_models,
    get_model_sources,
    get_runtime_revision,
    get_status,
    infer_capabilities,
    merge_models,
    normalize_model_source_base_url,
    normalize_newapi_base_url,
    save_bindings,
    save_connection,
    save_model_source,
    delete_model_source,
    update_model_capabilities,
)


def _isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)


def test_normalize_newapi_base_url() -> None:
    assert normalize_newapi_base_url("https://api.example.com/") == "https://api.example.com/v1"
    assert normalize_newapi_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"


def test_blank_api_key_preserves_saved_secret(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)

    save_connection(base_url="https://api.example.com", api_key="sk-original")
    save_connection(base_url="https://other.example.com/v1/", api_key="")

    connection = get_connection(include_secret=True)
    assert connection["baseUrl"] == "https://other.example.com/v1"
    assert connection["apiKey"] == "sk-original"
    assert connection["configured"] is True
    assert "sk-original" not in get_connection()["apiKeyPreview"]


def test_merge_models_preserves_manual_capabilities_and_marks_missing_unavailable(
    monkeypatch, tmp_path
) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "chat-one"}, {"id": "mystery-model"}])
    update_model_capabilities("mystery-model", ["image"])

    merged = merge_models([{"id": "mystery-model", "owned_by": "team"}])
    by_id = {item["id"]: item for item in merged}

    assert by_id["mystery-model"]["capabilities"] == ["image"]
    assert by_id["mystery-model"]["manualCapabilities"] == ["image"]
    assert by_id["mystery-model"]["available"] is True
    assert by_id["chat-one"]["available"] is False


def test_unknown_models_are_not_auto_classified() -> None:
    assert infer_capabilities("vendor-model-2026") == ["unknown"]
    assert infer_capabilities("text-embedding-3-large") == ["embedding"]
    assert infer_capabilities("seedance-2.0") == ["video"]


def test_global_bindings_can_select_unknown_model(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "vendor-model-2026"}])

    save_bindings({"hermes_llm": "vendor-model-2026"})

    assert get_bindings() == {"hermes_llm": "vendor-model-2026"}


def test_runtime_resolver_reports_missing_connection(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "chat-one"}])
    save_bindings({"hermes_llm": "chat-one"})

    with pytest.raises(ModelConnectionMissing):
        ModelRuntimeResolver().resolve("hermes_llm")


def test_runtime_resolver_reports_unbound_feature(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    save_connection(base_url="https://api.example.com", api_key="sk-test")

    with pytest.raises(FeatureModelUnbound):
        ModelRuntimeResolver().resolve("hermes_llm")


def test_runtime_resolver_reports_unavailable_bound_model(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    save_connection(base_url="https://api.example.com", api_key="sk-test")
    merge_models([{"id": "chat-one"}])
    save_bindings({"hermes_llm": "chat-one"})
    merge_models([])

    with pytest.raises(BoundModelUnavailable):
        ModelRuntimeResolver().resolve("hermes_llm")


def test_runtime_resolver_returns_only_global_binding(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    save_connection(base_url="https://api.example.com", api_key="sk-test")
    merge_models([{"id": "chat-one"}])
    save_bindings({"hermes_llm": "chat-one"})

    resolved = ModelRuntimeResolver().resolve("hermes_llm")

    assert resolved.model_id == "chat-one"
    assert resolved.base_url == "https://api.example.com/v1"
    assert resolved.api_key == "sk-test"
    assert get_models()[0]["id"] == "chat-one"

def test_runtime_revision_changes_without_cognee_restart_requirement(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    assert get_runtime_revision() == 0

    save_connection(base_url="https://api.example.com", api_key="sk-test")
    merge_models([{"id": "embed-one"}, {"id": "chat-one"}])
    after_connection = get_runtime_revision()
    save_bindings({"hermes_llm": "chat-one"})

    assert get_runtime_revision() == after_connection + 1
    assert get_status()["restartRequiredComponents"] == []

    save_bindings({"knowledge_embedding": "embed-one"})

    assert get_runtime_revision() == after_connection + 2
    assert get_status()["restartRequiredComponents"] == []


def test_unchanged_binding_does_not_advance_runtime_revision(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    save_connection(base_url="https://api.example.com", api_key="sk-test")
    merge_models([{"id": "chat-one"}])
    save_bindings({"hermes_llm": "chat-one"})
    revision = get_runtime_revision()

    save_bindings({"hermes_llm": "chat-one"})

    assert get_runtime_revision() == revision

def test_feature_catalog_includes_all_runtime_media_slots() -> None:
    assert FEATURE_BY_ID["character_reference_image"].capability.value == "image"
    assert FEATURE_BY_ID["background_music"].capability.value == "audio"
    assert FEATURE_BY_ID["background_music"].required is False

def test_custom_source_preserves_provider_api_path_and_masks_secret(
    monkeypatch, tmp_path
) -> None:
    _isolate_settings(monkeypatch, tmp_path)

    source = save_model_source(
        name="Volcengine Ark",
        base_url="https://ark.example.com/api/v3/",
        api_key="ark-secret-key",
    )

    assert normalize_model_source_base_url("https://ark.example.com/api/v3/") == "https://ark.example.com/api/v3"
    assert source["baseUrl"] == "https://ark.example.com/api/v3"
    assert "apiKey" not in source
    assert "ark-secret-key" not in source["apiKeyPreview"]
    secret_source = next(
        item
        for item in get_model_sources(include_secrets=True)
        if item["id"] == source["id"]
    )
    assert secret_source["apiKey"] == "ark-secret-key"


def test_same_model_id_from_multiple_sources_routes_selected_credentials(
    monkeypatch, tmp_path
) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    save_connection(base_url="https://newapi.example.com", api_key="newapi-key")
    source = save_model_source(
        name="Direct Provider",
        base_url="https://provider.example.com/api/v3",
        api_key="direct-key",
    )
    merge_models([{"id": "same-model"}])
    merge_models([{"id": "same-model"}], source_id=source["id"])
    binding_id = f'{source["id"]}::same-model'
    save_bindings({"hermes_llm": binding_id})

    resolved = ModelRuntimeResolver().resolve("hermes_llm")

    assert len([model for model in get_models() if model["id"] == "same-model"]) == 2
    assert resolved.model_id == "same-model"
    assert resolved.source_id == source["id"]
    assert resolved.base_url == "https://provider.example.com/api/v3"
    assert resolved.api_key == "direct-key"


def test_delete_source_removes_its_models_and_bindings(monkeypatch, tmp_path) -> None:
    _isolate_settings(monkeypatch, tmp_path)
    source = save_model_source(
        name="Direct Provider",
        base_url="https://provider.example.com/v1",
        api_key="direct-key",
    )
    merge_models([{"id": "direct-model"}], source_id=source["id"])
    save_bindings({"hermes_llm": f'{source["id"]}::direct-model'})

    delete_model_source(source["id"])

    assert all(model["sourceId"] != source["id"] for model in get_models())
    assert "hermes_llm" not in get_bindings()
    assert all(item["id"] != source["id"] for item in get_model_sources())
