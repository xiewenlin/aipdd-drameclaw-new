"""User-related ORM models."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from novelvideo.db import Base

SESSION_TOKEN_BYTES = 32
DEFAULT_SESSION_TTL_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def generate_session_token() -> str:
    """Generate a cryptographically random session token."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    model_config: Mapped[Optional["UserModelConfig"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    provider_channels: Mapped[list["UserProviderChannel"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    model_mappings: Mapped[list["UserModelMapping"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    device_info: Mapped[Optional[str]] = mapped_column(String(256))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="sessions")

    @property
    def is_valid(self) -> bool:
        now = _utcnow()
        return self.revoked_at is None and self.expires_at > now

    @classmethod
    def create(
        cls,
        user_id: str,
        *,
        ttl_days: int = DEFAULT_SESSION_TTL_DAYS,
        device_info: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> "UserSession":
        now = _utcnow()
        return cls(
            user_id=user_id,
            session_token=generate_session_token(),
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=now + timedelta(days=ttl_days),
            created_at=now,
            last_seen_at=now,
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "is_revoked": self.revoked_at is not None,
        }


class UserModelConfig(Base):
    __tablename__ = "user_model_configs"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gateway_mode: Mapped[str] = mapped_column(String(16), default="official", nullable=False)
    newapi_base_url: Mapped[Optional[str]] = mapped_column(String(512))
    newapi_api_key: Mapped[Optional[str]] = mapped_column(String(512))
    media_relay_provider: Mapped[str] = mapped_column(String(32), default="aliyun_oss")
    media_relay_ttl: Mapped[int] = mapped_column(Integer, default=1800)
    oss_endpoint: Mapped[Optional[str]] = mapped_column(String(256))
    oss_bucket: Mapped[Optional[str]] = mapped_column(String(128))
    oss_ak: Mapped[Optional[str]] = mapped_column(String(128))
    oss_sk: Mapped[Optional[str]] = mapped_column(String(512))
    cognee_provider: Mapped[Optional[str]] = mapped_column(String(64))
    cognee_model: Mapped[Optional[str]] = mapped_column(String(128))
    cognee_dimensions: Mapped[Optional[str]] = mapped_column(String(16))
    embedding_batch_size: Mapped[Optional[str]] = mapped_column(String(16))
    image_default_width: Mapped[int] = mapped_column(Integer, default=1440)
    image_default_height: Mapped[int] = mapped_column(Integer, default=2560)
    image_default_style: Mapped[str] = mapped_column(String(64), default="chinese_period_drama")
    video_resolution: Mapped[str] = mapped_column(String(16), default="720p")
    video_generate_audio: Mapped[str] = mapped_column(String(16), default="auto")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="model_config")


class UserProviderChannel(Base):
    __tablename__ = "user_provider_channels"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_upc_user_name"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider_type: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(512))
    api_key: Mapped[Optional[str]] = mapped_column(String(512))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="enabled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="provider_channels")

    def to_dict(self, decrypt: bool = False) -> dict:
        from novelvideo.utils.crypto import decrypt_value

        return {
            "id": str(self.id),
            "provider_type": self.provider_type,
            "name": self.name,
            "base_url": self.base_url,
            "api_key": decrypt_value(self.api_key) if decrypt and self.api_key else (self.api_key or ""),
            "weight": self.weight,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class UserModelMapping(Base):
    __tablename__ = "user_model_mappings"
    __table_args__ = (UniqueConstraint("user_id", "model_key", name="uq_umm_user_model_key"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    channel_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("user_provider_channels.id", ondelete="SET NULL"))
    model_type: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="enabled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="model_mappings")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "model_key": self.model_key,
            "model_name": self.model_name,
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "model_type": self.model_type,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
