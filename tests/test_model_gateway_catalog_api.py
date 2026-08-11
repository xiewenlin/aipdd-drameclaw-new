from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelvideo import config


@pytest.fixture
def gateway_module():
    route_path = (
        Path(__file__).parents[1]
        / "src"
        / "novelvideo"
        / "api"
        / "routes"
        / "model_gateway.py"
    )
    spec = importlib.util.spec_from_file_location(
        "novelvideo_model_gateway_catalog_api", route_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(gateway_module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
    monkeypatch.setattr(gateway_module, "is_ce_effective", lambda: True)
    app = FastAPI()
    app.include_router(gateway_module.router)
    return TestClient(app)


def test_config_exposes_only_unified_catalog_and_media_relay(client: TestClient) -> None:
    response = client.get("/model-gateway/config")

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
        "mediaRelay",
        "connection",
        "sources",
        "catalogStatus",
        "officialServiceUrl",
        "officialServiceLabel",
    }
    assert data["officialServiceUrl"] == "https://newapi.chonghuayunke.com"
    assert {
        "desiredRevision",
        "activeRevision",
        "runtimeState",
        "activeLeaseCount",
        "lastAppliedAt",
        "lastReloadError",
    } <= set(data["catalogStatus"])
    assert "apiKey" not in data["connection"]


@pytest.mark.parametrize(
    "path",
    [
        "/model-gateway/official/enable",
        "/model-gateway/official/config",
        "/model-gateway/custom/newapi/init",
        "/model-gateway/custom/newapi/provider-channels",
        "/model-gateway/custom/newapi/provider-channel/sync",
        "/model-gateway/custom/newapi/channels",
        "/model-gateway/custom/newapi/channels/batch",
        "/model-gateway/custom/newapi/embedding-model",
        "/model-gateway/custom/newapi/media-models",
    ],
)
def test_legacy_gateway_mutations_are_gone(client: TestClient, path: str) -> None:
    response = client.post(path, json={})

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "legacy_model_gateway_retired"


def test_connection_save_uses_only_unified_catalog(client: TestClient) -> None:
    response = client.put(
        "/model-gateway/connection",
        json={"baseUrl": "https://api.example.com", "apiKey": "sk-test"},
    )

    assert response.status_code == 200
    connection = response.json()["data"]["connection"]
    assert connection["baseUrl"] == "https://api.example.com/v1"
    assert connection["configured"] is True
    assert "apiKey" not in connection
    assert response.json()["data"]["catalogStatus"]["restartRequiredComponents"] == []


def test_migration_endpoints_return_dry_run_and_idempotent_apply(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_NAME", "missing-from-catalog")

    dry_run = client.get("/model-gateway/migration/dry-run")
    applied = client.post("/model-gateway/migration/apply")

    assert dry_run.status_code == 200
    assert dry_run.json()["data"]["canApply"] is True
    assert applied.status_code == 200
    assert applied.json()["data"]["applied"] is False

@pytest.mark.asyncio
async def test_save_drains_and_applies_before_next_cognee_operation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from novelvideo import model_runtime_hot_reload as runtime_module
    from novelvideo.cognee import store as store_module
    from novelvideo.model_runtime_hot_reload import (
        ModelRuntimeCoordinator,
        ModelRuntimeSnapshot,
    )

    def snapshot(revision: int, key: str) -> ModelRuntimeSnapshot:
        return ModelRuntimeSnapshot(
            runtime_revision=revision,
            base_url="https://api.example.com/v1",
            api_key=key,
            llm_model="knowledge-llm",
            embedding_model="knowledge-embedding",
            embedding_dimensions=1024,
            send_embedding_dimensions=True,
            fingerprint=f"runtime-{revision}",
        )

    current = [snapshot(1, "old-key")]
    applied: list[int] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda value: applied.append(value.runtime_revision))
    monkeypatch.setattr(runtime_module, "model_runtime_coordinator", coordinator)
    monkeypatch.setattr(runtime_module, "build_model_runtime_snapshot", lambda: current[0])
    monkeypatch.setattr(
        store_module,
        "require_cognee_embedding_compatibility_in_state_dir",
        lambda _state_dir: None,
    )

    await coordinator.acquire()
    current[0] = snapshot(2, "new-key")
    response = client.put(
        "/model-gateway/connection",
        json={"baseUrl": "https://api.example.com", "apiKey": "new-key"},
    )

    assert response.status_code == 200
    assert coordinator.status()["runtimeState"] == "draining"
    coordinator.release()

    async def search(store, query):
        async with runtime_module.cognee_runtime_lease() as active:
            return active.runtime_revision

    wrapped_search = store_module._with_cognee_runtime_lease(search)
    fake_store = type("Store", (), {"state_dir": Path("unused")})()

    assert await wrapped_search(fake_store, "hello") == 2
    assert applied == [1, 2]
    assert coordinator.status()["runtimeState"] == "ready"

def test_disabled_hot_reload_preserves_restart_required_component(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_RUNTIME_HOT_RELOAD_ENABLED", "false")

    response = client.put(
        "/model-gateway/connection",
        json={"baseUrl": "https://api.example.com", "apiKey": "sk-test"},
    )

    assert response.status_code == 200
    status = response.json()["data"]["catalogStatus"]
    assert status["restartRequiredComponents"] == ["cognee"]


def test_custom_source_crud_hides_secret(client: TestClient) -> None:
    created = client.post(
        "/model-gateway/sources",
        json={
            "name": "Volcengine Ark",
            "baseUrl": "https://ark.example.com/api/v3/",
            "apiKey": "ark-secret-key",
        },
    )

    assert created.status_code == 200
    source = created.json()["data"]
    assert source["baseUrl"] == "https://ark.example.com/api/v3"
    assert "apiKey" not in source
    assert "ark-secret-key" not in source["apiKeyPreview"]

    listed = client.get("/model-gateway/sources").json()["data"]["sources"]
    assert any(item["id"] == source["id"] for item in listed)
    assert all("apiKey" not in item for item in listed)

    deleted = client.delete(f'/model-gateway/sources/{source["id"]}')
    assert deleted.status_code == 200


def test_custom_source_sync_adds_source_binding_ids(
    client: TestClient, gateway_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = client.post(
        "/model-gateway/sources",
        json={
            "name": "Direct Provider",
            "baseUrl": "https://provider.example.com/api/v3",
            "apiKey": "direct-secret-key",
        },
    ).json()["data"]

    async def fetch_models(source_id: str) -> list[dict[str, str]]:
        assert source_id == source["id"]
        return [{"id": "same-model"}]

    monkeypatch.setattr(gateway_module, "_fetch_source_models", fetch_models)
    response = client.post(f'/model-gateway/sources/{source["id"]}/models/sync')

    assert response.status_code == 200
    models = response.json()["data"]["models"]
    direct = next(item for item in models if item["sourceId"] == source["id"])
    assert direct["id"] == "same-model"
    assert direct["bindingId"] == f'{source["id"]}::same-model'
