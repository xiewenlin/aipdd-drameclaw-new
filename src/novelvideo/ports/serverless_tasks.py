"""Task backend that completes work inside the current serverless invocation."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from novelvideo.ports import get_cancellation_store
from novelvideo.ports.tasks import QueuedTask, display_metadata_for_task
from novelvideo.project_context import require_project_home_node
from novelvideo.task_backend.limits import project_lane_effective_active_limit
from novelvideo.task_backend.queues import normalize_queue_kind
from novelvideo.task_state import ACTIVE_PROJECT_TASK_STATUSES, get_task_manager


class ServerlessTaskBackend:
    """Run a generation task before returning so Vercel cannot freeze it mid-flight.

    The existing UI may continue polling the durable MongoDB task record. Unlike
    the local backend, this implementation never relies on an asyncio background
    task surviving after the HTTP response has been sent.
    """

    async def enqueue_project_task(
        self,
        ctx,
        *,
        task_type: str,
        queue_kind: str = "default",
        episode: int = 0,
        beat_num: int | None = None,
        scope: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> QueuedTask:
        require_project_home_node(ctx, operation="enqueue project task")
        manager = get_task_manager()
        payload = payload or {}
        lane = normalize_queue_kind(queue_kind)
        metadata = {
            "backend": "vercel-function",
            "queue_kind": lane,
            "project_id": ctx.project_id,
            **display_metadata_for_task(task_type, payload),
        }
        state, reserved = manager.reserve_task_for_project(
            ctx,
            task_type,
            episode,
            beat_num=beat_num,
            scope=scope,
            metadata=metadata,
            queue_kind=lane,
            project_lane_limit=project_lane_effective_active_limit(
                lane, eligible_user_count=1
            ),
        )
        if not reserved and state.status in ACTIVE_PROJECT_TASK_STATUSES:
            return QueuedTask(task_state=state, backend="vercel-function")

        manager.update_progress_for_project(
            ctx,
            task_type,
            episode,
            beat_num=beat_num,
            scope=scope,
            progress=0.0,
            current_task="Generation started",
            metadata=metadata,
            status="running",
            expected_task_id=state.task_id,
        )
        envelope = {
            "project_id": ctx.project_id,
            "requester_user_id": ctx.requester_user_id,
            "task_type": task_type,
            "episode": episode,
            "beat_num": beat_num,
            "scope": scope,
            "queue_kind": lane,
            "payload": payload,
        }

        from novelvideo.task_backend.run_core import run_project_task_core_sync

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(
                run_project_task_core_sync,
                envelope,
                ctx,
                manager,
                run_task_id=state.task_id,
                metadata=metadata,
            ),
        )
        current = manager.get_task_for_project(
            ctx, task_type, episode, beat_num=beat_num, scope=scope
        )
        return QueuedTask(task_state=current or state, backend="vercel-function")

    async def cancel_project_task(self, ctx, task_state) -> bool:
        await get_cancellation_store().request_cancel(
            project_id=ctx.project_id,
            task_type=task_state.task_type,
            episode=task_state.episode,
            task_id=task_state.task_id,
            beat_num=task_state.beat_num,
            scope=task_state.scope,
        )
        get_task_manager().update_progress_for_project(
            ctx,
            task_state.task_type,
            task_state.episode,
            beat_num=task_state.beat_num,
            scope=task_state.scope,
            progress=task_state.progress,
            current_task="Cancellation requested",
            status="cancelled",
            expected_task_id=task_state.task_id,
        )
        return True


__all__ = ["ServerlessTaskBackend"]
