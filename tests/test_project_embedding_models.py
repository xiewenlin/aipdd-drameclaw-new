from __future__ import annotations

import asyncio
import json

import pytest

from novelvideo.embedding_models import (
    COGNEE_EMBEDDING_DIMENSIONS,
    PROJECT_EMBEDDING_DIMENSION_KEY,
    PROJECT_EMBEDDING_SIGNATURE_KEY,
    KnowledgeEmbeddingRebuildRequired,
    embedding_signature,
    embedding_gateway_credentials,
    embedding_model_scope,
    embedding_model_spec,
    require_current_embedding_model_spec,
)
from novelvideo.model_catalog import ResolvedFeatureModel, model_runtime_resolver
from novelvideo.project_config import (
    ensure_cognee_embedding_binding_in_state_dir,
    require_cognee_embedding_compatibility_in_state_dir,
    save_cognee_embedding_signature_in_state_dir,
)


@pytest.fixture
def global_embedding(monkeypatch: pytest.MonkeyPatch) -> ResolvedFeatureModel:
    resolved = ResolvedFeatureModel(
        feature_id="knowledge_embedding",
        model_id="embed-global",
        base_url="https://newapi.example/v1",
        api_key="sk-global",
    )
    monkeypatch.setattr(model_runtime_resolver, "resolve", lambda feature_id: resolved)
    return resolved


def test_embedding_spec_always_uses_global_binding(global_embedding):
    spec = embedding_model_spec("project-model", dimensions=3072)

    assert spec.internal_model == "embed-global"
    assert spec.dimensions == 3072
    assert spec.gateway == "newapi"
    assert embedding_gateway_credentials(spec) == (
        "sk-global",
        "https://newapi.example/v1",
    )


def test_project_model_field_cannot_override_global_binding(global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    config_path = state_dir / "project_config.json"
    config_path.write_text(
        json.dumps(
            {
                "cognee_embedding_model": "project-specific-model",
                PROJECT_EMBEDDING_DIMENSION_KEY: 1536,
            }
        ),
        encoding="utf-8",
    )

    spec = ensure_cognee_embedding_binding_in_state_dir(state_dir)

    assert spec.internal_model == "embed-global"
    assert spec.dimensions == 1536
    assert json.loads(config_path.read_text(encoding="utf-8"))[
        "cognee_embedding_model"
    ] == "project-specific-model"


def test_missing_project_dimension_uses_legacy_vector_size(global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    spec = ensure_cognee_embedding_binding_in_state_dir(state_dir)

    assert spec.internal_model == "embed-global"
    assert spec.dimensions == COGNEE_EMBEDDING_DIMENSIONS
    config = json.loads((state_dir / "project_config.json").read_text(encoding="utf-8"))
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY]["model"] == "embed-global"


@pytest.mark.parametrize("value", [0, -1, "invalid"])
def test_invalid_project_dimension_fails_closed(global_embedding, tmp_path, value):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "project_config.json").write_text(
        json.dumps({PROJECT_EMBEDDING_DIMENSION_KEY: value}),
        encoding="utf-8",
    )

    with pytest.raises((RuntimeError, ValueError)):
        ensure_cognee_embedding_binding_in_state_dir(state_dir)


@pytest.mark.asyncio
async def test_embedding_scope_isolates_dimensions_not_models(global_embedding):
    async def route(model: str, dimensions: int):
        with embedding_model_scope(model, dimensions=dimensions):
            await asyncio.sleep(0)
            return require_current_embedding_model_spec()

    first, second = await asyncio.gather(
        route("project-a", 1024),
        route("project-b", 3072),
    )

    assert first.internal_model == second.internal_model == "embed-global"
    assert first.dimensions == 1024
    assert second.dimensions == 3072


def test_embedding_scope_requires_context(global_embedding):
    with pytest.raises(RuntimeError, match="runtime model context"):
        require_current_embedding_model_spec()


