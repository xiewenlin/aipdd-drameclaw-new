"""MongoDB-backed ports used by the stateless Vercel deployment.

The application still materialises a project into a temporary directory while a
generation request is running. Durable control-plane data lives in MongoDB and
the temporary project workspace is persisted separately by ``mongo_workspace``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from threading import Lock
from typing import Any, Callable, TypeVar

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from ulid import ULID

from novelvideo.ports.auth_contract import (
    AgentAuthenticatedUser,
    AgentSessionToken,
    AuthenticatedUser,
    AuthError,
    AuthFailureReason,
    LoginResult,
)
from novelvideo.ports.project import Principal, ProjectRecord
from novelvideo.ports.tasks import cancel_key


T = TypeVar("T")
_CLIENT: MongoClient | None = None
_CLIENT_LOCK = Lock()
_INDEX_LOCK = Lock()
_INDEXES_READY = False
_PASSWORD_ITERATIONS = 390_000
_SESSION_TTL_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def get_mongo_client() -> MongoClient:
    """Return one thread-safe client per warm function instance."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            uri = os.environ.get("MONGODB_URI", "").strip()
            if not uri:
                raise RuntimeError("MONGODB_URI is required for the MongoDB backend")
            _CLIENT = MongoClient(
                uri,
                appname="dramaclaw-vercel",
                connectTimeoutMS=10_000,
                serverSelectionTimeoutMS=10_000,
                retryWrites=True,
                tz_aware=True,
            )
    return _CLIENT


def get_mongo_database() -> Database:
    database_name = os.environ.get("MONGODB_DB", "dramaclaw").strip() or "dramaclaw"
    return get_mongo_client()[database_name]


def ensure_mongo_indexes() -> None:
    global _INDEXES_READY
    if _INDEXES_READY:
        return
    with _INDEX_LOCK:
        if _INDEXES_READY:
            return
        db = get_mongo_database()
        db.users.create_index([("username", ASCENDING)], unique=True, name="username_unique")
        db.users.create_index(
            [("email", ASCENDING)],
            unique=True,
            sparse=True,
            name="email_unique",
        )
        db.user_sessions.create_index(
            [("session_token", ASCENDING)], unique=True, name="session_token_unique"
        )
        db.user_sessions.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="session_expiry"
        )
        db.user_sessions.create_index(
            [("user_id", ASCENDING), ("last_seen_at", DESCENDING)],
            name="user_sessions",
        )
        db.agent_sessions.create_index(
            [("token", ASCENDING)], unique=True, name="agent_token_unique"
        )
        db.agent_sessions.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="agent_expiry"
        )
        db.projects.create_index(
            [("owner_type", ASCENDING), ("owner_id", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="owner_project_unique",
        )
        db.projects.create_index(
            [("owner_id", ASCENDING), ("updated_at", DESCENDING)],
            name="owner_projects",
        )
        db.user_model_configs.create_index(
            [("user_id", ASCENDING)], unique=True, name="user_config_unique"
        )
        db.provider_channels.create_index(
            [("user_id", ASCENDING), ("name", ASCENDING)],
            unique=True,
            name="user_channel_unique",
        )
        db.model_mappings.create_index(
            [("user_id", ASCENDING), ("model_key", ASCENDING)],
            unique=True,
            name="user_model_mapping_unique",
        )
        db.task_cancellations.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="cancel_expiry"
        )
        _INDEXES_READY = True


async def _run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(partial(func, *args, **kwargs))


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(_PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt_text.encode("ascii")),
            int(rounds),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def _new_session_document(
    user_id: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_info: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "_id": str(ULID()),
        "user_id": user_id,
        "session_token": secrets.token_urlsafe(48),
        "device_info": device_info,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "expires_at": now + timedelta(days=_SESSION_TTL_DAYS),
        "created_at": now,
        "last_seen_at": now,
        "revoked_at": None,
    }


def _authenticated_user(document: dict[str, Any]) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=str(document["_id"]),
        username=str(document["username"]),
        role=str(document.get("role") or "user"),
        status=str(document.get("status") or "active"),
    )


