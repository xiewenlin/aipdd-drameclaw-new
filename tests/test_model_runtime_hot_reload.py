from __future__ import annotations

import asyncio

import pytest

from novelvideo.model_runtime_hot_reload import (
    ModelRuntimeCoordinator,
    ModelRuntimeReloadError,
    ModelRuntimeReloadWaitTimeout,
    ModelRuntimeSnapshot,
    build_model_runtime_snapshot,
)
from novelvideo.model_catalog import ResolvedFeatureModel, model_runtime_resolver


def _snapshot(
    revision: int,
    fingerprint: str,
    *,
    api_key: str = "secret-key",
) -> ModelRuntimeSnapshot:
    return ModelRuntimeSnapshot(
        runtime_revision=revision,
        base_url="https://newapi.example.com",
        api_key=api_key,
        llm_model="knowledge-llm",
        embedding_model="knowledge-embedding",
        embedding_dimensions=1024,
        send_embedding_dimensions=True,
        fingerprint=fingerprint,
    )


def _install_snapshot_reader(monkeypatch, current: list[ModelRuntimeSnapshot]) -> None:
    monkeypatch.setattr(
        "novelvideo.model_runtime_hot_reload.build_model_runtime_snapshot",
        lambda: current[0],
    )


def test_snapshot_uses_global_knowledge_bindings(monkeypatch) -> None:
    monkeypatch.setattr("novelvideo.model_catalog.get_runtime_revision", lambda: 7)
    monkeypatch.setattr(
        "novelvideo.embedding_models.get_newapi_embedding_model_config",
        lambda: {"dimension": 2048, "sendDimensions": False},
    )
    resolved = {
        "knowledge_llm": ResolvedFeatureModel(
            feature_id="knowledge_llm",
            model_id="knowledge-chat",
            base_url="https://newapi.example/v1",
            api_key="llm-key",
        ),
        "knowledge_embedding": ResolvedFeatureModel(
            feature_id="knowledge_embedding",
            model_id="knowledge-vector",
            base_url="https://newapi.example/v1",
            api_key="embedding-key",
        ),
    }
    monkeypatch.setattr(model_runtime_resolver, "resolve", resolved.__getitem__)

    snapshot = build_model_runtime_snapshot()

    assert snapshot.embedding_model == "knowledge-vector"
    assert snapshot.embedding_dimensions == 2048
    assert snapshot.send_embedding_dimensions is False
    assert snapshot.embedding_base_url == "https://newapi.example/v1"
    assert snapshot.embedding_api_key == "embedding-key"
    assert snapshot.llm_model == "knowledge-chat"
    assert snapshot.base_url == "https://newapi.example/v1"
    assert snapshot.api_key == "llm-key"


def test_unchanged_fingerprint_updates_revision_without_reapplying(monkeypatch) -> None:
    current = [_snapshot(1, "same-runtime")]
    _install_snapshot_reader(monkeypatch, current)
    applied: list[ModelRuntimeSnapshot] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(applied.append)

    coordinator.ensure_ready_sync()
    current[0] = _snapshot(2, "same-runtime")
    coordinator.note_configuration_changed()
    active = coordinator.ensure_ready_sync()

    assert active.runtime_revision == 2
    assert applied == [_snapshot(1, "same-runtime")]
    assert coordinator.status()["runtimeState"] == "ready"


@pytest.mark.asyncio
async def test_repeated_saves_coalesce_to_latest_snapshot(monkeypatch) -> None:
    first = _snapshot(1, "first")
    second = _snapshot(2, "second")
    latest = _snapshot(3, "latest")
    current = [first]
    _install_snapshot_reader(monkeypatch, current)
    applied: list[ModelRuntimeSnapshot] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(applied.append)

    async with coordinator.lease():
        current[0] = second
        coordinator.note_configuration_changed()
        current[0] = latest
        coordinator.note_configuration_changed()
        async def acquire_latest() -> ModelRuntimeSnapshot:
            async with coordinator.lease(timeout=1) as snapshot:
                return snapshot

        waiter = asyncio.create_task(acquire_latest())
        await asyncio.sleep(0.06)
        assert not waiter.done()
        assert coordinator.status()["runtimeState"] == "draining"

    acquired = await waiter

    assert acquired == latest
    assert applied == [first, latest]
    assert coordinator.status()["activeRevision"] == 3