def test_empty_knowledge_base_adopts_current_model_and_dimensions(
    monkeypatch, global_embedding, tmp_path
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    config_path = state_dir / "project_config.json"
    config_path.write_text(
        json.dumps(
            {
                PROJECT_EMBEDDING_DIMENSION_KEY: 2048,
                PROJECT_EMBEDDING_SIGNATURE_KEY: {
                    "model": "embed-stale",
                    "dimensions": 2048,
                    "sendDimensions": True,
                    "fingerprint": "stale",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "novelvideo.embedding_models._configured_embedding_options",
        lambda: (1024, True),
    )

    spec = ensure_cognee_embedding_binding_in_state_dir(state_dir)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert spec.internal_model == "embed-global"
    assert spec.dimensions == 1024
    assert config[PROJECT_EMBEDDING_DIMENSION_KEY] == 1024
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY]["model"] == "embed-global"
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY]["dimensions"] == 1024


def test_existing_unsigned_knowledge_base_requires_rebuild(global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    (state_dir / "cognee_system").mkdir(parents=True)
    (state_dir / "cognee_system" / "vectors.db").write_text("existing", encoding="utf-8")

    ensure_cognee_embedding_binding_in_state_dir(state_dir)

    with pytest.raises(KnowledgeEmbeddingRebuildRequired, match="knowledge_embedding_rebuild_required"):
        require_cognee_embedding_compatibility_in_state_dir(state_dir)


def test_same_dimension_different_model_requires_rebuild(monkeypatch, global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    spec = ensure_cognee_embedding_binding_in_state_dir(state_dir)
    save_cognee_embedding_signature_in_state_dir(state_dir, spec)
    (state_dir / "cognee_system").mkdir()
    (state_dir / "cognee_system" / "vectors.db").write_text("existing", encoding="utf-8")
    changed = ResolvedFeatureModel(
        feature_id="knowledge_embedding",
        model_id="embed-changed",
        base_url="https://another-newapi.example/v1",
        api_key="sk-changed",
    )
    monkeypatch.setattr(model_runtime_resolver, "resolve", lambda feature_id: changed)

    with pytest.raises(KnowledgeEmbeddingRebuildRequired, match="embed-global"):
        require_cognee_embedding_compatibility_in_state_dir(state_dir)


def test_credential_only_change_keeps_embedding_compatible(monkeypatch, global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    spec = ensure_cognee_embedding_binding_in_state_dir(state_dir)
    original = embedding_signature(spec)
    changed = ResolvedFeatureModel(
        feature_id="knowledge_embedding",
        model_id="embed-global",
        base_url="https://another-newapi.example/v1",
        api_key="sk-changed",
    )
    monkeypatch.setattr(model_runtime_resolver, "resolve", lambda feature_id: changed)

    current = require_cognee_embedding_compatibility_in_state_dir(state_dir)

    assert embedding_signature(current) == original

def test_embedding_rebuild_error_preserves_task_error_code() -> None:
    from novelvideo.task_backend.run_core import _project_task_failure_for_exception

    error = KnowledgeEmbeddingRebuildRequired(
        "knowledge_embedding_rebuild_required: rebuild the knowledge base"
    )
    message, metadata, handled = _project_task_failure_for_exception(error)

    assert message == str(error)
    assert metadata == {"error_code": "knowledge_embedding_rebuild_required"}
    assert handled is True

def test_dimension_change_requires_rebuild(monkeypatch, global_embedding, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    original = embedding_model_spec(dimensions=1024)
    save_cognee_embedding_signature_in_state_dir(state_dir, original)
    (state_dir / "cognee_system").mkdir()
    (state_dir / "cognee_system" / "vectors.db").write_text("existing", encoding="utf-8")
    monkeypatch.setattr(
        "novelvideo.embedding_models._configured_embedding_options",
        lambda: (3072, True),
    )

    with pytest.raises(KnowledgeEmbeddingRebuildRequired, match="1024"):
        require_cognee_embedding_compatibility_in_state_dir(state_dir)


@pytest.mark.asyncio
async def test_failed_rebuild_retains_previous_embedding_signature(
    monkeypatch, global_embedding, tmp_path
):
    from contextlib import asynccontextmanager

    from novelvideo.cognee import store as store_module

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    original = embedding_model_spec(dimensions=1024)
    save_cognee_embedding_signature_in_state_dir(state_dir, original)
    changed = ResolvedFeatureModel(
        feature_id="knowledge_embedding",
        model_id="embed-next",
        base_url="https://newapi.example/v1",
        api_key="sk-next",
    )
    monkeypatch.setattr(model_runtime_resolver, "resolve", lambda feature_id: changed)

    @asynccontextmanager
    async def lease_stub(*_args, **_kwargs):
        yield None

    monkeypatch.setattr(store_module, "cognee_runtime_lease", lease_stub)

    async def ingest_novel_fast(store, novel_path, rebuild=False):
        raise RuntimeError("rebuild failed")

    wrapped = store_module._with_cognee_runtime_lease(ingest_novel_fast)
    fake_store = type("Store", (), {"state_dir": state_dir})()

    with pytest.raises(RuntimeError, match="rebuild failed"):
        await wrapped(fake_store, "novel.txt", rebuild=True)

    config = json.loads((state_dir / "project_config.json").read_text(encoding="utf-8"))
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY] == embedding_signature(original)


@pytest.mark.asyncio
async def test_successful_rebuild_replaces_embedding_signature(
    monkeypatch, global_embedding, tmp_path
):
    from contextlib import asynccontextmanager

    from novelvideo.cognee import store as store_module

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    original = embedding_model_spec(dimensions=1024)
    save_cognee_embedding_signature_in_state_dir(state_dir, original)
    changed = ResolvedFeatureModel(
        feature_id="knowledge_embedding",
        model_id="embed-next",
        base_url="https://newapi.example/v1",
        api_key="sk-next",
    )
    monkeypatch.setattr(model_runtime_resolver, "resolve", lambda feature_id: changed)

    @asynccontextmanager
    async def lease_stub(*_args, **_kwargs):
        yield None

    monkeypatch.setattr(store_module, "cognee_runtime_lease", lease_stub)

    async def ingest_novel_fast(store, novel_path, rebuild=False):
        return {"status": "graph_ready"}

    wrapped = store_module._with_cognee_runtime_lease(ingest_novel_fast)
    fake_store = type("Store", (), {"state_dir": state_dir})()

    result = await wrapped(fake_store, "novel.txt", rebuild=True)

    config = json.loads((state_dir / "project_config.json").read_text(encoding="utf-8"))
    assert result == {"status": "graph_ready"}
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY]["model"] == "embed-next"
    assert config[PROJECT_EMBEDDING_SIGNATURE_KEY] != embedding_signature(original)
