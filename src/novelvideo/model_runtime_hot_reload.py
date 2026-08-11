"""Process-local generation coordinator for Cognee model settings."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import threading
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator






class ModelRuntimeReloadError(RuntimeError):
    code = "model_runtime_reload_failed"


class ModelRuntimeReloadWaitTimeout(ModelRuntimeReloadError):
    code = "model_runtime_reload_wait_timeout"


class ModelRuntimeRestartRequired(ModelRuntimeReloadError):
    code = "model_runtime_restart_required"


def model_runtime_hot_reload_enabled() -> bool:
    value = os.getenv("MODEL_RUNTIME_HOT_RELOAD_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ModelRuntimeSnapshot:
    runtime_revision: int
    base_url: str
    api_key: str
    llm_model: str
    embedding_model: str
    embedding_dimensions: int
    send_embedding_dimensions: bool
    fingerprint: str
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_credentials_required: bool = False


def _fingerprint(parts: Iterator[str]) -> str:
    material = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_model_runtime_snapshot() -> ModelRuntimeSnapshot:
    from novelvideo.model_catalog import get_runtime_revision, model_runtime_resolver
    from novelvideo.embedding_models import _configured_embedding_options

    llm = model_runtime_resolver.resolve("knowledge_llm")
    embedding = model_runtime_resolver.resolve("knowledge_embedding")
    embedding_dimensions, send_dimensions = _configured_embedding_options()

    base_url = llm.base_url
    api_key = llm.api_key
    llm_model = llm.model_id
    embedding_model = embedding.model_id
    embedding_base_url = embedding.base_url
    embedding_api_key = embedding.api_key
    embedding_credentials_required = True
    revision = get_runtime_revision()

    fingerprint = _fingerprint(
        iter(
            (
                base_url,
                api_key,
                llm_model,
                embedding_model,
                str(embedding_dimensions),
                "1" if send_dimensions else "0",
                embedding_base_url,
                embedding_api_key,
                "1" if embedding_credentials_required else "0",
            )
        )
    )
    return ModelRuntimeSnapshot(
        runtime_revision=revision,
        base_url=base_url,
        api_key=api_key,
        llm_model=llm_model,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        send_embedding_dimensions=send_dimensions,
        fingerprint=fingerprint,
        embedding_base_url=embedding_base_url,
        embedding_api_key=embedding_api_key,
        embedding_credentials_required=embedding_credentials_required,
    )


ApplySnapshot = Callable[[ModelRuntimeSnapshot], Any]
_lease_context: ContextVar[tuple[int, ModelRuntimeSnapshot, int] | None] = ContextVar(
    "novelvideo_cognee_runtime_lease", default=None
)


class ModelRuntimeCoordinator:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._apply_lock = threading.Lock()
        self._apply_snapshot: ApplySnapshot | None = None
        self._active_snapshot: ModelRuntimeSnapshot | None = None
        self._desired_snapshot: ModelRuntimeSnapshot | None = None
        self._active_lease_count = 0
        self._state = "uninitialized"
        self._last_applied_at: str | None = None
        self._last_reload_error = ""
        self._failed_fingerprint: str | None = None

    def register_applier(self, apply_snapshot: ApplySnapshot) -> None:
        with self._lock:
            self._apply_snapshot = apply_snapshot

    def note_configuration_changed(self) -> None:
        desired = build_model_runtime_snapshot()
        with self._lock:
            self._desired_snapshot = desired
            if self._active_snapshot is not None and self._active_snapshot.fingerprint == desired.fingerprint:
                self._active_snapshot = desired
                if self._state != "applying":
                    self._state = "ready"
            elif self._active_lease_count:
                self._state = "draining"
            elif self._active_snapshot is not None:
                self._state = "pending"

    @staticmethod
    def _sanitize_error(error: BaseException, snapshot: ModelRuntimeSnapshot) -> str:
        message = str(error)
        for secret in (snapshot.api_key, snapshot.embedding_api_key):
            if secret:
                message = message.replace(secret, "***")
        return message[:500]

    def _apply(self, snapshot: ModelRuntimeSnapshot) -> None:
        applier = self._apply_snapshot
        if applier is None:
            raise ModelRuntimeReloadError("Cognee runtime applier is not registered")
        if not snapshot.api_key:
            raise ModelRuntimeReloadError("Cognee LLM Key is not configured")
        if not snapshot.base_url:
            raise ModelRuntimeReloadError("NewAPI base URL is not configured")
        if not snapshot.embedding_model:
            raise ModelRuntimeReloadError("Knowledge Embedding model is not configured")
        if snapshot.embedding_credentials_required and not snapshot.embedding_base_url:
            raise ModelRuntimeReloadError("Knowledge Embedding endpoint is not configured")
        if snapshot.embedding_credentials_required and not snapshot.embedding_api_key:
            raise ModelRuntimeReloadError("Knowledge Embedding key is not configured; configure knowledge_embedding binding in settings")
        result = applier(snapshot)
        if inspect.isawaitable(result):
            raise ModelRuntimeReloadError("Cognee runtime applier must be synchronous")

    def ensure_ready_sync(self) -> ModelRuntimeSnapshot:
        desired = build_model_runtime_snapshot()
        with self._lock:
            self._desired_snapshot = desired
            if self._state == "failed" and self._failed_fingerprint == desired.fingerprint:
                raise ModelRuntimeReloadError(
                    self._last_reload_error or "Cognee runtime reload failed"
                )
            if (
                self._active_snapshot is not None
                and self._active_snapshot.fingerprint == desired.fingerprint
                and self._state == "ready"
            ):
                if self._active_snapshot.runtime_revision != desired.runtime_revision:
                    self._active_snapshot = desired
                return self._active_snapshot
            if self._active_lease_count:
                self._state = "draining"
                raise ModelRuntimeReloadError(
                    "Cognee runtime is draining; acquire an asynchronous runtime lease"
                )
            self._state = "applying"

        with self._apply_lock:
            try:
                self._apply(desired)
            except Exception as exc:
                sanitized_error = self._sanitize_error(exc, desired)
                with self._lock:
                    self._state = "failed"
                    self._last_reload_error = sanitized_error
                    self._failed_fingerprint = desired.fingerprint
                raise ModelRuntimeReloadError(sanitized_error) from exc

        with self._lock:
            self._active_snapshot = desired
            self._desired_snapshot = desired
            self._state = "ready"
            self._last_reload_error = ""
            self._failed_fingerprint = None
            self._last_applied_at = datetime.now(timezone.utc).isoformat()
            return desired

    def ensure_ready_without_reload_sync(self) -> ModelRuntimeSnapshot:
        desired = build_model_runtime_snapshot()
        with self._lock:
            self._desired_snapshot = desired
            active = self._active_snapshot
            if active is not None and active.fingerprint != desired.fingerprint:
                self._state = "pending"
                raise ModelRuntimeRestartRequired(
                    "Model gateway configuration changed; restart the backend to apply it"
                )
            if active is not None:
                return active
        return self.ensure_ready_sync()
    async def acquire_without_reload(self) -> ModelRuntimeSnapshot:
        desired = build_model_runtime_snapshot()
        should_apply = False
        with self._lock:
            self._desired_snapshot = desired
            active = self._active_snapshot
            if active is None:
                self._state = "applying"
                should_apply = True
            elif active.fingerprint != desired.fingerprint:
                self._state = "pending"
                raise ModelRuntimeRestartRequired(
                    "Model gateway configuration changed; restart the backend to apply it"
                )

        if should_apply:
            with self._apply_lock:
                try:
                    self._apply(desired)
                except Exception as exc:
                    sanitized_error = self._sanitize_error(exc, desired)
                    with self._lock:
                        self._state = "failed"
                        self._last_reload_error = sanitized_error
                        self._failed_fingerprint = desired.fingerprint
                    raise ModelRuntimeReloadError(sanitized_error) from exc
            with self._lock:
                self._active_snapshot = desired
                self._state = "ready"
                self._last_reload_error = ""
                self._failed_fingerprint = None
                self._last_applied_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            active = self._active_snapshot
            if active is None:
                raise ModelRuntimeReloadError("Cognee runtime is not initialized")
            self._active_lease_count += 1
            _lease_context.set((id(asyncio.current_task()), active, 1))
            return active

    async def acquire(self, timeout: float | None = None) -> ModelRuntimeSnapshot:
        current = _lease_context.get()
        task_id = id(asyncio.current_task())
        if current is not None and current[0] == task_id:
            _lease_context.set((task_id, current[1], current[2] + 1))
            return current[1]

        wait_timeout = float(
            timeout if timeout is not None else os.getenv("MODEL_RUNTIME_RELOAD_WAIT_TIMEOUT", "120")
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(wait_timeout, 0.0)

        while True:
            desired = build_model_runtime_snapshot()
            should_apply = False
            with self._lock:
                self._desired_snapshot = desired
                active = self._active_snapshot
                if (
                    active is not None
                    and active.fingerprint == desired.fingerprint
                    and self._state not in {"applying", "failed"}
                ):
                    if active.runtime_revision != desired.runtime_revision:
                        active = desired
                        self._active_snapshot = desired
                    self._state = "ready"
                    self._active_lease_count += 1
                    _lease_context.set((task_id, active, 1))
                    return active
                if self._state == "failed" and self._failed_fingerprint == desired.fingerprint:
                    raise ModelRuntimeReloadError(
                        self._last_reload_error or "Cognee runtime reload failed"
                    )
                if self._active_lease_count:
                    self._state = "draining"
                elif self._state != "applying":
                    self._state = "applying"
                    should_apply = True

            if should_apply:
                with self._apply_lock:
                    try:
                        self._apply(desired)
                    except Exception as exc:
                        sanitized_error = self._sanitize_error(exc, desired)
                        with self._lock:
                            self._state = "failed"
                            self._last_reload_error = sanitized_error
                            self._failed_fingerprint = desired.fingerprint
                        raise ModelRuntimeReloadError(sanitized_error) from exc
                latest = build_model_runtime_snapshot()
                with self._lock:
                    self._active_snapshot = desired
                    self._desired_snapshot = latest
                    self._state = (
                        "ready" if latest.fingerprint == desired.fingerprint else "pending"
                    )
                    self._last_reload_error = ""
                    self._failed_fingerprint = None
                    self._last_applied_at = datetime.now(timezone.utc).isoformat()
                continue

            if loop.time() >= deadline:
                raise ModelRuntimeReloadWaitTimeout(
                    "Timed out waiting for the active Cognee runtime generation to drain"
                )
            await asyncio.sleep(0.05)

    def release(self) -> None:
        current = _lease_context.get()
        task_id = id(asyncio.current_task())
        if current is None or current[0] != task_id:
            return
        if current[2] > 1:
            _lease_context.set((task_id, current[1], current[2] - 1))
            return
        _lease_context.set(None)
        with self._lock:
            self._active_lease_count = max(0, self._active_lease_count - 1)
            desired = self._desired_snapshot
            active = self._active_snapshot
            if (
                self._active_lease_count == 0
                and desired is not None
                and active is not None
                and desired.fingerprint != active.fingerprint
            ):
                self._state = "pending"

    @asynccontextmanager
    async def lease(self, timeout: float | None = None):
        snapshot = await self.acquire(timeout=timeout)
        try:
            yield snapshot
        finally:
            self.release()

    def status(self) -> dict[str, Any]:
        from novelvideo.model_catalog import ModelRoutingError, get_runtime_revision

        try:
            persisted = build_model_runtime_snapshot()
        except ModelRoutingError as exc:
            with self._lock:
                active = self._active_snapshot
                return {
                    "desiredRevision": get_runtime_revision(),
                    "activeRevision": active.runtime_revision if active else None,
                    "runtimeState": "failed" if active else "uninitialized",
                    "activeLeaseCount": self._active_lease_count,
                    "lastAppliedAt": self._last_applied_at,
                    "lastReloadError": f"{exc.code}: model gateway configuration is incomplete",
                }
        with self._lock:
            self._desired_snapshot = persisted
            desired = persisted
            active = self._active_snapshot
            state = self._state
            if state == "ready" and active is not None and desired.fingerprint != active.fingerprint:
                state = "draining" if self._active_lease_count else "pending"
            return {
                "desiredRevision": desired.runtime_revision,
                "activeRevision": active.runtime_revision if active else None,
                "runtimeState": state,
                "activeLeaseCount": self._active_lease_count,
                "lastAppliedAt": self._last_applied_at,
                "lastReloadError": self._last_reload_error,
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._active_snapshot = None
            self._desired_snapshot = None
            self._active_lease_count = 0
            self._state = "uninitialized"
            self._last_applied_at = None
            self._last_reload_error = ""
            self._failed_fingerprint = None
        _lease_context.set(None)


model_runtime_coordinator = ModelRuntimeCoordinator()


def get_model_runtime_status() -> dict[str, Any]:
    return model_runtime_coordinator.status()


def note_model_runtime_configuration_changed() -> None:
    model_runtime_coordinator.note_configuration_changed()


@asynccontextmanager
async def cognee_runtime_lease(timeout: float | None = None):
    if model_runtime_hot_reload_enabled():
        async with model_runtime_coordinator.lease(timeout=timeout) as snapshot:
            yield snapshot
        return

    snapshot = await model_runtime_coordinator.acquire_without_reload()
    try:
        yield snapshot
    finally:
        model_runtime_coordinator.release()
