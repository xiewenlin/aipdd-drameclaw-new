"""Destructive-only-to-its-own-database smoke test for the MongoDB backend."""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from ulid import ULID


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env.local", override=False)


async def smoke() -> None:
    if not os.environ.get("MONGODB_URI", "").strip():
        raise RuntimeError("MONGODB_URI is not configured")

    suffix = str(ULID()).lower()
    database_name = f"dramaclaw_codex_smoke_{suffix}"
    work_root = Path(tempfile.gettempdir()) / f"dramaclaw-smoke-{suffix}"
    os.environ["MONGODB_DB"] = database_name
    os.environ["DRAMACLAW_WORK_ROOT"] = str(work_root)
    os.environ["DB_ENCRYPTION_KEY"] = secrets.token_urlsafe(32)
    os.environ["ST_EDITION"] = "ce"

    from novelvideo.mongo_task_state import MongoTaskStateManager
    from novelvideo.mongo_workspace import hydrate_workspace, persist_workspace
    from novelvideo.ports.mongodb import (
        MongoAuthPort,
        MongoProjectAccess,
        MongoProjectRegistry,
        MongoUserModelSettings,
        ensure_mongo_indexes,
        get_mongo_client,
        project_work_root,
    )
    from novelvideo.project_context import ProjectContext

    client = get_mongo_client()
    try:
        client.admin.command("ping")
        ensure_mongo_indexes()

        auth = MongoAuthPort()
        registered = await auth.register(
            "codex_smoke_user", "correct-horse-battery-staple", email="smoke@example.invalid"
        )
        verified = await auth.verify_session(registered.raw_cookie)
        assert verified["username"] == "codex_smoke_user"
        logged_in = await auth.login(
            "codex_smoke_user", "correct-horse-battery-staple"
        )
        assert (await auth.verify_session(logged_in.raw_cookie))["id"] == registered.user.id

        settings = MongoUserModelSettings()
        config = await settings.update_user_config(
            registered.user.id,
            {"gateway_mode": "custom", "newapi_api_key": "smoke-secret-value"},
        )
        assert config["gateway_mode"] == "custom"
        assert "smoke-secret-value" not in config["newapi_api_key"]

        registry = MongoProjectRegistry()
        record = await registry.create_project(
            owner_user_id=registered.user.id,
            owner_username=registered.user.username,
            name="codex-smoke-project",
        )
        access = MongoProjectAccess()
        principals = await access.resolve_requester_principals(registered.user.id)
        assert await access.effective_project_role(record, principals) == "owner"

        Path(record.output_dir).mkdir(parents=True, exist_ok=True)
        Path(record.state_dir).mkdir(parents=True, exist_ok=True)
        Path(record.runtime_dir).mkdir(parents=True, exist_ok=True)
        (Path(record.output_dir) / "generated.txt").write_text("generated", encoding="utf-8")
        (Path(record.state_dir) / "project_config.json").write_text(
            '{"user":"codex_smoke_user"}', encoding="utf-8"
        )
        assert persist_workspace(record.id)
        shutil.rmtree(project_work_root(record.id))
        assert hydrate_workspace(record.id)
        assert (Path(record.output_dir) / "generated.txt").read_text(encoding="utf-8") == "generated"

        ctx = ProjectContext(
            project_id=record.id,
            project_name=record.name,
            owner_type=record.owner_type,
            owner_id=record.owner_id,
            owner_username=record.owner_username,
            requester_user_id=registered.user.id,
            requester_username=registered.user.username,
            requester_principals=(("user", registered.user.id),),
            effective_role="owner",
            home_node_id="local",
            output_dir=Path(record.output_dir),
            state_dir=Path(record.state_dir),
            runtime_dir=Path(record.runtime_dir),
            is_home_node=True,
        )
        tasks = MongoTaskStateManager()
        state, reserved = tasks.reserve_task_for_project(
            ctx, "smoke_generation", 1, project_lane_limit=4
        )
        assert reserved
        tasks.complete_task_for_project(
            ctx,
            "smoke_generation",
            1,
            result={"text": "ok"},
            expected_task_id=state.task_id,
        )
        completed = tasks.get_task_for_project(ctx, "smoke_generation", 1)
        assert completed and completed.status == "completed"
        assert completed.result and completed.result["text"] == "ok"

        await auth.revoke_session(logged_in.raw_cookie)
        print("MongoDB serverless smoke test passed")
    finally:
        client.drop_database(database_name)
        if work_root.exists():
            shutil.rmtree(work_root)


if __name__ == "__main__":
    asyncio.run(smoke())
