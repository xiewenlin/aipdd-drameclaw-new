"""Unified NewAPI model catalog endpoints for CE."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from novelvideo import config as app_config
from novelvideo.model_catalog import (
    FEATURE_BY_ID,
    FEATURE_CATALOG,
    OFFICIAL_SERVICE_LABEL,
    OFFICIAL_SERVICE_URL,
    ModelCapability,
    ModelRoutingError,
    model_runtime_resolver,
    get_bindings,
    get_connection,
    get_models,
    get_model_sources,
    get_status,
    merge_models,
    delete_model_source,
    save_bindings,
    save_connection,
    save_model_source,
    update_model_capabilities,
    update_status,
)
from novelvideo.model_gateway_settings import build_media_relay_status, save_media_relay_config
from novelvideo.model_migration import apply_model_migration, build_model_migration_report
from novelvideo.shared.runtime_env import is_ce_effective
from novelvideo.api.auth import get_api_user

router = APIRouter(prefix="/model-gateway", dependencies=[Depends(get_api_user)])


class MediaRelayConfigBody(BaseModel):
    provider: str = "aliyun_oss"
    ttl_seconds: int = Field(default=1800, alias="ttlSeconds")
    endpoint: str = ""
    bucket: str = ""
    access_key_id: str = Field(default="", alias="accessKeyId")
    access_key_secret: str = Field(default="", alias="accessKeySecret")
    cloud_name: str = Field(default="", alias="cloudName")
    cloudinary_api_key: str = Field(default="", alias="apiKey")
    cloudinary_api_secret: str = Field(default="", alias="apiSecret")
    cloudinary_folder: str = Field(default="", alias="apiFolder")


class NewApiConnectionBody(BaseModel):
    base_url: str = Field(alias="baseUrl")
    api_key: str | None = Field(default=None, alias="apiKey")


class ModelSourceBody(BaseModel):
    name: str
    base_url: str = Field(alias="baseUrl")
    api_key: str | None = Field(default=None, alias="apiKey")


class ModelCapabilitiesBody(BaseModel):
    capabilities: list[ModelCapability]


class FeatureBindingsBody(BaseModel):
    bindings: dict[str, str | None]


def _require_ce_catalog_management() -> None:
    if not is_ce_effective():
        raise HTTPException(
            status_code=403,
            detail="model gateway management is only available in CE",
        )


def _media_relay_status() -> dict[str, Any]:
    return build_media_relay_status(
        env_provider=app_config.MEDIA_RELAY_PROVIDER,
        env_ttl_seconds=app_config.MEDIA_RELAY_TTL_SECONDS,
        env_endpoint=app_config.OSS_RELAY_ENDPOINT,
        env_bucket=app_config.OSS_RELAY_BUCKET,
        env_access_key_id=app_config.OSS_RELAY_AK,
        env_access_key_secret=app_config.OSS_RELAY_SK,
        env_cloud_name=app_config.CLOUDINARY_RELAY_CLOUD_NAME,
        env_cloudinary_api_key=app_config.CLOUDINARY_RELAY_API_KEY,
        env_cloudinary_api_secret=app_config.CLOUDINARY_RELAY_API_SECRET,
        env_cloudinary_folder=app_config.CLOUDINARY_RELAY_FOLDER,
    )


def _catalog_status() -> dict[str, Any]:
    from novelvideo.model_runtime_hot_reload import (
        get_model_runtime_status,
        model_runtime_hot_reload_enabled,
    )

    status = get_status()
    if model_runtime_hot_reload_enabled():
        status["restartRequiredComponents"] = [
            component
            for component in status.get("restartRequiredComponents", [])
            if component != "cognee"
        ]
    status.update(get_model_runtime_status())
    return status


def _catalog_payload() -> dict[str, Any]:
    return {
        "mediaRelay": _media_relay_status(),
        "connection": get_connection(),
        "sources": get_model_sources(),
        "catalogStatus": _catalog_status(),
        "officialServiceUrl": OFFICIAL_SERVICE_URL,
        "officialServiceLabel": OFFICIAL_SERVICE_LABEL,
    }


async def _fetch_source_models(source_id: str) -> list[dict[str, Any]]:
    source = next(
        (item for item in get_model_sources(include_secrets=True) if item["id"] == source_id),
        None,
    )
    if not source or not source.get("configured"):
        raise HTTPException(status_code=409, detail={"code": "model_source_missing", "message": "模型源尚未配置"})
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f'{source["baseUrl"]}/models',
                headers={"Authorization": f'Bearer {source["apiKey"]}'},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail={"code": "model_source_request_failed", "message": str(exc)}) from exc
    models = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(models, list):
        raise HTTPException(status_code=502, detail={"code": "invalid_models_response", "message": "模型源 /models 响应缺少 data 数组"})
    return [item for item in models if isinstance(item, dict)]


async def _fetch_upstream_models() -> list[dict[str, Any]]:
    connection = get_connection(include_secret=True)
    if not connection.get("configured"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "model_connection_missing",
                "message": "请先配置 NewAPI 地址和 API Key",
            },
        )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f'{connection["baseUrl"]}/models',
                headers={"Authorization": f'Bearer {connection["apiKey"]}'},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        update_status(lastError=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"code": "newapi_request_failed", "message": str(exc)},
        ) from exc
    models = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(models, list):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "invalid_models_response",
                "message": "NewAPI /models 响应缺少 data 数组",
            },
        )
    return [item for item in models if isinstance(item, dict)]


@router.post("/official/enable")
@router.post("/official/config")
@router.post("/custom/newapi/init")
@router.post("/custom/newapi/provider-channels")
@router.post("/custom/newapi/provider-channel/sync")
@router.post("/custom/newapi/channels")
@router.post("/custom/newapi/channels/batch")
@router.post("/custom/newapi/embedding-model")
@router.post("/custom/newapi/media-models")
async def retired_legacy_model_gateway() -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_model_gateway_retired",
            "message": "旧 official/custom Provider 管理已退役，请使用统一 NewAPI 连接和功能模型绑定。",
        },
    )


@router.get("/config")
async def get_model_gateway_config() -> dict[str, Any]:
    return {"ok": True, "data": _catalog_payload()}


@router.post("/media-relay/config")
async def save_media_relay_settings(body: MediaRelayConfigBody) -> dict[str, Any]:
    _require_ce_catalog_management()
    provider = body.provider.strip().lower()
    if provider not in {"aliyun_oss", "cloudinary"}:
        raise HTTPException(status_code=400, detail="unsupported media relay provider")
    if body.ttl_seconds <= 0:
        raise HTTPException(status_code=400, detail="ttlSeconds must be positive")
    values = {
        "endpoint": body.endpoint.strip(),
        "bucket": body.bucket.strip(),
        "accessKeyId": body.access_key_id.strip(),
        "accessKeySecret": body.access_key_secret.strip(),
        "cloudName": body.cloud_name.strip(),
        "apiKey": body.cloudinary_api_key.strip(),
        "apiSecret": body.cloudinary_api_secret.strip(),
        "apiFolder": body.cloudinary_folder.strip().strip("/"),
    }
    required_names = (
        ("cloudName", "apiKey", "apiSecret")
        if provider == "cloudinary"
        else ("endpoint", "bucket", "accessKeyId", "accessKeySecret")
    )
    missing = [name for name in required_names if not values[name]]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {', '.join(missing)}")
    save_media_relay_config(
        provider=provider,
        ttl_seconds=body.ttl_seconds,
        endpoint=values["endpoint"],
        bucket=values["bucket"],
        access_key_id=values["accessKeyId"],
        access_key_secret=values["accessKeySecret"],
        cloud_name=values["cloudName"],
        cloudinary_api_key=values["apiKey"],
        cloudinary_api_secret=values["apiSecret"],
        cloudinary_folder=values["apiFolder"],
    )
    return {"ok": True, "data": _media_relay_status()}


@router.put("/connection")
async def put_newapi_connection(body: NewApiConnectionBody) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        connection = save_connection(base_url=body.base_url, api_key=body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": {**_catalog_payload(), "connection": connection}}


@router.post("/connection/test")
async def test_newapi_connection() -> dict[str, Any]:
    _require_ce_catalog_management()
    models = await _fetch_upstream_models()
    tested_at = datetime.now(timezone.utc).isoformat()
    update_status(lastTestAt=tested_at, lastError="")
    return {
        "ok": True,
        "data": {"connected": True, "modelCount": len(models), "testedAt": tested_at},
    }


@router.get("/sources")
async def list_model_sources() -> dict[str, Any]:
    return {"ok": True, "data": {"sources": get_model_sources()}}


@router.post("/sources")
async def create_model_source(body: ModelSourceBody) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        source = save_model_source(name=body.name, base_url=body.base_url, api_key=body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": source}


@router.put("/sources/{source_id}")
async def update_model_source(source_id: str, body: ModelSourceBody) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        source = save_model_source(source_id=source_id, name=body.name, base_url=body.base_url, api_key=body.api_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="model source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": source}


@router.delete("/sources/{source_id}")
async def remove_model_source(source_id: str) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        delete_model_source(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="model source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": {"deleted": True}}


@router.post("/sources/{source_id}/test")
async def test_model_source(source_id: str) -> dict[str, Any]:
    _require_ce_catalog_management()
    models = await _fetch_source_models(source_id)
    return {"ok": True, "data": {"connected": True, "modelCount": len(models)}}


@router.post("/sources/{source_id}/models/sync")
async def sync_model_source(source_id: str) -> dict[str, Any]:
    _require_ce_catalog_management()
    if not any(item["id"] == source_id for item in get_model_sources()):
        raise HTTPException(status_code=404, detail="model source not found")
    models = merge_models(await _fetch_source_models(source_id), source_id=source_id)
    return {"ok": True, "data": {"models": models, "sourceId": source_id}}


@router.post("/models/sync")
async def sync_newapi_models() -> dict[str, Any]:
    _require_ce_catalog_management()
    models = merge_models(await _fetch_upstream_models())
    synced_at = datetime.now(timezone.utc).isoformat()
    update_status(lastSyncAt=synced_at, lastError="")
    return {"ok": True, "data": {"models": models, "syncedAt": synced_at}}


@router.get("/models")
async def list_newapi_models(include_unavailable: bool = True) -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "models": get_models(include_unavailable=include_unavailable),
            "status": get_status(),
        },
    }


@router.patch("/models/{model_id:path}")
async def patch_newapi_model(
    model_id: str, body: ModelCapabilitiesBody
) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        model = update_model_capabilities(
            model_id, [item.value for item in body.capabilities]
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
    return {"ok": True, "data": model}


@router.get("/features")
async def list_model_features() -> dict[str, Any]:
    features = [
        {
            "id": item.id,
            "label": item.label,
            "capability": item.capability.value,
            "required": item.required,
        }
        for item in FEATURE_CATALOG
    ]
    return {"ok": True, "data": {"features": features}}


@router.get("/feature-bindings")
async def list_feature_model_bindings() -> dict[str, Any]:
    return {"ok": True, "data": {"bindings": get_bindings()}}


@router.put("/feature-bindings")
async def put_feature_model_bindings(body: FeatureBindingsBody) -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        bindings = save_bindings(body.bindings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "data": {"bindings": bindings, "catalogStatus": _catalog_status()},
    }


@router.get("/migration/dry-run")
async def dry_run_model_migration() -> dict[str, Any]:
    _require_ce_catalog_management()
    return {"ok": True, "data": build_model_migration_report()}


@router.post("/migration/apply")
async def apply_legacy_model_migration() -> dict[str, Any]:
    _require_ce_catalog_management()
    try:
        report = apply_model_migration()
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "model_migration_conflict", "message": str(exc)},
        ) from exc
    return {"ok": True, "data": report}


@router.post("/features/{feature_id}/test")
async def test_feature_model(feature_id: str) -> dict[str, Any]:
    _require_ce_catalog_management()
    feature = FEATURE_BY_ID.get(feature_id)
    model_id = get_bindings().get(feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    if not model_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "feature_model_unbound", "message": "该功能尚未绑定模型"},
        )
    try:
        resolved = model_runtime_resolver.resolve(feature_id)
    except ModelRoutingError as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc
    if feature.capability not in {ModelCapability.LLM, ModelCapability.VISION_LLM}:
        return {
            "ok": True,
            "data": {
                "featureId": feature_id,
                "modelId": model_id,
                "validated": True,
                "liveRequest": False,
            },
        }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f'{resolved.base_url}/chat/completions',
                headers={"Authorization": f'Bearer {resolved.api_key}'},
                json={
                    "model": resolved.model_id,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "feature_test_failed", "message": str(exc)},
        ) from exc
    return {
        "ok": True,
        "data": {
            "featureId": feature_id,
            "modelId": model_id,
            "validated": True,
            "liveRequest": True,
        },
    }
