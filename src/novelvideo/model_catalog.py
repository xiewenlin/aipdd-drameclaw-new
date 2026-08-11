"""Global model source catalog and feature bindings."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from novelvideo.model_gateway_settings import (
    _read_all,
    _write_many,
    mask_secret,
    normalize_api_key,
    normalize_relay_base_url,
)

CATALOG_VERSION = 1
DEFAULT_SOURCE_ID = "newapi"
OFFICIAL_SERVICE_URL = "https://newapi.chonghuayunke.com"
OFFICIAL_SERVICE_LABEL = "没有可用的 NewAPI 服务？获取官方服务"


class ModelCapability(StrEnum):
    LLM = "llm"
    VISION_LLM = "vision_llm"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    EMBEDDING = "embedding"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeatureDefinition:
    id: str
    label: str
    capability: ModelCapability
    required: bool = True


FEATURE_CATALOG: tuple[FeatureDefinition, ...] = (
    FeatureDefinition("knowledge_llm", "知识库 LLM", ModelCapability.LLM),
    FeatureDefinition("hermes_llm", "Hermes 剧本分析", ModelCapability.LLM),
    FeatureDefinition("scene_builder_llm", "场景构建", ModelCapability.LLM),
    FeatureDefinition("content_rewriter_llm", "内容改写", ModelCapability.LLM),
    FeatureDefinition("video_prompt_optimizer_llm", "视频提示词优化", ModelCapability.LLM),
    FeatureDefinition("vision_analysis_llm", "视觉分析", ModelCapability.VISION_LLM),
    FeatureDefinition("sketch_image", "草图生成", ModelCapability.IMAGE),
    FeatureDefinition("render_image", "渲染图生成", ModelCapability.IMAGE),
    FeatureDefinition("scene_master_image", "场景主图", ModelCapability.IMAGE),
    FeatureDefinition("scene_reverse_image", "场景反打图", ModelCapability.IMAGE),
    FeatureDefinition("scene_360_image", "场景 360 图", ModelCapability.IMAGE),
    FeatureDefinition("prop_reference_image", "道具参考图", ModelCapability.IMAGE),
    FeatureDefinition("character_reference_image", "角色参考图", ModelCapability.IMAGE),
    FeatureDefinition("image_to_video", "图生视频", ModelCapability.VIDEO),
    FeatureDefinition("text_to_video", "文生视频", ModelCapability.VIDEO),
    FeatureDefinition("character_tts", "角色语音", ModelCapability.AUDIO),
    FeatureDefinition("background_music", "背景音乐", ModelCapability.AUDIO, required=False),
    FeatureDefinition("knowledge_embedding", "知识库 Embedding", ModelCapability.EMBEDDING),
)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURE_CATALOG}

_CONNECTION_KEY = "newapi_connection_v1"
_MODELS_KEY = "newapi_model_catalog_v1"
_BINDINGS_KEY = "feature_model_bindings_v1"
_STATUS_KEY = "newapi_sync_status_v1"
_SOURCES_KEY = "model_sources_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(key: str, default: Any) -> Any:
    raw = _read_all().get(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _save_json(key: str, value: Any) -> None:
    _write_many({key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))})


def normalize_newapi_base_url(value: str | None) -> str:
    return normalize_relay_base_url(value)


def normalize_model_source_base_url(value: str | None) -> str:
    """Preserve provider-specific API paths such as Volcengine Ark /api/v3."""
    return str(value or "").strip().rstrip("/")


def get_connection(*, include_secret: bool = False) -> dict[str, Any]:
    saved = _load_json(_CONNECTION_KEY, {})
    api_key = normalize_api_key(saved.get("apiKey"))
    result = {
        "baseUrl": normalize_newapi_base_url(saved.get("baseUrl")),
        "apiKeyPreview": mask_secret(api_key),
        "configured": bool(normalize_newapi_base_url(saved.get("baseUrl")) and api_key),
    }
    if include_secret:
        result["apiKey"] = api_key
    return result


def _source_binding_id(source_id: str, model_id: str) -> str:
    return model_id if source_id == DEFAULT_SOURCE_ID else f"{source_id}::{model_id}"


def save_connection(*, base_url: str, api_key: str | None = None) -> dict[str, Any]:
    normalized_url = normalize_newapi_base_url(base_url)
    if not normalized_url:
        raise ValueError("NewAPI base URL is required")
    existing = get_connection(include_secret=True)
    normalized_key = normalize_api_key(api_key)
    if api_key is not None and str(api_key).strip() and not normalized_key:
        raise ValueError("API key is invalid")
    effective_key = normalized_key or existing.get("apiKey", "")
    changed = (
        existing.get("baseUrl") != normalized_url
        or existing.get("apiKey", "") != effective_key
    )
    _save_json(
        _CONNECTION_KEY,
        {"version": CATALOG_VERSION, "baseUrl": normalized_url, "apiKey": effective_key},
    )
    if changed:
        mark_runtime_configuration_changed()
    return get_connection()


def get_model_sources(*, include_secrets: bool = False) -> list[dict[str, Any]]:
    connection = get_connection(include_secret=include_secrets)
    sources: list[dict[str, Any]] = [
        {
            "id": DEFAULT_SOURCE_ID,
            "name": "NewAPI",
            "type": "newapi",
            "baseUrl": connection.get("baseUrl", ""),
            "apiKeyPreview": connection.get("apiKeyPreview", ""),
            "configured": connection.get("configured", False),
            "isDefault": True,
            **({"apiKey": connection.get("apiKey", "")} if include_secrets else {}),
        }
    ]
    saved = _load_json(_SOURCES_KEY, [])
    if not isinstance(saved, list):
        return sources
    for raw in saved:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("id") or "").strip()
        if not source_id or source_id == DEFAULT_SOURCE_ID:
            continue
        api_key = normalize_api_key(raw.get("apiKey"))
        base_url = normalize_model_source_base_url(raw.get("baseUrl"))
        source = {
            "id": source_id,
            "name": str(raw.get("name") or source_id).strip(),
            "type": "openai_compatible",
            "baseUrl": base_url,
            "apiKeyPreview": mask_secret(api_key),
            "configured": bool(base_url and api_key),
            "isDefault": False,
        }
        if include_secrets:
            source["apiKey"] = api_key
        sources.append(source)
    return sources


def save_model_source(
    *, name: str, base_url: str, api_key: str | None = None, source_id: str | None = None
) -> dict[str, Any]:
    normalized_name = str(name).strip()
    normalized_url = normalize_model_source_base_url(base_url)
    if not normalized_name:
        raise ValueError("model source name is required")
    if not normalized_url:
        raise ValueError("model source base URL is required")
    if source_id == DEFAULT_SOURCE_ID:
        raise ValueError("the NewAPI source must use the connection API")
    sources = get_model_sources(include_secrets=True)[1:]
    existing = next((item for item in sources if item["id"] == source_id), None)
    if source_id and existing is None:
        raise KeyError(source_id)
    normalized_key = normalize_api_key(api_key)
    if api_key is not None and str(api_key).strip() and not normalized_key:
        raise ValueError("API key is invalid")
    effective_key = normalized_key or (existing or {}).get("apiKey", "")
    if not effective_key:
        raise ValueError("model source API key is required")
    effective_id = source_id or "source_{}".format(uuid.uuid4().hex[:12])
    stored = {
        "id": effective_id,
        "name": normalized_name,
        "type": "openai_compatible",
        "baseUrl": normalized_url,
        "apiKey": effective_key,
    }
    updated = [
        {
            "id": item["id"],
            "name": item["name"],
            "type": "openai_compatible",
            "baseUrl": item["baseUrl"],
            "apiKey": item.get("apiKey", ""),
        }
        for item in sources
        if item["id"] != effective_id
    ]
    updated.append(stored)
    _save_json(_SOURCES_KEY, updated)
    mark_runtime_configuration_changed()
    return next(item for item in get_model_sources() if item["id"] == effective_id)


def delete_model_source(source_id: str) -> None:
    if source_id == DEFAULT_SOURCE_ID:
        raise ValueError("the NewAPI source cannot be deleted")
    sources = get_model_sources(include_secrets=True)[1:]
    if not any(item["id"] == source_id for item in sources):
        raise KeyError(source_id)
    _save_json(
        _SOURCES_KEY,
        [
            {
                "id": item["id"],
                "name": item["name"],
                "type": "openai_compatible",
                "baseUrl": item["baseUrl"],
                "apiKey": item.get("apiKey", ""),
            }
            for item in sources
            if item["id"] != source_id
        ],
    )
    removed_bindings = {
        model["bindingId"]
        for model in get_models()
        if model.get("sourceId") == source_id
    }
    _save_json(
        _MODELS_KEY,
        [model for model in get_models() if model.get("sourceId") != source_id],
    )
    bindings = get_bindings()
    next_bindings = {fid: bid for fid, bid in bindings.items() if bid not in removed_bindings}
    if next_bindings != bindings:
        _save_json(_BINDINGS_KEY, next_bindings)
    mark_runtime_configuration_changed()



def infer_capabilities(model_id: str, metadata: dict[str, Any] | None = None) -> list[str]:
    text = " ".join([model_id, json.dumps(metadata or {}, ensure_ascii=False)]).lower()
    capabilities: set[ModelCapability] = set()
    if any(token in text for token in ("embedding", "embed", "bge-", "text-embedding")):
        capabilities.add(ModelCapability.EMBEDDING)
    if any(token in text for token in ("tts", "speech", "audio", "voice", "suno")):
        capabilities.add(ModelCapability.AUDIO)
    if any(token in text for token in ("video", "seedance", "veo", "kling", "sora", "wan2")):
        capabilities.add(ModelCapability.VIDEO)
    if any(token in text for token in ("image", "flux", "stable-diffusion", "dall-e", "midjourney", "ling-shan", "lingshan")):
        capabilities.add(ModelCapability.IMAGE)
    if any(token in text for token in ("vision", "gpt-4o", "gemini", "qwen-vl")):
        capabilities.add(ModelCapability.VISION_LLM)
    if not capabilities and any(token in text for token in ("gpt", "claude", "deepseek", "qwen", "llama", "glm", "mistral", "chat")):
        capabilities.add(ModelCapability.LLM)
    return sorted(capability.value for capability in capabilities) or [ModelCapability.UNKNOWN.value]


def get_models(*, include_unavailable: bool = True) -> list[dict[str, Any]]:
    raw = _load_json(_MODELS_KEY, [])
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        source_id = str(item.get("sourceId") or DEFAULT_SOURCE_ID)
        model_id = str(item["id"])
        normalized.append({**item, "sourceId": source_id, "bindingId": str(item.get("bindingId") or _source_binding_id(source_id, model_id))})
    return normalized if include_unavailable else [model for model in normalized if model.get("available", True)]


def merge_models(
    upstream_models: Iterable[dict[str, Any]], *, source_id: str = DEFAULT_SOURCE_ID
) -> list[dict[str, Any]]:
    all_models = get_models()
    existing = {str(item.get("id")): item for item in all_models if item.get("id") and item.get("sourceId") == source_id}
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    synced_at = _now_iso()
    for raw in upstream_models:
        model_id = str(raw.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        previous = existing.get(model_id, {})
        inferred = infer_capabilities(model_id, raw)
        manual = previous.get("manualCapabilities") or []
        merged.append({
            "id": model_id,
            "sourceId": source_id,
            "bindingId": _source_binding_id(source_id, model_id),
            "ownedBy": str(raw.get("owned_by") or raw.get("ownedBy") or ""),
            "capabilities": manual or inferred,
            "inferredCapabilities": inferred,
            "manualCapabilities": manual,
            "available": True,
            "metadata": raw,
            "lastSeenAt": synced_at,
        })
    for model_id, previous in existing.items():
        if model_id not in seen:
            merged.append({**previous, "available": False})
    untouched = [item for item in all_models if item.get("sourceId") != source_id]
    all_updated = untouched + merged
    all_updated.sort(key=lambda item: (str(item.get("sourceId", "")).lower(), str(item.get("id", "")).lower()))
    _save_json(_MODELS_KEY, all_updated)
    return all_updated


def update_model_capabilities(binding_id: str, capabilities: Iterable[str]) -> dict[str, Any]:
    normalized = sorted({ModelCapability(item).value for item in capabilities})
    models = get_models()
    for model in models:
        if model.get("bindingId") == binding_id:
            model["manualCapabilities"] = normalized
            model["capabilities"] = normalized or model.get("inferredCapabilities") or ["unknown"]
            _save_json(_MODELS_KEY, models)
            return model
    raise KeyError(binding_id)


def get_bindings() -> dict[str, str]:
    raw = _load_json(_BINDINGS_KEY, {})
    return {str(key): str(value) for key, value in raw.items() if value}


def save_bindings(bindings: dict[str, str | None]) -> dict[str, str]:
    unknown = sorted(set(bindings) - set(FEATURE_BY_ID))
    if unknown:
        raise ValueError(f"unknown feature ids: {', '.join(unknown)}")
    model_ids = {model["bindingId"] for model in get_models()}
    missing = sorted({str(value) for value in bindings.values() if value and value not in model_ids})
    if missing:
        raise ValueError(f"unknown model ids: {', '.join(missing)}")
    previous = get_bindings()
    current = dict(previous)
    for feature_id, model_id in bindings.items():
        if model_id:
            current[feature_id] = str(model_id)
        else:
            current.pop(feature_id, None)
    _save_json(_BINDINGS_KEY, current)
    if current != previous:
        mark_runtime_configuration_changed()

    return current


def get_status() -> dict[str, Any]:
    status = _load_json(_STATUS_KEY, {})
    return status if isinstance(status, dict) else {}


def update_status(**values: Any) -> dict[str, Any]:
    status = {**get_status(), **values}
    _save_json(_STATUS_KEY, status)
    return status


def get_runtime_revision() -> int:
    try:
        return int(get_status().get("runtimeRevision", 0))
    except (TypeError, ValueError):
        return 0


def mark_runtime_configuration_changed(
    *, restart_components: Iterable[str] = ()
) -> dict[str, Any]:
    status = get_status()
    pending = {
        str(component).strip()
        for component in status.get("restartRequiredComponents", [])
        if str(component).strip()
    }
    pending.update(
        str(component).strip()
        for component in restart_components
        if str(component).strip()
    )
    from novelvideo.model_runtime_hot_reload import model_runtime_hot_reload_enabled

    if not model_runtime_hot_reload_enabled():
        pending.add("cognee")
    updated = update_status(
        runtimeRevision=get_runtime_revision() + 1,
        restartRequiredComponents=sorted(pending),
    )
    try:
        from novelvideo.model_runtime_hot_reload import (
            note_model_runtime_configuration_changed,
        )

        if model_runtime_hot_reload_enabled():
            note_model_runtime_configuration_changed()
    except (ImportError, ModelRoutingError):
        pass
    return updated


class ModelRoutingError(RuntimeError):
    code = "model_routing_error"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class ModelConnectionMissing(ModelRoutingError):
    code = "model_connection_missing"


class FeatureModelUnbound(ModelRoutingError):
    code = "feature_model_unbound"


class BoundModelUnavailable(ModelRoutingError):
    code = "bound_model_unavailable"


@dataclass(frozen=True)
class ResolvedFeatureModel:
    feature_id: str
    model_id: str
    base_url: str
    api_key: str
    source_id: str = DEFAULT_SOURCE_ID


class ModelRuntimeResolver:
    """Resolve models exclusively from global feature bindings."""

    def resolve(self, feature_id: str) -> ResolvedFeatureModel:
        if feature_id not in FEATURE_BY_ID:
            raise FeatureModelUnbound(f"Unknown feature: {feature_id}")
        binding_id = get_bindings().get(feature_id)
        if not binding_id:
            raise FeatureModelUnbound(f"Feature has no global model binding: {feature_id}")
        model = next((item for item in get_models() if item.get("bindingId") == binding_id), None)
        if not model or not model.get("available", True):
            raise BoundModelUnavailable(f"Bound model is unavailable: {binding_id}")
        source_id = str(model.get("sourceId") or DEFAULT_SOURCE_ID)
        source = next((item for item in get_model_sources(include_secrets=True) if item["id"] == source_id), None)
        if not source or not source.get("configured"):
            raise ModelConnectionMissing(f"Model source is not configured: {source_id}")
        return ResolvedFeatureModel(
            feature_id=feature_id,
            model_id=str(model["id"]),
            base_url=str(source["baseUrl"]),
            api_key=str(source["apiKey"]),
            source_id=source_id,
        )


model_runtime_resolver = ModelRuntimeResolver()