@pytest.mark.asyncio
async def test_new_lease_waits_until_old_generation_releases(monkeypatch) -> None:
    first = _snapshot(1, "first")
    latest = _snapshot(2, "latest")
    current = [first]
    _install_snapshot_reader(monkeypatch, current)
    events: list[str] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda snapshot: events.append(f"apply:{snapshot.runtime_revision}"))

    async with coordinator.lease():
        events.append("old:start")
        current[0] = latest
        coordinator.note_configuration_changed()

        async def use_latest() -> None:
            async with coordinator.lease(timeout=1) as snapshot:
                events.append(f"new:{snapshot.runtime_revision}")

        waiter = asyncio.create_task(use_latest())
        await asyncio.sleep(0.06)
        events.append("old:end")
        assert "new:2" not in events

    await waiter

    assert events == ["apply:1", "old:start", "old:end", "apply:2", "new:2"]


@pytest.mark.asyncio
async def test_wait_timeout_does_not_cancel_active_lease(monkeypatch) -> None:
    current = [_snapshot(1, "first")]
    _install_snapshot_reader(monkeypatch, current)
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda snapshot: None)

    async with coordinator.lease():
        current[0] = _snapshot(2, "latest")
        coordinator.note_configuration_changed()

        async def wait_for_latest() -> None:
            with pytest.raises(ModelRuntimeReloadWaitTimeout):
                await coordinator.acquire(timeout=0.01)

        await asyncio.create_task(wait_for_latest())
        assert coordinator.status()["activeLeaseCount"] == 1

    assert coordinator.status()["activeLeaseCount"] == 0


@pytest.mark.asyncio
async def test_cancellation_releases_lease(monkeypatch) -> None:
    current = [_snapshot(1, "first")]
    _install_snapshot_reader(monkeypatch, current)
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda snapshot: None)
    entered = asyncio.Event()

    async def operation() -> None:
        async with coordinator.lease():
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(operation())
    await entered.wait()
    assert coordinator.status()["activeLeaseCount"] == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert coordinator.status()["activeLeaseCount"] == 0


@pytest.mark.asyncio
async def test_nested_lease_is_reentrant(monkeypatch) -> None:
    current = [_snapshot(1, "first")]
    _install_snapshot_reader(monkeypatch, current)
    applied: list[ModelRuntimeSnapshot] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(applied.append)

    async with coordinator.lease() as outer:
        async with coordinator.lease() as inner:
            assert inner is outer
            assert coordinator.status()["activeLeaseCount"] == 1
        assert coordinator.status()["activeLeaseCount"] == 1

    assert coordinator.status()["activeLeaseCount"] == 0
    assert applied == [current[0]]


@pytest.mark.asyncio
async def test_failed_snapshot_is_blocked_and_error_is_sanitized(monkeypatch) -> None:
    secret = "sk-sensitive-value"
    current = [_snapshot(1, "broken", api_key=secret)]
    _install_snapshot_reader(monkeypatch, current)
    attempts = 0
    coordinator = ModelRuntimeCoordinator()

    def fail(snapshot: ModelRuntimeSnapshot) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError(f"gateway rejected {snapshot.api_key}")

    coordinator.register_applier(fail)

    with pytest.raises(ModelRuntimeReloadError) as first_error:
        await coordinator.acquire()
    with pytest.raises(ModelRuntimeReloadError) as repeated_error:
        await coordinator.acquire()
    with pytest.raises(ModelRuntimeReloadError):
        coordinator.ensure_ready_sync()

    status = coordinator.status()
    assert attempts == 1
    assert secret not in str(first_error.value)
    assert secret not in str(repeated_error.value)
    assert secret not in status["lastReloadError"]
    assert "***" in status["lastReloadError"]
    assert status["runtimeState"] == "failed"


@pytest.mark.asyncio
async def test_changed_snapshot_can_recover_after_failure(monkeypatch) -> None:
    current = [_snapshot(1, "broken")]
    _install_snapshot_reader(monkeypatch, current)
    coordinator = ModelRuntimeCoordinator()
    applied: list[str] = []

    def apply(snapshot: ModelRuntimeSnapshot) -> None:
        applied.append(snapshot.fingerprint)
        if snapshot.fingerprint == "broken":
            raise RuntimeError("broken configuration")

    coordinator.register_applier(apply)
    with pytest.raises(ModelRuntimeReloadError):
        await coordinator.acquire()

    current[0] = _snapshot(2, "fixed")
    async with coordinator.lease() as snapshot:
        assert snapshot.fingerprint == "fixed"

    assert applied == ["broken", "fixed"]
    assert coordinator.status()["runtimeState"] == "ready"

