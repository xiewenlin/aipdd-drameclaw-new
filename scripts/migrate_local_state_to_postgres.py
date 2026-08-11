"""Migrate CE registry/auth/settings state from SQLite to PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from novelvideo import config
from novelvideo.db import async_session, engine
from novelvideo.db_models.project import Project
from novelvideo.db_models.user import (
    User,
    UserModelConfig,
    UserModelMapping,
    UserProviderChannel,
    UserSession,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _rows(path: Path, table: str) -> list[dict]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if not exists:
            return []
        return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
    finally:
        connection.close()


def _copy_fields(target, row: dict, fields: Iterable[str]) -> None:
    for field in fields:
        if field in row:
            setattr(target, field, row[field])


class MigrationReport:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.skipped: list[str] = []

    def add(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def skip(self, message: str) -> None:
        self.skipped.append(message)

    def print(self) -> None:
        for key in sorted(self.counts):
            print(f"{key}: {self.counts[key]}")
        for message in self.skipped:
            print(f"SKIPPED: {message}")


async def _migrate_users(
    auth_path: Path,
    report: MigrationReport,
) -> dict[str, str]:
    source_users = _rows(auth_path, "users")
    id_map: dict[str, str] = {}
    async with async_session() as session:
        for row in source_users:
            result = await session.execute(select(User).where(User.username == row["username"]))
            user = result.scalar_one_or_none()
            if user is None:
                email = row.get("email") or None
                if email:
                    email_result = await session.execute(select(User.id).where(User.email == email))
                    if email_result.scalar_one_or_none() is not None:
                        report.skip(f"user {row['username']}: email already belongs to another user")
                        email = None
                user = User(
                    username=row["username"],
                    email=email,
                    password_hash=row["password_hash"],
                    role=row.get("role") or "user",
                    status=row.get("status") or "active",
                    display_name=row.get("display_name"),
                    avatar_url=row.get("avatar_url"),
                    created_at=_parse_datetime(row.get("created_at")),
                    updated_at=_parse_datetime(row.get("updated_at")),
                    last_login_at=_parse_datetime(row.get("last_login_at")),
                )
                session.add(user)
                await session.flush()
                report.add("users_created")
            else:
                user.password_hash = row["password_hash"]
                user.role = row.get("role") or user.role
                user.status = row.get("status") or user.status
                user.display_name = row.get("display_name") or user.display_name
                user.avatar_url = row.get("avatar_url") or user.avatar_url
                user.last_login_at = _parse_datetime(row.get("last_login_at")) or user.last_login_at
                report.add("users_updated")
            id_map[str(row["id"])] = str(user.id)
        await session.commit()

    source_sessions = _rows(auth_path, "user_sessions")
    async with async_session() as session:
        for row in source_sessions:
            user_id = id_map.get(str(row["user_id"]))
            if not user_id:
                report.skip(f"session {row['id']}: source user not mapped")
                continue
            result = await session.execute(
                select(UserSession.id).where(UserSession.session_token == row["session_token"])
            )
            if result.scalar_one_or_none() is not None:
                report.add("sessions_existing")
                continue
            session.add(
                UserSession(
                    user_id=user_id,
                    session_token=row["session_token"],
                    device_info=row.get("device_info"),
                    ip_address=row.get("ip_address"),
                    user_agent=row.get("user_agent"),
                    expires_at=_parse_datetime(row.get("expires_at")),
                    created_at=_parse_datetime(row.get("created_at")),
                    last_seen_at=_parse_datetime(row.get("last_seen_at")),
                    revoked_at=_parse_datetime(row.get("revoked_at")),
                )
            )
            report.add("sessions_created")
        await session.commit()
    return id_map


async def _resolve_user_id(source_id: str, id_map: dict[str, str]) -> str | None:
    mapped = id_map.get(source_id)
    if mapped:
        return mapped
    try:
        uuid.UUID(source_id)
    except ValueError:
        return None
    async with async_session() as session:
        return source_id if await session.get(User, source_id) else None


async def _migrate_settings(
    settings_path: Path,
    id_map: dict[str, str],
    report: MigrationReport,
) -> None:
    config_fields = (
        "gateway_mode",
        "newapi_base_url",
        "newapi_api_key",
        "media_relay_provider",
        "media_relay_ttl",
        "oss_endpoint",
        "oss_bucket",
        "oss_ak",
        "oss_sk",
        "cognee_provider",
        "cognee_model",
        "cognee_dimensions",
        "embedding_batch_size",
        "image_default_width",
        "image_default_height",
        "image_default_style",
        "video_resolution",
        "video_generate_audio",
    )
    async with async_session() as session:
        for row in _rows(settings_path, "user_model_configs"):
            user_id = await _resolve_user_id(str(row["user_id"]), id_map)
            if not user_id:
                report.skip(f"model config {row['user_id']}: source user not mapped")
                continue
            config_row = await session.get(UserModelConfig, user_id)
            if config_row is None:
                config_row = UserModelConfig(user_id=user_id)
                session.add(config_row)
                report.add("model_configs_created")
            else:
                report.add("model_configs_updated")
            _copy_fields(config_row, row, config_fields)
            config_row.updated_at = _parse_datetime(row.get("updated_at")) or datetime.now(timezone.utc)
        await session.commit()

    channel_map: dict[str, str] = {}
    async with async_session() as session:
        for row in _rows(settings_path, "user_provider_channels"):
            user_id = await _resolve_user_id(str(row["user_id"]), id_map)
            if not user_id:
                report.skip(f"channel {row['id']}: source user not mapped")
                continue
            result = await session.execute(
                select(UserProviderChannel).where(
                    UserProviderChannel.user_id == user_id,
                    UserProviderChannel.name == row["name"],
                )
            )
            channel = result.scalar_one_or_none()
            if channel is None:
                channel = UserProviderChannel(user_id=user_id, provider_type=row["provider_type"], name=row["name"])
                session.add(channel)
                await session.flush()
                report.add("channels_created")
            else:
                report.add("channels_updated")
            _copy_fields(channel, row, ("provider_type", "name", "base_url", "api_key", "weight", "status"))
            channel.created_at = _parse_datetime(row.get("created_at")) or channel.created_at
            channel.updated_at = _parse_datetime(row.get("updated_at")) or datetime.now(timezone.utc)
            channel_map[str(row["id"])] = str(channel.id)
        await session.commit()

    async with async_session() as session:
        for row in _rows(settings_path, "user_model_mappings"):
            user_id = await _resolve_user_id(str(row["user_id"]), id_map)
            if not user_id:
                report.skip(f"model mapping {row['id']}: source user not mapped")
                continue
            source_channel_id = row.get("channel_id")
            channel_id = channel_map.get(str(source_channel_id)) if source_channel_id else None
            result = await session.execute(
                select(UserModelMapping).where(
                    UserModelMapping.user_id == user_id,
                    UserModelMapping.model_key == row["model_key"],
                )
            )
            mapping = result.scalar_one_or_none()
            if mapping is None:
                mapping = UserModelMapping(
                    user_id=user_id,
                    model_key=row["model_key"],
                    model_name=row["model_name"],
                    model_type=row["model_type"],
                )
                session.add(mapping)
                report.add("model_mappings_created")
            else:
                report.add("model_mappings_updated")
            _copy_fields(mapping, row, ("model_name", "model_type", "priority", "status"))
            mapping.channel_id = channel_id
            mapping.created_at = _parse_datetime(row.get("created_at")) or mapping.created_at
            mapping.updated_at = _parse_datetime(row.get("updated_at")) or datetime.now(timezone.utc)
        await session.commit()


async def _migrate_projects(
    projects_path: Path,
    id_map: dict[str, str],
    report: MigrationReport,
) -> None:
    async with async_session() as session:
        for row in _rows(projects_path, "projects"):
            owner_id = id_map.get(str(row["owner_id"]))
            if not owner_id:
                result = await session.execute(
                    select(User.id).where(User.username == row["owner_username"])
                )
                resolved = result.scalar_one_or_none()
                owner_id = str(resolved) if resolved else None
            if not owner_id:
                report.skip(f"project {row['id']}: owner {row['owner_username']} not found")
                continue
            existing = await session.get(Project, str(row["id"]))
            if existing is None:
                duplicate = await session.execute(
                    select(Project.id).where(
                        Project.owner_type == row["owner_type"],
                        Project.owner_id == owner_id,
                        Project.name == row["name"],
                    )
                )
                if duplicate.scalar_one_or_none() is not None:
                    report.skip(f"project {row['id']}: owner/name already exists")
                    continue
                existing = Project(id=str(row["id"]))
                session.add(existing)
                report.add("projects_created")
            else:
                report.add("projects_updated")
            _copy_fields(
                existing,
                row,
                (
                    "owner_type",
                    "owner_username",
                    "name",
                    "home_node_id",
                    "output_dir",
                    "state_dir",
                    "runtime_dir",
                    "status",
                ),
            )
            existing.owner_id = owner_id
            existing.created_at = _parse_datetime(row.get("created_at")) or datetime.now(timezone.utc)
            existing.updated_at = _parse_datetime(row.get("updated_at")) or datetime.now(timezone.utc)
            existing.purged_at = _parse_datetime(row.get("purged_at"))
        await session.commit()


async def migrate(state_dir: Path, strict: bool) -> int:
    report = MigrationReport()
    local_dir = state_dir / "local"
    async with engine.begin() as connection:
        await connection.run_sync(Project.__table__.create, checkfirst=True)
    id_map = await _migrate_users(local_dir / "auth.db", report)
    await _migrate_settings(local_dir / "user_settings.db", id_map, report)
    await _migrate_projects(local_dir / "projects.db", id_map, report)
    report.print()
    if strict and report.skipped:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=Path(config.STATE_DIR))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    return asyncio.run(migrate(args.state_dir, args.strict))


if __name__ == "__main__":
    raise SystemExit(main())