class MongoAuthPort:
    async def verify_session(self, raw_cookie: str | None) -> dict:
        if not raw_cookie:
            raise AuthError(AuthFailureReason.MISSING, "Missing session cookie")

        def operation() -> dict:
            ensure_mongo_indexes()
            db = get_mongo_database()
            session = db.user_sessions.find_one({"session_token": raw_cookie})
            if session is None:
                raise AuthError(AuthFailureReason.INVALID, "Session not found")
            if session.get("revoked_at") is not None:
                raise AuthError(AuthFailureReason.REVOKED, "Session revoked")
            if session["expires_at"] < utc_now():
                raise AuthError(AuthFailureReason.EXPIRED, "Session expired")
            user = db.users.find_one({"_id": session["user_id"]})
            if user is None:
                raise AuthError(AuthFailureReason.INVALID, "User not found")
            if user.get("status") != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "User suspended")
            db.user_sessions.update_one(
                {"_id": session["_id"]}, {"$set": {"last_seen_at": utc_now()}}
            )
            return _authenticated_user(user).to_legacy_dict()

        return await _run_sync(operation)

    async def revoke_session(self, raw_cookie: str) -> None:
        if not raw_cookie:
            return
        await _run_sync(
            get_mongo_database().user_sessions.update_one,
            {"session_token": raw_cookie},
            {"$set": {"revoked_at": utc_now()}},
        )

    async def login(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_info: str | None = None,
    ) -> LoginResult:
        def operation() -> LoginResult:
            ensure_mongo_indexes()
            db = get_mongo_database()
            user = db.users.find_one({"username": username})
            if user is None or not _verify_password(password, str(user.get("password_hash") or "")):
                raise AuthError(AuthFailureReason.INVALID, "Invalid username or password")
            if user.get("status") != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "Account is not active")
            now = utc_now()
            db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now}})
            session = _new_session_document(
                str(user["_id"]),
                ip_address=ip_address,
                user_agent=user_agent,
                device_info=device_info,
            )
            db.user_sessions.insert_one(session)
            return LoginResult(
                user=_authenticated_user(user),
                session_id=str(session["_id"]),
                raw_cookie=str(session["session_token"]),
            )

        return await _run_sync(operation)

    async def register(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> LoginResult:
        def operation() -> LoginResult:
            ensure_mongo_indexes()
            db = get_mongo_database()
            now = utc_now()
            user = {
                "_id": str(ULID()),
                "username": username,
                "email": email or None,
                "password_hash": _hash_password(password),
                "role": "user",
                "status": "active",
                "display_name": display_name or username,
                "created_at": now,
                "updated_at": now,
                "last_login_at": now,
            }
            if not email:
                user.pop("email")
            try:
                db.users.insert_one(user)
            except DuplicateKeyError as exc:
                message = "Email already registered" if email and db.users.find_one({"email": email}) else "Username already taken"
                raise AuthError(AuthFailureReason.INVALID, message) from exc
            db.user_model_configs.update_one(
                {"user_id": user["_id"]},
                {"$setOnInsert": _default_user_config(user["_id"], now)},
                upsert=True,
            )
            session = _new_session_document(str(user["_id"]))
            db.user_sessions.insert_one(session)
            return LoginResult(
                user=_authenticated_user(user),
                session_id=str(session["_id"]),
                raw_cookie=str(session["session_token"]),
            )

        return await _run_sync(operation)

    async def list_user_sessions(self, user_id: str) -> list[dict]:
        def operation() -> list[dict]:
            rows = get_mongo_database().user_sessions.find(
                {"user_id": user_id}, {"session_token": 0}
            ).sort("last_seen_at", DESCENDING)
            return [_json_document(row) for row in rows]

        return await _run_sync(operation)

    async def revoke_user_session(self, user_id: str, session_id: str) -> bool:
        result = await _run_sync(
            get_mongo_database().user_sessions.update_one,
            {"_id": session_id, "user_id": user_id},
            {"$set": {"revoked_at": utc_now()}},
        )
        return result.matched_count > 0


class MongoAuthSession:
    async def create_agent_session(
        self,
        *,
        username: str,
        scopes,
        ttl_seconds: int | None = None,
        agent_kind: str = "agent",
        worker_id: str | None = None,
        parent_session_id: str | None = None,
        current_scope_kind: str = "home",
        current_project_id: str | None = None,
        metadata: dict | None = None,
    ) -> AgentSessionToken:
        def operation() -> AgentSessionToken:
            ensure_mongo_indexes()
            db = get_mongo_database()
            user = db.users.find_one({"username": username})
            if user is None:
                raise AuthError(AuthFailureReason.INVALID, "User not found")
            ttl = int(ttl_seconds or 2 * 3600)
            session_id = str(ULID())
            token_value = f"agent-{secrets.token_urlsafe(42)}"
            normalized_scopes = tuple(scopes or ())
            expires_at = utc_now() + timedelta(seconds=ttl)
            db.agent_sessions.insert_one(
                {
                    "_id": session_id,
                    "token": token_value,
                    "user_id": str(user["_id"]),
                    "username": username,
                    "role": user.get("role") or "user",
                    "agent_kind": agent_kind,
                    "worker_id": worker_id,
                    "scopes": list(normalized_scopes),
                    "current_scope_kind": current_scope_kind,
                    "current_project_id": current_project_id,
                    "parent_session_id": parent_session_id,
                    "metadata": metadata or {},
                    "expires_at": expires_at,
                    "created_at": utc_now(),
                }
            )
            return AgentSessionToken(
                value=token_value,
                session_id=session_id,
                user=username,
                scopes=normalized_scopes,
                exp=int(expires_at.timestamp()),
                worker_id=worker_id or "",
                agent_kind=agent_kind,
            )

        return await _run_sync(operation)

    async def verify_agent_session(self, token: str) -> dict:
        def operation() -> dict:
            row = get_mongo_database().agent_sessions.find_one({"token": token})
            if row is None or row["expires_at"] < utc_now():
                raise AuthError(AuthFailureReason.INVALID, "agent session not found")
            return AgentAuthenticatedUser(
                id=str(row["user_id"]),
                username=str(row["username"]),
                role=str(row.get("role") or "user"),
                agent_session_id=str(row["_id"]),
                agent_kind=str(row.get("agent_kind") or "agent"),
                worker_id=row.get("worker_id"),
                scopes=tuple(row.get("scopes") or ()),
                current_scope_kind=str(row.get("current_scope_kind") or "home"),
                current_project_id=row.get("current_project_id"),
                parent_session_id=row.get("parent_session_id"),
            ).to_legacy_dict()

        return await _run_sync(operation)

    async def update_agent_session_scope(
        self,
        token_value: str,
        *,
        scope_kind: str,
        project_id: str | None,
    ) -> None:
        result = await _run_sync(
            get_mongo_database().agent_sessions.update_one,
            {"token": token_value, "expires_at": {"$gt": utc_now()}},
            {"$set": {"current_scope_kind": scope_kind, "current_project_id": project_id}},
        )
        if result.matched_count == 0:
            raise AuthError(AuthFailureReason.INVALID, "agent session not found")

    async def revoke_agent_session(self, token_value: str) -> None:
        await _run_sync(get_mongo_database().agent_sessions.delete_one, {"token": token_value})


def serverless_work_root() -> Path:
    configured = os.environ.get("DRAMACLAW_WORK_ROOT", "").strip()
    root = Path(configured) if configured else Path(tempfile.gettempdir()) / "dramaclaw"
    return root.resolve()


def project_work_root(project_id: str) -> Path:
    return serverless_work_root() / "projects" / project_id


def _project_record(document: dict[str, Any]) -> ProjectRecord:
    return ProjectRecord(
        id=str(document["_id"]),
        owner_type=str(document.get("owner_type") or "user"),
        owner_id=str(document["owner_id"]),
        owner_username=str(document["owner_username"]),
        name=str(document["name"]),
        home_node_id=str(document.get("home_node_id") or "local"),
        output_dir=str(document["output_dir"]),
        state_dir=str(document["state_dir"]),
        runtime_dir=str(document["runtime_dir"]),
        status=str(document.get("status") or "active"),
        created_at=_iso(document.get("created_at")),
        updated_at=_iso(document.get("updated_at")),
        purged_at=_iso(document.get("purged_at")) or None,
    )


class MongoProjectRegistry:
    async def get_project(self, project_id: str) -> ProjectRecord | None:
        row = await _run_sync(get_mongo_database().projects.find_one, {"_id": project_id})
        return _project_record(row) if row else None

    async def get_project_by_owner_name(
        self, owner_user_id: str, name: str
    ) -> ProjectRecord | None:
        row = await _run_sync(
            get_mongo_database().projects.find_one,
            {
                "owner_type": "user",
                "owner_id": owner_user_id,
                "name": name,
                "purged_at": None,
            },
        )
        return _project_record(row) if row else None

    async def create_project(
        self,
        *,
        owner_user_id: str,
        owner_username: str,
        name: str,
        home_node_id: str | None = None,
        output_dir: str | None = None,
        state_dir: str | None = None,
        runtime_dir: str | None = None,
    ) -> ProjectRecord:
        def operation() -> ProjectRecord:
            ensure_mongo_indexes()
            project_id = str(ULID())
            root = project_work_root(project_id)
            now = utc_now()
            document = {
                "_id": project_id,
                "owner_type": "user",
                "owner_id": owner_user_id,
                "owner_username": owner_username,
                "name": name,
                "home_node_id": "local",
                "output_dir": output_dir or str(root / "output"),
                "state_dir": state_dir or str(root / "state"),
                "runtime_dir": runtime_dir or str(root / "runtime"),
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "purged_at": None,
                "workspace_revision": None,
                "workspace_file_id": None,
            }
            try:
                get_mongo_database().projects.insert_one(document)
            except DuplicateKeyError as exc:
                raise ValueError(f"Project '{name}' already exists") from exc
            return _project_record(document)

        return await _run_sync(operation)

    async def list_accessible_projects(
        self, principals: list[tuple[str, str]]
    ) -> list[ProjectRecord]:
        user_ids = [value for kind, value in principals if kind == "user"]
        if not user_ids:
            return []

        def operation() -> list[ProjectRecord]:
            rows = get_mongo_database().projects.find(
                {"owner_type": "user", "owner_id": {"$in": user_ids}, "purged_at": None}
            ).sort("updated_at", DESCENDING)
            return [_project_record(row) for row in rows]

        return await _run_sync(operation)

    async def update_project_status(
        self, project_id: str, status: str
    ) -> ProjectRecord | None:
        row = await _run_sync(
            get_mongo_database().projects.find_one_and_update,
            {"_id": project_id, "purged_at": None},
            {"$set": {"status": status, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return _project_record(row) if row else None

    async def mark_project_purged(self, project_id: str) -> ProjectRecord | None:
        now = utc_now()
        row = await _run_sync(
            get_mongo_database().projects.find_one_and_update,
            {"_id": project_id},
            {"$set": {"status": "deleted", "updated_at": now, "purged_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _project_record(row) if row else None

    async def delete_uncommitted_project(self, project_id: str) -> None:
        await _run_sync(get_mongo_database().projects.delete_one, {"_id": project_id})

    async def delete_project_home(self, project_id: str) -> None:
        from novelvideo.mongo_workspace import delete_workspace

        await _run_sync(delete_workspace, project_id)

    async def resolve_username_by_user_id(self, user_id: str) -> str | None:
        row = await _run_sync(get_mongo_database().users.find_one, {"_id": user_id})
        return str(row["username"]) if row else None

    async def resolve_user_id_by_username(self, username: str) -> str | None:
        row = await _run_sync(get_mongo_database().users.find_one, {"username": username})
        return str(row["_id"]) if row else None


class MongoProjectAccess:
    async def resolve_requester_principals(self, user_id: str) -> list[Principal]:
        return [Principal("user", user_id)] if user_id else []

    async def effective_project_role(
        self, project: ProjectRecord, principals: list[Principal]
    ) -> str | None:
        if any(p.type == project.owner_type and p.id == project.owner_id for p in principals):
            return "owner"
        return None

    async def count_project_task_eligible_users(
        self, *, project_id: str, owner_type: str, owner_id: str
    ) -> int:
        _ = project_id, owner_type, owner_id
        return 1


_CONFIG_DEFAULTS: dict[str, Any] = {
    "gateway_mode": "official",
    "newapi_base_url": "",
    "media_relay_provider": "aliyun_oss",
    "media_relay_ttl": 1800,
    "oss_endpoint": "",
    "oss_bucket": "",
    "oss_ak": "",
    "cognee_provider": "",
    "cognee_model": "",
    "cognee_dimensions": "",
    "embedding_batch_size": "",
    "image_default_width": 1440,
    "image_default_height": 2560,
    "image_default_style": "chinese_period_drama",
    "video_resolution": "720p",
    "video_generate_audio": "auto",
}
_CONFIG_FIELDS = tuple(_CONFIG_DEFAULTS)


def _default_user_config(user_id: str, now: datetime | None = None) -> dict[str, Any]:
    return {"user_id": user_id, **_CONFIG_DEFAULTS, "updated_at": now or utc_now()}


def _mask_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _encrypt(value: str) -> str:
    from novelvideo.utils.crypto import encrypt_value

    return encrypt_value(value)


def _decrypt(value: str | None) -> str:
    if not value:
        return ""
    from novelvideo.utils.crypto import decrypt_value

    return decrypt_value(value)


def _public_config(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: row.get(key, default) for key, default in _CONFIG_DEFAULTS.items()}
    result["newapi_api_key"] = _mask_key(_decrypt(row.get("newapi_api_key")))
    result["oss_sk"] = _mask_key(_decrypt(row.get("oss_sk")))
    result["updated_at"] = _iso(row.get("updated_at")) or None
    return result


class MongoUserModelSettings:
    async def get_user_config(self, user_id: str) -> dict:
        def operation() -> dict:
            ensure_mongo_indexes()
            db = get_mongo_database()
            row = db.user_model_configs.find_one_and_update(
                {"user_id": user_id},
                {"$setOnInsert": _default_user_config(user_id)},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return _public_config(row)

        return await _run_sync(operation)

    async def update_user_config(self, user_id: str, config: dict) -> dict:
        def operation() -> dict:
            updates = {key: config[key] for key in _CONFIG_FIELDS if config.get(key) is not None}
            for secret_field in ("newapi_api_key", "oss_sk"):
                value = config.get(secret_field)
                if value and "*" not in str(value) and "..." not in str(value):
                    updates[secret_field] = _encrypt(str(value))
            updates["updated_at"] = utc_now()
            row = get_mongo_database().user_model_configs.find_one_and_update(
                {"user_id": user_id},
                {"$set": updates, "$setOnInsert": {"user_id": user_id}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return _public_config(row)

        return await _run_sync(operation)

    async def list_channels(self, user_id: str) -> list[dict]:
        def operation() -> list[dict]:
            rows = get_mongo_database().provider_channels.find({"user_id": user_id}).sort(
                "created_at", ASCENDING
            )
            result = []
            for row in rows:
                row["id"] = str(row.pop("_id"))
                row["api_key"] = _decrypt(row.get("api_key"))
                result.append(_json_document(row))
            return result

        return await _run_sync(operation)

    async def create_channel(self, user_id: str, channel: dict) -> dict:
        def operation() -> dict:
            now = utc_now()
            row = {
                "_id": str(ULID()),
                "user_id": user_id,
                "provider_type": channel["provider_type"],
                "name": channel["name"],
                "base_url": channel.get("base_url", ""),
                "api_key": _encrypt(str(channel.get("api_key") or "")) if channel.get("api_key") else "",
                "weight": channel.get("weight", 1),
                "status": channel.get("status", "enabled"),
                "created_at": now,
                "updated_at": now,
            }
            get_mongo_database().provider_channels.insert_one(row)
            public = dict(row)
            public["id"] = str(public.pop("_id"))
            public["api_key"] = _decrypt(public.get("api_key"))
            return _json_document(public)

        return await _run_sync(operation)

    async def update_channel(
        self, user_id: str, channel_id: str, channel: dict
    ) -> dict:
        def operation() -> dict:
            updates = {
                key: channel[key]
                for key in ("provider_type", "name", "base_url", "weight", "status")
                if channel.get(key) is not None
            }
            if channel.get("api_key"):
                updates["api_key"] = _encrypt(str(channel["api_key"]))
            updates["updated_at"] = utc_now()
            row = get_mongo_database().provider_channels.find_one_and_update(
                {"_id": channel_id, "user_id": user_id},
                {"$set": updates},
                return_document=ReturnDocument.AFTER,
            )
            if row is None:
                raise ValueError("Channel not found")
            row["id"] = str(row.pop("_id"))
            row["api_key"] = _decrypt(row.get("api_key"))
            return _json_document(row)

        return await _run_sync(operation)

    async def delete_channel(self, user_id: str, channel_id: str) -> bool:
        result = await _run_sync(
            get_mongo_database().provider_channels.delete_one,
            {"_id": channel_id, "user_id": user_id},
        )
        return result.deleted_count > 0

    async def list_model_mappings(self, user_id: str) -> list[dict]:
        def operation() -> list[dict]:
            rows = get_mongo_database().model_mappings.find({"user_id": user_id}).sort(
                "priority", DESCENDING
            )
            result = []
            for row in rows:
                row["id"] = str(row.pop("_id"))
                result.append(_json_document(row))
            return result

        return await _run_sync(operation)

    async def update_model_mappings(
        self, user_id: str, mappings: list[dict]
    ) -> list[dict]:
        def operation() -> list[dict]:
            db = get_mongo_database()
            keys = []
            now = utc_now()
            for mapping in mappings:
                key = str(mapping["model_key"])
                keys.append(key)
                db.model_mappings.update_one(
                    {"user_id": user_id, "model_key": key},
                    {
                        "$set": {
                            "model_name": mapping["model_name"],
                            "channel_id": mapping.get("channel_id") or None,
                            "model_type": mapping["model_type"],
                            "priority": mapping.get("priority", 0),
                            "status": mapping.get("status", "enabled"),
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "_id": str(ULID()),
                            "user_id": user_id,
                            "model_key": key,
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            delete_filter: dict[str, Any] = {"user_id": user_id}
            if keys:
                delete_filter["model_key"] = {"$nin": keys}
            db.model_mappings.delete_many(delete_filter)
            rows = db.model_mappings.find({"user_id": user_id}).sort("priority", DESCENDING)
            result = []
            for row in rows:
                row["id"] = str(row.pop("_id"))
                result.append(_json_document(row))
            return result

        return await _run_sync(operation)


class MongoCancellationStore:
    async def request_cancel(
        self,
        *,
        project_id: str,
        task_type: str,
        episode: int,
        task_id: str,
        beat_num: int | None = None,
        scope: str | None = None,
        ttl_seconds: int = 86_400,
    ) -> None:
        key = cancel_key(
            project_id=project_id,
            task_type=task_type,
            episode=episode,
            task_id=task_id,
            beat_num=beat_num,
            scope=scope,
        )
        await _run_sync(
            get_mongo_database().task_cancellations.update_one,
            {"_id": key},
            {"$set": {"expires_at": utc_now() + timedelta(seconds=max(ttl_seconds, 0))}},
            upsert=True,
        )

    async def is_cancel_requested(
        self,
        *,
        project_id: str,
        task_type: str,
        episode: int,
        task_id: str,
        beat_num: int | None = None,
        scope: str | None = None,
    ) -> bool:
        key = cancel_key(
            project_id=project_id,
            task_type=task_type,
            episode=episode,
            task_id=task_id,
            beat_num=beat_num,
            scope=scope,
        )
        row = await _run_sync(get_mongo_database().task_cancellations.find_one, {"_id": key})
        return bool(row and row.get("expires_at") and row["expires_at"] > utc_now())


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def _json_document(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, dict):
        return {str(key): _json_document(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_document(item) for item in value]
    return value


__all__ = [
    "MongoAuthPort",
    "MongoAuthSession",
    "MongoCancellationStore",
    "MongoProjectAccess",
    "MongoProjectRegistry",
    "MongoUserModelSettings",
    "ensure_mongo_indexes",
    "get_mongo_client",
    "get_mongo_database",
    "project_work_root",
    "serverless_work_root",
]
