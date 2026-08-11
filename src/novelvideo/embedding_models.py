"""Global Cognee embedding binding and vector compatibility signatures."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from novelvideo.model_gateway_settings import get_newapi_embedding_model_config

PROJECT_EMBEDDING_MODEL_KEY = "cognee_embedding_model"
PROJECT_EMBEDDING_DIMENSION_KEY = "cognee_embedding_dimension"
PROJECT_EMBEDDING_SIGNATURE_KEY = "cognee_embedding_signature"
COGNEE_EMBEDDING_MODEL_LEGACY = "DC-cognee-embedding"
COGNEE_EMBEDDING_MODEL_V1 = "DC-cognee-embedding-v1"
COGNEE_EMBEDDING_MODEL_V2 = "DC-cognee-embedding-v2"
COGNEE_EMBEDDING_DIMENSIONS = 1024


class KnowledgeEmbeddingRebuildRequired(RuntimeError):
    code = "knowledge_embedding_rebuild_required"


@dataclass(frozen=True)
class EmbeddingModelSpec:
    internal_model: str
    dimensions: int
    send_dimensions: bool
    gateway: str = "newapi"


_CURRENT_COGNEE_EMBEDDING_SPEC: ContextVar[EmbeddingModelSpec | None] = ContextVar(
    "current_cognee_embedding_spec",
    default=None,
)


def _configured_embedding_options() -> tuple[int, bool]:
    saved = get_newapi_embedding_model_config()
    dimensions = int(saved.get("dimension") or COGNEE_EMBEDDING_DIMENSIONS)
    if dimensions <= 0:
        raise RuntimeError(f"Unsupported embedding dimensions: {dimensions}")
    return dimensions, bool(saved.get("sendDimensions", True))


def embedding_model_spec(
    model: str | None = None,
    *,
    dimensions: int | None = None,
) -> EmbeddingModelSpec:
    """Resolve the global embedding model while preserving vector dimensions."""

    del model
    from novelvideo.model_catalog import model_runtime_resolver

    resolved = model_runtime_resolver.resolve("knowledge_embedding")
    configured_dimensions, send_dimensions = _configured_embedding_options()
    effective_dimensions = int(configured_dimensions if dimensions is None else dimensions)
    if effective_dimensions <= 0:
        raise RuntimeError(f"Unsupported embedding dimensions: {effective_dimensions}")
    return EmbeddingModelSpec(
        internal_model=resolved.model_id,
        dimensions=effective_dimensions,
        send_dimensions=send_dimensions,
    )


def embedding_signature(spec: EmbeddingModelSpec) -> dict[str, object]:
    model = spec.internal_model.strip()
    semantic = {
        "model": model,
        "dimensions": int(spec.dimensions),
        "sendDimensions": bool(spec.send_dimensions),
    }
    fingerprint = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**semantic, "fingerprint": fingerprint}


def embedding_signature_summary(signature: dict[str, object]) -> str:
    return (
        f"model={signature.get('model') or '<unknown>'}, "
        f"dimensions={signature.get('dimensions') or '<unknown>'}, "
        f"sendDimensions={bool(signature.get('sendDimensions', True))}"
    )


def embedding_model_for_new_project() -> str:
    return embedding_model_spec().internal_model


def embedding_model_binding_for_new_project() -> EmbeddingModelSpec:
    return embedding_model_spec()


def embedding_model_for_legacy_project() -> str:
    return embedding_model_spec().internal_model


def active_gateway_uses_custom_embedding() -> bool:
    return True


def embedding_gateway_credentials(spec: EmbeddingModelSpec) -> tuple[str, str]:
    del spec
    from novelvideo.model_catalog import model_runtime_resolver

    resolved = model_runtime_resolver.resolve("knowledge_embedding")
    return resolved.api_key, resolved.base_url


def current_embedding_model_spec() -> EmbeddingModelSpec | None:
    return _CURRENT_COGNEE_EMBEDDING_SPEC.get()


def require_current_embedding_model_spec() -> EmbeddingModelSpec:
    spec = current_embedding_model_spec()
    if spec is None:
        raise RuntimeError("Cognee embedding request has no runtime model context")
    return spec


@contextmanager
def embedding_model_scope(
    model: str | None = None,
    *,
    dimensions: int | None = None,
) -> Iterator[EmbeddingModelSpec]:
    """Bind the global model and an optional historical vector dimension."""

    spec = embedding_model_spec(model, dimensions=dimensions)
    token = _CURRENT_COGNEE_EMBEDDING_SPEC.set(spec)
    try:
        yield spec
    finally:
        _CURRENT_COGNEE_EMBEDDING_SPEC.reset(token)