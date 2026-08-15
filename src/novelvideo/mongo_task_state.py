"""MongoDB task-state manager with the legacy ``TaskStateManager`` API."""

from __future__ import annotations

import os
import uuid
from dataclasses import asdict, fields
from datetime import timedelta, timezone
from typing import List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from novelvideo.ports.mongodb import get_mongo_database, utc_now
from novelvideo.project_context import ProjectContext
from novelvideo.task_backend.queues import normalize_queue_kind
from novelvideo.task_identity import project_task_state_key, task_state_key
from novelvideo.task_state import (
    ACTIVE_PROJECT_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    TaskState,
    TaskStateManager,
    get_current_project_task_id,
    utc_now_iso,
)


_TASK_FIELDS = {field.name for field in fields(TaskState)}


class MongoTaskStateManager(TaskStateManager):
    """Persist task polling state outside the short-lived function process."""

    def __init__(self) -> None:
        super().__init__()
        collection = self._collection
        collection.create_index([("task_key", ASCENDING)], unique=True, name="task_key_unique")
        collection.create_index(
            [("project_id", ASCENDING), ("updated_at", DESCENDING)],
            name="project_tasks",
        )
        collection.create_index(
            [("username", ASCENDING), ("updated_at", DESCENDING)],
            name="user_tasks",
        )
        collection.create_index(
            [("expires_at_date", ASCENDING)], expireAfterSeconds=0, name="task_expiry"
        )

    @property
    def _collection(self):
        return get_mongo_database().task_states

    @staticmethod
    def _document_to_state(document: dict) -> TaskState:
        payload = {key: value for key, value in document.items() if key in _TASK_FIELDS}
        return TaskState(**payload)

    def _save_state(self, task_key: str, state: TaskState, ttl: int | None = None) -> None:
        document = asdict(state)
        document["_id"] = task_key
        document["task_key"] = task_key
        document["expires_at_date"] = (
            utc_now() + timedelta(seconds=ttl) if ttl is not None else None
        )
        state.expires_at = (
            document["expires_at_date"].isoformat() if document["expires_at_date"] else ""
        )
        document["expires_at"] = state.expires_at
        self._collection.replace_one({"_id": task_key}, document, upsert=True)

    def _get_by_key(self, task_key: str) -> TaskState | None:
        row = self._collection.find_one({"_id": task_key})
        if row is None:
            return None
        expires_at = row.get("expires_at_date")
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= utc_now():
                self._collection.delete_one({"_id": task_key})
                return None
        return self._document_to_state(row)

    def _recover_stale_active_tasks(self) -> None:
        """Release tasks left active when a serverless invocation is terminated."""
        try:
            stale_seconds = max(360, int(os.environ.get("VERCEL_TASK_STALE_SECONDS", "600")))
        except ValueError:
            stale_seconds = 600
        now = utc_now()
        cutoff = (now - timedelta(seconds=stale_seconds)).isoformat()
        expires_at = now + timedelta(seconds=self.COMPLETED_TTL)
        completed_at = now.isoformat()
        self._collection.update_many(
            {
                "status": {"$in": list(ACTIVE_PROJECT_TASK_STATUSES)},
                "updated_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "status": "failed",
                    "error": "The serverless invocation ended before the task completed; retry the task.",
                    "current_task": "Generation interrupted; retry available",
                    "updated_at": completed_at,
                    "completed_at": completed_at,
                    "expires_at_date": expires_at,
                    "expires_at": expires_at.isoformat(),
                }
            },
        )

    @staticmethod
    def _legacy_key(
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int | None = None,
        scope: str | None = None,
    ) -> str:
        return task_state_key(
            task_type,
            username,
            project,
            episode,
            beat_num=beat_num,
            scope=scope,
        )

    @staticmethod
    def _project_key(
        task_type: str,
        project_id: str,
        episode: int,
        beat_num: int | None = None,
        scope: str | None = None,
    ) -> str:
        return project_task_state_key(
            task_type,
            project_id,
            episode,
            beat_num=beat_num,
            scope=scope,
        )

    def create_task(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        metadata: dict | None = None,
        status: str = "pending",
    ) -> TaskState:
        now = utc_now_iso()
        state = TaskState(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            username=username,
            project=project,
            episode=episode,
            beat_num=beat_num,
            scope=scope,
            status=status,
            result=self._merge_metadata_into_result(None, metadata),
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        ttl = self.COMPLETED_TTL if status in TERMINAL_TASK_STATUSES else None
        self._save_state(
            self._legacy_key(task_type, username, project, episode, beat_num, scope),
            state,
            ttl,
        )
        return state

    def create_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        metadata: dict | None = None,
        status: str = "queued",
        queue_kind: str = "default",
    ) -> TaskState:
        now = utc_now_iso()
        state = TaskState(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            queue_kind=normalize_queue_kind(queue_kind),
            project_id=ctx.project_id,
            requester_user_id=ctx.requester_user_id,
            owner_username=ctx.owner_username,
            project_name=ctx.project_name,
            username=ctx.requester_username,
            project=ctx.project_name,
            episode=episode,
            beat_num=beat_num,
            scope=scope,
            status=status,
            result=self._merge_metadata_into_result(None, metadata),
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        ttl = self.COMPLETED_TTL if status in TERMINAL_TASK_STATUSES else None
        self._save_state(
            self._project_key(task_type, ctx.project_id, episode, beat_num, scope),
            state,
            ttl,
        )
        return state

    def reserve_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        metadata: dict | None = None,
        queue_kind: str = "default",
        project_lane_limit=None,
    ) -> tuple[TaskState, bool]:
        from novelvideo.task_backend.limits import (
            ProjectTaskLimitExceeded,
            ProjectUserTaskLimitExceeded,
            project_lane_active_limit,
            project_user_lane_active_limit,
        )

        self._recover_stale_active_tasks()
        key = self._project_key(task_type, ctx.project_id, episode, beat_num, scope)
        existing = self._get_by_key(key)
        if existing and existing.status in ACTIVE_PROJECT_TASK_STATUSES:
            return existing, False

        lane = normalize_queue_kind(queue_kind)
        limit = project_lane_limit
        if limit is None:
            limit = project_lane_active_limit(lane)
        if limit is not None:
            active = self.count_active_tasks_for_project_lane(ctx, lane)
            if active >= limit:
                raise ProjectTaskLimitExceeded(
                    project_id=ctx.project_id,
                    queue_kind=lane,
                    limit=limit,
                    active=active,
                )
        user_limit = project_user_lane_active_limit(lane)
        if user_limit is not None:
            active = self.count_active_tasks_for_project_user_lane(ctx, lane)
            if active >= user_limit:
                raise ProjectUserTaskLimitExceeded(
                    project_id=ctx.project_id,
                    requester_user_id=ctx.requester_user_id,
                    queue_kind=lane,
                    limit=user_limit,
                    active=active,
                )

        now = utc_now_iso()
        state = TaskState(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            queue_kind=lane,
            project_id=ctx.project_id,
            requester_user_id=ctx.requester_user_id,
            owner_username=ctx.owner_username,
            project_name=ctx.project_name,
            username=ctx.requester_username,
            project=ctx.project_name,
            episode=episode,
            beat_num=beat_num,
            scope=scope,
            status="submitting",
            progress=0.0,
            current_task="Task is being submitted",
            result=self._merge_metadata_into_result(None, metadata),
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        document = asdict(state)
        document.update(
            {"_id": key, "task_key": key, "expires_at_date": None, "expires_at": ""}
        )
        try:
            result = self._collection.replace_one(
                {"_id": key, "status": {"$nin": list(ACTIVE_PROJECT_TASK_STATUSES)}},
                document,
                upsert=True,
            )
            if result.matched_count == 0 and result.upserted_id is None:
                current = self._get_by_key(key)
                if current is not None:
                    return current, False
        except DuplicateKeyError:
            current = self._get_by_key(key)
            if current is not None:
                return current, False
            raise
        return state, True

    def update_progress(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        progress: float = None,
        current_task: str = None,
        logs: List[str] = None,
        metadata: dict | None = None,
    ):
        state = self.get_task(task_type, username, project, episode, beat_num, scope)
        if state is None:
            state = self.create_task(task_type, username, project, episode, beat_num, scope)
        if state.status in TERMINAL_TASK_STATUSES:
            return
        self._apply_update(
            state,
            status="running",
            progress=progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
        )
        self._save_state(
            self._legacy_key(task_type, username, project, episode, beat_num, scope), state
        )

    def update_progress_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        progress: float = None,
        current_task: str = None,
        logs: List[str] = None,
        metadata: dict | None = None,
        status: str = "running",
        expected_task_id: str | None = None,
        queue_kind: str | None = None,
    ):
        expected_task_id = expected_task_id or get_current_project_task_id() or None
        state = self.get_task_for_project(ctx, task_type, episode, beat_num, scope)
        if state is None:
            if expected_task_id:
                return
            state = self.create_task_for_project(
                ctx,
                task_type,
                episode,
                beat_num,
                scope,
                metadata,
                status,
                normalize_queue_kind(queue_kind),
            )
        if expected_task_id and state.task_id != expected_task_id:
            return
        if state.status in TERMINAL_TASK_STATUSES:
            return
        self._apply_update(
            state,
            status=status,
            progress=progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
        )
        ttl = self.COMPLETED_TTL if status in TERMINAL_TASK_STATUSES else None
        self._save_state(
            self._project_key(task_type, ctx.project_id, episode, beat_num, scope), state, ttl
        )

    def _apply_update(
        self,
        state: TaskState,
        *,
        status: str,
        progress: float | None = None,
        current_task: str | None = None,
        logs: List[str] | None = None,
        metadata: dict | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        state.status = status
        if progress is not None:
            state.progress = progress
        if current_task is not None:
            state.current_task = current_task
        if logs:
            state.logs = self._merge_logs(state.logs, logs, self.MAX_LOGS)
        state.metadata = self._merge_task_metadata(state.metadata, metadata)
        if result is not None or metadata is not None:
            state.result = self._merge_metadata_into_result(
                result if result is not None else state.result, state.metadata
            )
        if error is not None:
            state.error = error
        state.updated_at = utc_now_iso()
        if status in TERMINAL_TASK_STATUSES:
            state.completed_at = state.updated_at

    def complete_task(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        result: dict = None,
        progress: float | None = None,
        current_task: str | None = None,
        logs: List[str] | None = None,
        metadata: dict | None = None,
    ):
        state = self.get_task(task_type, username, project, episode, beat_num, scope)
        if state is None:
            state = self.create_task(task_type, username, project, episode, beat_num, scope)
        self._apply_update(
            state,
            status="completed",
            progress=1.0 if progress is None else progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
            result=result,
        )
        state.error = None
        self._save_state(
            self._legacy_key(task_type, username, project, episode, beat_num, scope),
            state,
            self.COMPLETED_TTL,
        )

    def complete_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        result: dict = None,
        progress: float | None = None,
        current_task: str | None = None,
        logs: List[str] | None = None,
        metadata: dict | None = None,
        expected_task_id: str | None = None,
        queue_kind: str | None = None,
    ):
        expected_task_id = expected_task_id or get_current_project_task_id() or None
        state = self.get_task_for_project(ctx, task_type, episode, beat_num, scope)
        if state is None:
            if expected_task_id:
                return
            state = self.create_task_for_project(
                ctx,
                task_type,
                episode,
                beat_num,
                scope,
                metadata,
                queue_kind=normalize_queue_kind(queue_kind),
            )
        if (expected_task_id and state.task_id != expected_task_id) or state.status == "cancelled":
            return
        self._apply_update(
            state,
            status="completed",
            progress=1.0 if progress is None else progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
            result=result,
        )
        state.error = None
        self._save_state(
            self._project_key(task_type, ctx.project_id, episode, beat_num, scope),
            state,
            self.COMPLETED_TTL,
        )

    def fail_task(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        error: str = None,
        progress: float | None = None,
        current_task: str | None = None,
        logs: List[str] | None = None,
        metadata: dict | None = None,
    ):
        state = self.get_task(task_type, username, project, episode, beat_num, scope)
        if state is None:
            state = self.create_task(task_type, username, project, episode, beat_num, scope)
        self._apply_update(
            state,
            status="failed",
            progress=progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
            error=error,
        )
        self._save_state(
            self._legacy_key(task_type, username, project, episode, beat_num, scope),
            state,
            self.COMPLETED_TTL,
        )

    def fail_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
        error: str = None,
        progress: float | None = None,
        current_task: str | None = None,
        logs: List[str] | None = None,
        metadata: dict | None = None,
        expected_task_id: str | None = None,
        queue_kind: str | None = None,
    ):
        expected_task_id = expected_task_id or get_current_project_task_id() or None
        state = self.get_task_for_project(ctx, task_type, episode, beat_num, scope)
        if state is None:
            if expected_task_id:
                return
            state = self.create_task_for_project(
                ctx,
                task_type,
                episode,
                beat_num,
                scope,
                metadata,
                queue_kind=normalize_queue_kind(queue_kind),
            )
        if (expected_task_id and state.task_id != expected_task_id) or state.status == "cancelled":
            return
        self._apply_update(
            state,
            status="failed",
            progress=progress,
            current_task=current_task,
            logs=logs,
            metadata=metadata,
            error=error,
        )
        self._save_state(
            self._project_key(task_type, ctx.project_id, episode, beat_num, scope),
            state,
            self.COMPLETED_TTL,
        )

    def get_task(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
    ) -> Optional[TaskState]:
        return self._get_by_key(
            self._legacy_key(task_type, username, project, episode, beat_num, scope)
        )

    def get_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
    ) -> Optional[TaskState]:
        return self._get_by_key(
            self._project_key(task_type, ctx.project_id, episode, beat_num, scope)
        )

    def delete_task(
        self,
        task_type: str,
        username: str,
        project: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
    ):
        self._collection.delete_one(
            {"_id": self._legacy_key(task_type, username, project, episode, beat_num, scope)}
        )

    def delete_task_for_project(
        self,
        ctx: ProjectContext,
        task_type: str,
        episode: int,
        beat_num: int = None,
        scope: str | None = None,
    ):
        self._collection.delete_one(
            {"_id": self._project_key(task_type, ctx.project_id, episode, beat_num, scope)}
        )

    def list_tasks_for_project(self, ctx: ProjectContext) -> List[TaskState]:
        return [
            self._document_to_state(row)
            for row in self._collection.find({"project_id": ctx.project_id}).sort(
                "updated_at", DESCENDING
            )
            if not self._expired(row)
        ]

    @staticmethod
    def _expired(row: dict) -> bool:
        expires_at = row.get("expires_at_date")
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= utc_now()

    def _count_active(self, query: dict) -> int:
        self._recover_stale_active_tasks()
        return self._collection.count_documents(
            {**query, "status": {"$in": list(ACTIVE_PROJECT_TASK_STATUSES)}}
        )

    def count_active_tasks_for_project(self, ctx: ProjectContext) -> int:
        return self._count_active({"project_id": ctx.project_id})

    def count_active_tasks_for_project_lane(
        self, ctx: ProjectContext, queue_kind: str | None
    ) -> int:
        return self._count_active(
            {"project_id": ctx.project_id, "queue_kind": normalize_queue_kind(queue_kind)}
        )

    def count_active_tasks_for_project_user_lane(
        self, ctx: ProjectContext, queue_kind: str | None
    ) -> int:
        return self._count_active(
            {
                "project_id": ctx.project_id,
                "queue_kind": normalize_queue_kind(queue_kind),
                "requester_user_id": ctx.requester_user_id,
            }
        )

    def list_tasks_for_user(self, username: str) -> List[TaskState]:
        return [
            self._document_to_state(row)
            for row in self._collection.find({"username": username}).sort(
                "updated_at", DESCENDING
            )
            if not self._expired(row)
        ]

    def count_active_tasks_for_user(self, username: str) -> int:
        return self._count_active({"username": username})


__all__ = ["MongoTaskStateManager"]