@pytest.mark.asyncio
async def test_workers_converge_independently_on_next_operation(monkeypatch) -> None:
    first = _snapshot(1, "first")
    latest = _snapshot(2, "latest")
    current = [first]
    _install_snapshot_reader(monkeypatch, current)
    worker_one_applied: list[str] = []
    worker_two_applied: list[str] = []
    worker_one = ModelRuntimeCoordinator()
    worker_two = ModelRuntimeCoordinator()
    worker_one.register_applier(
        lambda snapshot: worker_one_applied.append(snapshot.fingerprint)
    )
    worker_two.register_applier(
        lambda snapshot: worker_two_applied.append(snapshot.fingerprint)
    )

    async with worker_one.lease():
        pass
    async with worker_two.lease():
        pass

    current[0] = latest
    worker_one.note_configuration_changed()
    async with worker_one.lease() as snapshot:
        assert snapshot == latest

    assert worker_two.status()["activeRevision"] == 1
    assert worker_two.status()["desiredRevision"] == 2
    async with worker_two.lease() as snapshot:
        assert snapshot == latest

    assert worker_one_applied == ["first", "latest"]
    assert worker_two_applied == ["first", "latest"]

@pytest.mark.asyncio
async def test_disabled_hot_reload_requires_restart_after_change(monkeypatch) -> None:
    from novelvideo.model_runtime_hot_reload import ModelRuntimeRestartRequired

    current = [_snapshot(1, "first")]
    _install_snapshot_reader(monkeypatch, current)
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda snapshot: None)

    snapshot = await coordinator.acquire_without_reload()
    coordinator.release()
    assert snapshot.runtime_revision == 1

    current[0] = _snapshot(2, "second")
    with pytest.raises(ModelRuntimeRestartRequired):
        await coordinator.acquire_without_reload()

    assert coordinator.status()["runtimeState"] == "pending"

def test_disabled_sync_initialization_never_applies_changed_snapshot(monkeypatch) -> None:
    from novelvideo.model_runtime_hot_reload import ModelRuntimeRestartRequired

    current = [_snapshot(1, "first")]
    _install_snapshot_reader(monkeypatch, current)
    applied: list[int] = []
    coordinator = ModelRuntimeCoordinator()
    coordinator.register_applier(lambda snapshot: applied.append(snapshot.runtime_revision))

    coordinator.ensure_ready_without_reload_sync()
    current[0] = _snapshot(2, "second")

    with pytest.raises(ModelRuntimeRestartRequired):
        coordinator.ensure_ready_without_reload_sync()

    assert applied == [1]


def test_status_is_safe_when_gateway_configuration_is_incomplete(monkeypatch) -> None:
    from novelvideo.model_catalog import FeatureModelUnbound

    def raise_unbound():
        raise FeatureModelUnbound("Feature has no global model binding: knowledge_llm")

    monkeypatch.setattr(
        "novelvideo.model_runtime_hot_reload.build_model_runtime_snapshot",
        raise_unbound,
    )
    monkeypatch.setattr("novelvideo.model_catalog.get_runtime_revision", lambda: 11)
    coordinator = ModelRuntimeCoordinator()

    status = coordinator.status()

    assert status["desiredRevision"] == 11
    assert status["activeRevision"] is None
    assert status["runtimeState"] == "uninitialized"
    assert status["lastReloadError"] == (
        "feature_model_unbound: model gateway configuration is incomplete"
    )
    assert "knowledge_llm" not in status["lastReloadError"]


def test_status_does_not_expose_connection_secret(monkeypatch) -> None:
    from novelvideo.model_catalog import ModelConnectionMissing

    secret = "sk-sensitive-value"
    monkeypatch.setattr(
        "novelvideo.model_runtime_hot_reload.build_model_runtime_snapshot",
        lambda: (_ for _ in ()).throw(
            ModelConnectionMissing(f"connection missing: {secret}")
        ),
    )
    coordinator = ModelRuntimeCoordinator()

    status = coordinator.status()

    assert secret not in status["lastReloadError"]
    assert status["lastReloadError"].startswith("model_connection_missing:")
