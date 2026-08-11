"""PostgreSQL-based authentication port implementations for CE."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from dataclasses import replace
from sqlalchemy import select
from ulid import ULID

from novelvideo.db import async_session
from novelvideo.db_models.user import (
    User,
    UserSession,
    hash_password,
    verify_password,
)
from novelvideo.ports.auth_contract import (
    AgentAuthenticatedUser,
    AgentSessionToken,
    AuthenticatedUser,
    AuthError,
    AuthFailureReason,
    LoginResult,
)

logger = logging.getLogger("novelvideo.ports.auth")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresAuthPort:
    """AuthPort implementation backed by PostgreSQL users & sessions."""

    async def verify_session(self, raw_cookie: str | None) -> dict:
        if not raw_cookie:
            raise AuthError(AuthFailureReason.MISSING, "Missing session cookie")

        async with async_session() as session:
            result = await session.execute(
                select(UserSession, User)
                .join(User, UserSession.user_id == User.id)
                .where(UserSession.session_token == raw_cookie)
            )
            row = result.first()

            if row is None:
                raise AuthError(AuthFailureReason.INVALID, "Session not found")

            db_session, user = row

            if db_session.revoked_at is not None:
                raise AuthError(AuthFailureReason.REVOKED, "Session revoked")

            if db_session.expires_at < _utcnow():
                raise AuthError(AuthFailureReason.EXPIRED, "Session expired")

            if user.status != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "User suspended")

            db_session.last_seen_at = _utcnow()
            await session.commit()

            return AuthenticatedUser(
                id=str(user.id),
                username=user.username,
                role=user.role,
                status=user.status,
            ).to_legacy_dict()

    async def revoke_session(self, raw_cookie: str) -> None:
        if not raw_cookie:
            return
        async with async_session() as session:
            result = await session.execute(
                select(UserSession).where(UserSession.session_token == raw_cookie)
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.revoked_at = _utcnow()
                await session.commit()

    async def login(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_info: str | None = None,
    ) -> LoginResult:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalar_one_or_none()

            if user is None or not verify_password(password, user.password_hash):
                raise AuthError(AuthFailureReason.INVALID, "Invalid username or password")

            if user.status != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "Account is not active")

            user.last_login_at = _utcnow()

            new_session = UserSession.create(
                user_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
                device_info=device_info,
            )
            session.add(new_session)
            await session.commit()
            await session.refresh(new_session)

            return LoginResult(
                user=AuthenticatedUser(
                    id=str(user.id),
                    username=user.username,
                    role=user.role,
                    status=user.status,
                ),
                session_id=str(new_session.id),
                raw_cookie=new_session.session_token,
            )

    async def register(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> LoginResult:
        async with async_session() as session:
            existing = await session.execute(
                select(User.id).where(User.username == username)
            )
            if existing.scalar_one_or_none():
                raise AuthError(AuthFailureReason.INVALID, "Username already taken")

            if email:
                existing_email = await session.execute(
                    select(User.id).where(User.email == email)
                )
                if existing_email.scalar_one_or_none():
                    raise AuthError(AuthFailureReason.INVALID, "Email already registered")

            user = User(
                username=username,
                email=email or None,
                password_hash=hash_password(password),
                role="user",
                status="active",
                display_name=display_name or username,
            )
            session.add(user)
            await session.flush()

            from novelvideo.db_models.user import UserModelConfig

            default_config = UserModelConfig(
                user_id=str(user.id),
                gateway_mode="official",
            )
            session.add(default_config)

            new_session = UserSession.create(user_id=str(user.id))
            session.add(new_session)
            await session.commit()
            await session.refresh(user)
            await session.refresh(new_session)

            return LoginResult(
                user=AuthenticatedUser(
                    id=str(user.id),
                    username=user.username,
                    role=user.role,
                    status=user.status,
                ),
                session_id=str(new_session.id),
                raw_cookie=new_session.session_token,
            )

    async def list_user_sessions(self, user_id: str) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(UserSession)
                .where(UserSession.user_id == user_id)
                .order_by(UserSession.last_seen_at.desc())
            )
            sessions = result.scalars().all()
            return [s.to_dict() for s in sessions]

    async def revoke_user_session(self, user_id: str, session_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(UserSession).where(
                    UserSession.id == session_id,
                    UserSession.user_id == user_id,
                )
            )
            db_session = result.scalar_one_or_none()
            if not db_session:
                return False
            db_session.revoked_at = _utcnow()
            await session.commit()
            return True


class PostgresAuthSession:
    """AuthSessionPort implementation - agent sessions in memory."""

    def __init__(self) -> None:
        self._agent_sessions: dict[str, AgentAuthenticatedUser] = {}

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
        session_id = str(ULID())
        token_value = f"local-{ULID()}"
        exp = int(time.time()) + int(ttl_seconds or 2 * 3600)
        normalized_scopes = tuple(scopes or ())
        self._agent_sessions[token_value] = AgentAuthenticatedUser(
            id="local",
            username=username,
            role="owner",
            agent_session_id=session_id,
            agent_kind=agent_kind,
            worker_id=worker_id,
            scopes=normalized_scopes,
            current_scope_kind=current_scope_kind,
            current_project_id=current_project_id,
            parent_session_id=parent_session_id,
        )
        return AgentSessionToken(
            value=token_value,
            session_id=session_id,
            user=username,
            scopes=normalized_scopes,
            exp=exp,
            worker_id=worker_id or "",
            agent_kind=agent_kind,
        )

    async def verify_agent_session(self, token: str) -> dict:
        session = self._agent_sessions.get(token)
        if session is None:
            raise AuthError(AuthFailureReason.INVALID, "agent session not found")
        return session.to_legacy_dict()

    async def update_agent_session_scope(
        self,
        token_value: str,
        *,
        scope_kind: str,
        project_id: str | None,
    ) -> None:
        session = self._agent_sessions.get(token_value)
        if session is None:
            raise AuthError(AuthFailureReason.INVALID, "agent session not found")
        self._agent_sessions[token_value] = replace(
            session,
            current_scope_kind=scope_kind,
            current_project_id=project_id,
        )

    async def revoke_agent_session(self, token_value: str) -> None:
        self._agent_sessions.pop(token_value, None)



class SQLiteAuthPort:
    """AuthPort implementation backed by SQLite (for local CE development)."""

    def __init__(self) -> None:
        import asyncio
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False

    def _db_path(self):
        from pathlib import Path
        from novelvideo import config
        return Path(config.STATE_DIR) / "local" / "auth.db"

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
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user',
                        status TEXT NOT NULL DEFAULT 'active',
                        display_name TEXT,
                        avatar_url TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_login_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_token TEXT UNIQUE NOT NULL,
                        device_info TEXT,
                        ip_address TEXT,
                        user_agent TEXT,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        revoked_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
                    CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
                """)
                await db.commit()
            finally:
                await db.close()
            self._schema_ready = True

    async def verify_session(self, raw_cookie: str | None) -> dict:
        from novelvideo.ports.auth_contract import AuthError, AuthFailureReason, AuthenticatedUser
        if not raw_cookie:
            raise AuthError(AuthFailureReason.MISSING, "Missing session cookie")

        from datetime import datetime, timezone
        db = await self._connect()
        try:
            cursor = await db.execute("""
                SELECT s.*, u.username, u.role, u.status
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ?
            """, (raw_cookie,))
            row = await cursor.fetchone()
            await cursor.close()

            if row is None:
                raise AuthError(AuthFailureReason.INVALID, "Session not found")

            if row["revoked_at"] is not None:
                raise AuthError(AuthFailureReason.REVOKED, "Session revoked")

            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                raise AuthError(AuthFailureReason.EXPIRED, "Session expired")

            if row["status"] != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "User suspended")

            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute("UPDATE user_sessions SET last_seen_at = ? WHERE id = ?", (now_iso, row["id"]))
            await db.commit()

            return AuthenticatedUser(
                id=str(row["user_id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                status=str(row["status"]),
            ).to_legacy_dict()
        finally:
            await db.close()

    async def revoke_session(self, raw_cookie: str) -> None:
        if not raw_cookie:
            return
        from datetime import datetime, timezone
        db = await self._connect()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE session_token = ?",
                (now_iso, raw_cookie),
            )
            await db.commit()
        finally:
            await db.close()

    async def login(
        self,
        username: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_info: str | None = None,
    ) -> "LoginResult":
        from novelvideo.ports.auth_contract import AuthError, AuthFailureReason, AuthenticatedUser, LoginResult
        from novelvideo.db_models.user import verify_password
        from datetime import datetime, timezone, timedelta
        from ulid import ULID
        from novelvideo.db_models.user import generate_session_token, DEFAULT_SESSION_TTL_DAYS

        db = await self._connect()
        try:
            cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = await cursor.fetchone()
            await cursor.close()

            if row is None or not verify_password(password, row["password_hash"]):
                raise AuthError(AuthFailureReason.INVALID, "Invalid username or password")

            if row["status"] != "active":
                raise AuthError(AuthFailureReason.USER_SUSPENDED, "Account is not active")

            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            await db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now_iso, row["id"]))

            session_id = str(ULID())
            session_token = generate_session_token()
            expires_at = (now + timedelta(days=DEFAULT_SESSION_TTL_DAYS)).isoformat()

            await db.execute("""
                INSERT INTO user_sessions (id, user_id, session_token, device_info, ip_address, user_agent, expires_at, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, row["id"], session_token, device_info, ip_address, user_agent, expires_at, now_iso, now_iso))
            await db.commit()

            return LoginResult(
                user=AuthenticatedUser(
                    id=str(row["id"]),
                    username=str(row["username"]),
                    role=str(row["role"]),
                    status=str(row["status"]),
                ),
                session_id=session_id,
                raw_cookie=session_token,
            )
        finally:
            await db.close()

    async def register(
        self,
        username: str,
        password: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> "LoginResult":
        from novelvideo.ports.auth_contract import AuthError, AuthFailureReason, AuthenticatedUser, LoginResult
        from novelvideo.db_models.user import hash_password
        from datetime import datetime, timezone, timedelta
        from ulid import ULID
        from novelvideo.db_models.user import generate_session_token, DEFAULT_SESSION_TTL_DAYS

        db = await self._connect()
        try:
            cursor = await db.execute("SELECT id FROM users WHERE username = ?", (username,))
            if await cursor.fetchone():
                await cursor.close()
                raise AuthError(AuthFailureReason.INVALID, "Username already taken")
            await cursor.close()

            if email:
                cursor = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
                if await cursor.fetchone():
                    await cursor.close()
                    raise AuthError(AuthFailureReason.INVALID, "Email already registered")
                await cursor.close()

            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            user_id = str(ULID())
            pwd_hash = hash_password(password)

            await db.execute("""
                INSERT INTO users (id, username, email, password_hash, role, status, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'user', 'active', ?, ?, ?)
            """, (user_id, username, email or None, pwd_hash, display_name or username, now_iso, now_iso))

            session_id = str(ULID())
            session_token = generate_session_token()
            expires_at = (now + timedelta(days=DEFAULT_SESSION_TTL_DAYS)).isoformat()

            await db.execute("""
                INSERT INTO user_sessions (id, user_id, session_token, expires_at, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, session_token, expires_at, now_iso, now_iso))
            await db.commit()

            return LoginResult(
                user=AuthenticatedUser(
                    id=user_id,
                    username=username,
                    role="user",
                    status="active",
                ),
                session_id=session_id,
                raw_cookie=session_token,
            )
        finally:
            await db.close()

    async def list_user_sessions(self, user_id: str) -> list[dict]:
        db = await self._connect()
        try:
            cursor = await db.execute("""
                SELECT * FROM user_sessions
                WHERE user_id = ?
                ORDER BY last_seen_at DESC
            """, (user_id,))
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def revoke_user_session(self, user_id: str, session_id: str) -> bool:
        from datetime import datetime, timezone
        db = await self._connect()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor = await db.execute("""
                UPDATE user_sessions SET revoked_at = ?
                WHERE id = ? AND user_id = ?
            """, (now_iso, session_id, user_id))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await db.close()