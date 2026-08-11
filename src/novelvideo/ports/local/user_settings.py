"""PostgreSQL implementation of user model settings port."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novelvideo.db import async_session
from novelvideo.db_models.user import (
    UserModelConfig,
    UserModelMapping,
    UserProviderChannel,
)
from novelvideo.utils.crypto import decrypt_value, encrypt_value

logger = logging.getLogger("novelvideo.ports.user_settings")


class PostgresUserModelSettings:
    """Per-user model gateway configuration stored in PostgreSQL."""

    async def get_user_config(self, user_id: str) -> dict:
        async with async_session() as session:
            result = await session.execute(
                select(UserModelConfig).where(UserModelConfig.user_id == user_id)
            )
            config = result.scalar_one_or_none()

            if not config:
                config = UserModelConfig(user_id=user_id)
                session.add(config)
                await session.commit()
                await session.refresh(config)

            return self._config_to_dict(config)

    async def update_user_config(self, user_id: str, config_data: dict) -> dict:
        async with async_session() as session:
            result = await session.execute(
                select(UserModelConfig).where(UserModelConfig.user_id == user_id)
            )
            config = result.scalar_one_or_none()

            if not config:
                config = UserModelConfig(user_id=user_id)
                session.add(config)

            for field in [
                "gateway_mode",
                "newapi_base_url",
                "media_relay_provider",
                "media_relay_ttl",
                "oss_endpoint",
                "oss_bucket",
                "oss_ak",
                "cognee_provider",
                "cognee_model",
                "cognee_dimensions",
                "embedding_batch_size",
                "image_default_width",
                "image_default_height",
                "image_default_style",
                "video_resolution",
                "video_generate_audio",
            ]:
                if field in config_data and config_data[field] is not None:
                    setattr(config, field, config_data[field])

            if "newapi_api_key" in config_data and config_data["newapi_api_key"] is not None:
                config.newapi_api_key = encrypt_value(config_data["newapi_api_key"])

            if "oss_sk" in config_data and config_data["oss_sk"] is not None:
                config.oss_sk = encrypt_value(config_data["oss_sk"])

            await session.commit()
            await session.refresh(config)

            return self._config_to_dict(config)

    def _config_to_dict(self, config: UserModelConfig) -> dict:
        return {
            "gateway_mode": config.gateway_mode,
            "newapi_base_url": config.newapi_base_url or "",
            "newapi_api_key": self._mask_key(decrypt_value(config.newapi_api_key)) if config.newapi_api_key else "",
            "media_relay_provider": config.media_relay_provider,
            "media_relay_ttl": config.media_relay_ttl,
            "oss_endpoint": config.oss_endpoint or "",
            "oss_bucket": config.oss_bucket or "",
            "oss_ak": config.oss_ak or "",
            "oss_sk": self._mask_key(config.oss_sk) if config.oss_sk else "",
            "cognee_provider": config.cognee_provider or "",
            "cognee_model": config.cognee_model or "",
            "cognee_dimensions": config.cognee_dimensions or "",
            "embedding_batch_size": config.embedding_batch_size or "",
            "image_default_width": config.image_default_width,
            "image_default_height": config.image_default_height,
            "image_default_style": config.image_default_style,
            "video_resolution": config.video_resolution,
            "video_generate_audio": config.video_generate_audio,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    @staticmethod
    def _mask_key(value: str | None) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    # ------------------------------------------------------------------
    # Provider channels
    # ------------------------------------------------------------------

    async def list_channels(self, user_id: str) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(UserProviderChannel)
                .where(UserProviderChannel.user_id == user_id)
                .order_by(UserProviderChannel.created_at.asc())
            )
            channels = result.scalars().all()
            return [ch.to_dict() for ch in channels]

    async def create_channel(self, user_id: str, channel_data: dict) -> dict:
        async with async_session() as session:
            api_key = channel_data.get("api_key", "")
            if api_key:
                api_key = encrypt_value(api_key)

            channel = UserProviderChannel(
                user_id=user_id,
                provider_type=channel_data["provider_type"],
                name=channel_data["name"],
                base_url=channel_data.get("base_url", ""),
                api_key=api_key,
                weight=channel_data.get("weight", 1),
                status=channel_data.get("status", "enabled"),
            )
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            return channel.to_dict()

    async def update_channel(self, user_id: str, channel_id: str, channel_data: dict) -> dict:
        async with async_session() as session:
            result = await session.execute(
                select(UserProviderChannel).where(
                    UserProviderChannel.id == channel_id,
                    UserProviderChannel.user_id == user_id,
                )
            )
            channel = result.scalar_one_or_none()
            if not channel:
                raise ValueError("Channel not found")

            for field in ["provider_type", "name", "base_url", "weight", "status"]:
                if field in channel_data and channel_data[field] is not None:
                    setattr(channel, field, channel_data[field])

            if "api_key" in channel_data and channel_data["api_key"]:
                channel.api_key = encrypt_value(channel_data["api_key"])

            await session.commit()
            await session.refresh(channel)
            return channel.to_dict()

    async def delete_channel(self, user_id: str, channel_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(UserProviderChannel).where(
                    UserProviderChannel.id == channel_id,
                    UserProviderChannel.user_id == user_id,
                )
            )
            channel = result.scalar_one_or_none()
            if not channel:
                return False
            await session.delete(channel)
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Model mappings
    # ------------------------------------------------------------------

    async def list_model_mappings(self, user_id: str) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(UserModelMapping)
                .where(UserModelMapping.user_id == user_id)
                .order_by(UserModelMapping.priority.desc())
            )
            mappings = result.scalars().all()
            return [m.to_dict() for m in mappings]

    async def update_model_mappings(self, user_id: str, mappings_data: list[dict]) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(UserModelMapping).where(UserModelMapping.user_id == user_id)
            )
            existing = {m.model_key: m for m in result.scalars().all()}

            seen_keys = set()
            for item in mappings_data:
                key = item["model_key"]
                seen_keys.add(key)
                if key in existing:
                    m = existing[key]
                    m.model_name = item.get("model_name", m.model_name)
                    m.channel_id = item.get("channel_id") or None
                    m.model_type = item.get("model_type", m.model_type)
                    m.priority = item.get("priority", 0)
                    m.status = item.get("status", "enabled")
                else:
                    m = UserModelMapping(
                        user_id=user_id,
                        model_key=key,
                        model_name=item["model_name"],
                        channel_id=item.get("channel_id") or None,
                        model_type=item["model_type"],
                        priority=item.get("priority", 0),
                        status=item.get("status", "enabled"),
                    )
                    session.add(m)

            for key, m in existing.items():
                if key not in seen_keys:
                    await session.delete(m)

            await session.commit()

            result = await session.execute(
                select(UserModelMapping)
                .where(UserModelMapping.user_id == user_id)
                .order_by(UserModelMapping.priority.desc())
            )
            return [m.to_dict() for m in result.scalars().all()]



class SQLiteUserModelSettings:
    """Per-user model gateway configuration stored in SQLite (local CE)."""

    def __init__(self) -> None:
        import asyncio
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False

    def _db_path(self):
        from pathlib import Path
        from novelvideo import config
        return Path(config.STATE_DIR) / "local" / "user_settings.db"

    async def _connect(self):
        import aiosqlite
        await self._ensure_schema()
        db = await aiosqlite.connect(self._db_path())
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        return db

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            import aiosqlite
            db_path = self._db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = await aiosqlite.connect(db_path)
            try:
                await db.executescript("""
                    CREATE TABLE IF NOT EXISTS user_model_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT UNIQUE NOT NULL,
                        gateway_mode TEXT NOT NULL DEFAULT 'official',
                        newapi_base_url TEXT,
                        newapi_api_key TEXT,
                        media_relay_provider TEXT NOT NULL DEFAULT 'aliyun_oss',
                        media_relay_ttl INTEGER NOT NULL DEFAULT 1800,
                        oss_endpoint TEXT,
                        oss_bucket TEXT,
                        oss_ak TEXT,
                        oss_sk TEXT,
                        cognee_provider TEXT,
                        cognee_model TEXT,
                        cognee_dimensions TEXT,
                        embedding_batch_size TEXT,
                        image_default_width INTEGER NOT NULL DEFAULT 1440,
                        image_default_height INTEGER NOT NULL DEFAULT 2560,
                        image_default_style TEXT NOT NULL DEFAULT 'chinese_period_drama',
                        video_resolution TEXT NOT NULL DEFAULT '720p',
                        video_generate_audio TEXT NOT NULL DEFAULT 'auto',
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS user_provider_channels (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        provider_type INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        base_url TEXT,
                        api_key TEXT,
                        weight INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'enabled',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, name)
                    );

                    CREATE TABLE IF NOT EXISTS user_model_mappings (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        model_key TEXT NOT NULL,
                        model_name TEXT NOT NULL,
                        channel_id TEXT,
                        model_type INTEGER NOT NULL,
                        priority INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'enabled',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, model_key)
                    );
                """)
                await db.commit()
            finally:
                await db.close()
            self._schema_ready = True

    def _mask_key(self, key: str | None) -> str:
        if not key:
            return ""
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "****" + key[-4:]

    async def get_user_config(self, user_id: str) -> dict:
        from datetime import datetime, timezone
        from novelvideo.utils.crypto import decrypt_value

        db = await self._connect()
        try:
            cursor = await db.execute("SELECT * FROM user_model_configs WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            await cursor.close()

            if not row:
                now_iso = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "INSERT INTO user_model_configs (user_id, updated_at) VALUES (?, ?)",
                    (user_id, now_iso),
                )
                await db.commit()
                cursor = await db.execute("SELECT * FROM user_model_configs WHERE user_id = ?", (user_id,))
                row = await cursor.fetchone()
                await cursor.close()

            return {
                "gateway_mode": row["gateway_mode"],
                "newapi_base_url": row["newapi_base_url"] or "",
                "newapi_api_key": self._mask_key(decrypt_value(row["newapi_api_key"])) if row["newapi_api_key"] else "",
                "media_relay_provider": row["media_relay_provider"],
                "media_relay_ttl": row["media_relay_ttl"],
                "oss_endpoint": row["oss_endpoint"] or "",
                "oss_bucket": row["oss_bucket"] or "",
                "oss_ak": row["oss_ak"] or "",
                "oss_sk": self._mask_key(row["oss_sk"]) if row["oss_sk"] else "",
                "cognee_provider": row["cognee_provider"] or "",
                "cognee_model": row["cognee_model"] or "",
                "cognee_dimensions": row["cognee_dimensions"] or "",
                "embedding_batch_size": row["embedding_batch_size"] or "",
                "image_default_width": row["image_default_width"],
                "image_default_height": row["image_default_height"],
                "image_default_style": row["image_default_style"],
                "video_resolution": row["video_resolution"],
                "video_generate_audio": row["video_generate_audio"],
            }
        finally:
            await db.close()

    async def update_user_config(self, user_id: str, config_data: dict) -> dict:
        from datetime import datetime, timezone
        from novelvideo.utils.crypto import encrypt_value

        db = await self._connect()
        try:
            cursor = await db.execute("SELECT * FROM user_model_configs WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            await cursor.close()

            now_iso = datetime.now(timezone.utc).isoformat()

            if not row:
                fields = ["user_id", "updated_at"]
                placeholders = ["?", "?"]
                values = [user_id, now_iso]

                for field in [
                    "gateway_mode", "newapi_base_url", "media_relay_provider",
                    "media_relay_ttl", "oss_endpoint", "oss_bucket", "oss_ak",
                    "cognee_provider", "cognee_model", "cognee_dimensions",
                    "embedding_batch_size", "image_default_width", "image_default_height",
                    "image_default_style", "video_resolution", "video_generate_audio",
                ]:
                    if field in config_data and config_data[field] is not None:
                        fields.append(field)
                        placeholders.append("?")
                        values.append(config_data[field])

                if "newapi_api_key" in config_data and config_data["newapi_api_key"] is not None:
                    fields.append("newapi_api_key")
                    placeholders.append("?")
                    values.append(encrypt_value(config_data["newapi_api_key"]))

                if "oss_sk" in config_data and config_data["oss_sk"] is not None:
                    fields.append("oss_sk")
                    placeholders.append("?")
                    values.append(encrypt_value(config_data["oss_sk"]))

                await db.execute(
                    f"INSERT INTO user_model_configs ({', '.join(fields)}) VALUES ({', '.join(placeholders)})",
                    tuple(values),
                )
                await db.commit()
            else:
                updates = []
                values = []

                for field in [
                    "gateway_mode", "newapi_base_url", "media_relay_provider",
                    "media_relay_ttl", "oss_endpoint", "oss_bucket", "oss_ak",
                    "cognee_provider", "cognee_model", "cognee_dimensions",
                    "embedding_batch_size", "image_default_width", "image_default_height",
                    "image_default_style", "video_resolution", "video_generate_audio",
                ]:
                    if field in config_data and config_data[field] is not None:
                        updates.append(f"{field} = ?")
                        values.append(config_data[field])

                if "newapi_api_key" in config_data and config_data["newapi_api_key"] is not None:
                    updates.append("newapi_api_key = ?")
                    values.append(encrypt_value(config_data["newapi_api_key"]))

                if "oss_sk" in config_data and config_data["oss_sk"] is not None:
                    updates.append("oss_sk = ?")
                    values.append(encrypt_value(config_data["oss_sk"]))

                if updates:
                    updates.append("updated_at = ?")
                    values.append(now_iso)
                    values.append(user_id)
                    await db.execute(
                        f"UPDATE user_model_configs SET {', '.join(updates)} WHERE user_id = ?",
                        tuple(values),
                    )
                    await db.commit()

            return await self.get_user_config(user_id)
        finally:
            await db.close()

    # ------------------------------------------------------------------
    # Provider channels
    # ------------------------------------------------------------------

    async def list_channels(self, user_id: str) -> list[dict]:
        from novelvideo.utils.crypto import decrypt_value

        db = await self._connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM user_provider_channels WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            result = []
            for row in rows:
                d = dict(row)
                d["api_key"] = decrypt_value(d["api_key"]) if d["api_key"] else ""
                result.append(d)
            return result
        finally:
            await db.close()

    async def create_channel(self, user_id: str, channel_data: dict) -> dict:
        from datetime import datetime, timezone
        from ulid import ULID
        from novelvideo.utils.crypto import encrypt_value, decrypt_value

        db = await self._connect()
        try:
            channel_id = str(ULID())
            now_iso = datetime.now(timezone.utc).isoformat()
            api_key = encrypt_value(channel_data.get("api_key", "")) if channel_data.get("api_key") else None

            await db.execute("""
                INSERT INTO user_provider_channels (id, user_id, provider_type, name, base_url, api_key, weight, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                channel_id, user_id,
                channel_data["provider_type"],
                channel_data["name"],
                channel_data.get("base_url", ""),
                api_key,
                channel_data.get("weight", 1),
                channel_data.get("status", "enabled"),
                now_iso, now_iso,
            ))
            await db.commit()

            cursor = await db.execute("SELECT * FROM user_provider_channels WHERE id = ?", (channel_id,))
            row = await cursor.fetchone()
            await cursor.close()
            d = dict(row)
            d["api_key"] = decrypt_value(d["api_key"]) if d["api_key"] else ""
            return d
        finally:
            await db.close()

    async def update_channel(self, user_id: str, channel_id: str, channel_data: dict) -> dict:
        from datetime import datetime, timezone
        from novelvideo.utils.crypto import encrypt_value, decrypt_value

        db = await self._connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM user_provider_channels WHERE id = ? AND user_id = ?",
                (channel_id, user_id),
            )
            row = await cursor.fetchone()
            await cursor.close()

            if not row:
                raise ValueError("Channel not found")

            updates = []
            values = []
            for field in ["provider_type", "name", "base_url", "weight", "status"]:
                if field in channel_data and channel_data[field] is not None:
                    updates.append(f"{field} = ?")
                    values.append(channel_data[field])

            if "api_key" in channel_data and channel_data["api_key"]:
                updates.append("api_key = ?")
                values.append(encrypt_value(channel_data["api_key"]))

            if updates:
                now_iso = datetime.now(timezone.utc).isoformat()
                updates.append("updated_at = ?")
                values.append(now_iso)
                values.append(channel_id)
                values.append(user_id)
                await db.execute(
                    f"UPDATE user_provider_channels SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                    tuple(values),
                )
                await db.commit()

            cursor = await db.execute(
                "SELECT * FROM user_provider_channels WHERE id = ? AND user_id = ?",
                (channel_id, user_id),
            )
            row = await cursor.fetchone()
            await cursor.close()
            d = dict(row)
            d["api_key"] = decrypt_value(d["api_key"]) if d["api_key"] else ""
            return d
        finally:
            await db.close()

    async def delete_channel(self, user_id: str, channel_id: str) -> bool:
        db = await self._connect()
        try:
            cursor = await db.execute(
                "DELETE FROM user_provider_channels WHERE id = ? AND user_id = ?",
                (channel_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()

    # ------------------------------------------------------------------
    # Model mappings
    # ------------------------------------------------------------------

    async def list_model_mappings(self, user_id: str) -> list[dict]:
        db = await self._connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM user_model_mappings WHERE user_id = ? ORDER BY priority DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def update_model_mappings(self, user_id: str, mappings_data: list[dict]) -> list[dict]:
        from datetime import datetime, timezone
        from ulid import ULID

        db = await self._connect()
        try:
            cursor = await db.execute(
                "SELECT * FROM user_model_mappings WHERE user_id = ?",
                (user_id,),
            )
            existing_rows = await cursor.fetchall()
            await cursor.close()
            existing = {row["model_key"]: row for row in existing_rows}

            now_iso = datetime.now(timezone.utc).isoformat()
            seen_keys = set()

            for item in mappings_data:
                key = item["model_key"]
                seen_keys.add(key)
                if key in existing:
                    row = existing[key]
                    await db.execute("""
                        UPDATE user_model_mappings
                        SET model_name = ?, channel_id = ?, model_type = ?, priority = ?, status = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                    """, (
                        item.get("model_name", row["model_name"]),
                        item.get("channel_id") or None,
                        item.get("model_type", row["model_type"]),
                        item.get("priority", 0),
                        item.get("status", "enabled"),
                        now_iso,
                        row["id"], user_id,
                    ))
                else:
                    mapping_id = str(ULID())
                    await db.execute("""
                        INSERT INTO user_model_mappings (id, user_id, model_key, model_name, channel_id, model_type, priority, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        mapping_id, user_id, key,
                        item["model_name"],
                        item.get("channel_id") or None,
                        item["model_type"],
                        item.get("priority", 0),
                        item.get("status", "enabled"),
                        now_iso, now_iso,
                    ))

            for key, row in existing.items():
                if key not in seen_keys:
                    await db.execute("DELETE FROM user_model_mappings WHERE id = ?", (row["id"],))

            await db.commit()

            return await self.list_model_mappings(user_id)
        finally:
            await db.close()