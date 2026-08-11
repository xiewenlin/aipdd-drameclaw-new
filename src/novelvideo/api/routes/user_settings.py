"""User settings endpoints: model gateway config, provider channels, model mappings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from novelvideo.api.auth import get_api_user
from novelvideo.ports import get_user_model_settings

router = APIRouter(prefix="/settings")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class GatewayConfigUpdate(BaseModel):
    gateway_mode: str | None = None
    newapi_base_url: str | None = Field(default=None, alias="baseUrl")
    newapi_api_key: str | None = Field(default=None, alias="apiKey")
    media_relay_provider: str | None = None
    media_relay_ttl: int | None = None
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_ak: str | None = None
    oss_sk: str | None = None
    cognee_provider: str | None = None
    cognee_model: str | None = None
    cognee_dimensions: str | None = None
    embedding_batch_size: str | None = None
    image_default_width: int | None = None
    image_default_height: int | None = None
    image_default_style: str | None = None
    video_resolution: str | None = None
    video_generate_audio: str | None = None


class ProviderChannelCreate(BaseModel):
    provider_type: int = Field(alias="type")
    name: str
    base_url: str = ""
    api_key: str = ""
    weight: int = 1
    status: str = "enabled"


class ProviderChannelUpdate(BaseModel):
    provider_type: int | None = Field(default=None, alias="type")
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    weight: int | None = None
    status: str | None = None


class ModelMappingItem(BaseModel):
    model_key: str
    model_name: str
    channel_id: str | None = None
    model_type: int
    priority: int = 0
    status: str = "enabled"


class ModelMappingsUpdate(BaseModel):
    mappings: list[ModelMappingItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user_id(user: dict) -> str:
    uid = str(user.get("user_id") or user.get("id") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return uid


# ---------------------------------------------------------------------------
# Model gateway config
# ---------------------------------------------------------------------------


@router.get("/model-gateway")
async def get_model_gateway_config(user: dict = Depends(get_api_user)):
    """获取当前用户的模型网关配置。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    config = await settings.get_user_config(user_id)
    return JSONResponse({"ok": True, "data": config})


@router.put("/model-gateway")
async def update_model_gateway_config(
    body: GatewayConfigUpdate,
    user: dict = Depends(get_api_user),
):
    """更新当前用户的模型网关配置。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    config = await settings.update_user_config(user_id, body.model_dump(exclude_none=True))
    return JSONResponse({"ok": True, "data": config})


# ---------------------------------------------------------------------------
# Provider channels
# ---------------------------------------------------------------------------


@router.get("/provider-channels")
async def list_provider_channels(user: dict = Depends(get_api_user)):
    """获取当前用户的所有渠道配置。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    channels = await settings.list_channels(user_id)
    return JSONResponse({"ok": True, "data": channels})


@router.post("/provider-channels")
async def create_provider_channel(
    body: ProviderChannelCreate,
    user: dict = Depends(get_api_user),
):
    """创建一个新的渠道。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    channel = await settings.create_channel(user_id, body.model_dump())
    return JSONResponse({"ok": True, "data": channel})


@router.put("/provider-channels/{channel_id}")
async def update_provider_channel(
    channel_id: str,
    body: ProviderChannelUpdate,
    user: dict = Depends(get_api_user),
):
    """更新指定渠道。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    try:
        channel = await settings.update_channel(
            user_id, channel_id, body.model_dump(exclude_none=True)
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Channel not found")
    return JSONResponse({"ok": True, "data": channel})


@router.delete("/provider-channels/{channel_id}")
async def delete_provider_channel(
    channel_id: str,
    user: dict = Depends(get_api_user),
):
    """删除指定渠道。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    success = await settings.delete_channel(user_id, channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Model mappings
# ---------------------------------------------------------------------------


@router.get("/model-mappings")
async def get_model_mappings(user: dict = Depends(get_api_user)):
    """获取当前用户的模型映射配置。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    mappings = await settings.list_model_mappings(user_id)
    return JSONResponse({"ok": True, "data": mappings})


@router.put("/model-mappings")
async def update_model_mappings(
    body: ModelMappingsUpdate,
    user: dict = Depends(get_api_user),
):
    """批量更新模型映射（全量替换）。"""
    user_id = _current_user_id(user)
    settings = get_user_model_settings()
    mappings_data = [m.model_dump() for m in body.mappings]
    mappings = await settings.update_model_mappings(user_id, mappings_data)
    return JSONResponse({"ok": True, "data": mappings})
