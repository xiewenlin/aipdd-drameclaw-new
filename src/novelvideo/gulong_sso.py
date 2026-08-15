"""Verification for short-lived SSO assertions issued by the Gulong website."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


_AUDIENCE = "gulong-short-drama"
_DEFAULT_ISSUER = "https://sologle.com"
_CLOCK_SKEW_SECONDS = 15
_MAX_ASSERTION_AGE_SECONDS = 180


class GulongSsoError(ValueError):
    """Raised when a Gulong SSO assertion cannot be trusted."""


@dataclass(frozen=True)
class GulongIdentity:
    subject: str
    username: str | None
    email: str | None
    display_name: str | None
    role: str
    jti: str
    expires_at: int


def _decode_segment(value: str) -> bytes:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise GulongSsoError("Malformed SSO assertion") from exc


def _object_segment(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_decode_segment(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GulongSsoError("Malformed SSO assertion") from exc
    if not isinstance(decoded, dict):
        raise GulongSsoError("Malformed SSO assertion")
    return decoded


def _required_text(payload: dict[str, Any], key: str, *, max_length: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise GulongSsoError(f"Invalid SSO {key}")
    return value.strip()


def _optional_text(payload: dict[str, Any], key: str, *, max_length: int) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > max_length:
        raise GulongSsoError(f"Invalid SSO {key}")
    return value.strip() or None


def verify_gulong_sso_assertion(token: str, *, now: int | None = None) -> GulongIdentity:
    """Verify an HS256 assertion and return its bounded identity claims."""

    secret = os.environ.get("SHORT_DRAMA_SSO_SECRET", "").strip()
    if len(secret) < 32:
        raise GulongSsoError("Gulong SSO is not configured")
    if not isinstance(token, str) or len(token) > 4096:
        raise GulongSsoError("Malformed SSO assertion")

    parts = token.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise GulongSsoError("Malformed SSO assertion")
    header_segment, payload_segment, signature = parts
    header = _object_segment(header_segment)
    payload = _object_segment(payload_segment)
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise GulongSsoError("Unsupported SSO assertion")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected, signature):
        raise GulongSsoError("Invalid SSO signature")

    issuer = os.environ.get("GULONG_SSO_ISSUER", _DEFAULT_ISSUER).strip() or _DEFAULT_ISSUER
    if payload.get("iss") != issuer or payload.get("aud") != _AUDIENCE:
        raise GulongSsoError("Invalid SSO issuer or audience")

    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if not isinstance(issued_at, int) or not isinstance(expires_at, int):
        raise GulongSsoError("Invalid SSO lifetime")
    current = int(time.time()) if now is None else int(now)
    if issued_at > current + _CLOCK_SKEW_SECONDS or expires_at < current - _CLOCK_SKEW_SECONDS:
        raise GulongSsoError("SSO assertion expired")
    if expires_at <= issued_at or expires_at - issued_at > _MAX_ASSERTION_AGE_SECONDS:
        raise GulongSsoError("Invalid SSO lifetime")

    role = _optional_text(payload, "role", max_length=32) or "user"
    if role not in {"user", "developer", "admin"}:
        role = "user"
    return GulongIdentity(
        subject=_required_text(payload, "sub", max_length=128),
        username=_optional_text(payload, "username", max_length=64),
        email=_optional_text(payload, "email", max_length=254),
        display_name=_optional_text(payload, "name", max_length=128),
        role=role,
        jti=_required_text(payload, "jti", max_length=128),
        expires_at=expires_at,
    )


__all__ = ["GulongIdentity", "GulongSsoError", "verify_gulong_sso_assertion"]
