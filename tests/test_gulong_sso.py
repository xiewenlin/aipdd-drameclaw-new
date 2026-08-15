from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from novelvideo.gulong_sso import GulongSsoError, verify_gulong_sso_assertion


def _segment(value: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).rstrip(b"=").decode("ascii")


def _token(secret: str, payload: dict) -> str:
    header = _segment({"alg": "HS256", "typ": "JWT"})
    body = _segment(payload)
    signing_input = f"{header}.{body}"
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return f"{signing_input}.{signature}"


def test_verifies_signed_gulong_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-sso-secret-that-is-longer-than-32-bytes"
    monkeypatch.setenv("SHORT_DRAMA_SSO_SECRET", secret)
    token = _token(
        secret,
        {
            "iss": "https://sologle.com",
            "aud": "gulong-short-drama",
            "sub": "gulong-user-1",
            "username": "director",
            "email": "director@example.com",
            "name": "导演",
            "role": "developer",
            "iat": 1_000,
            "exp": 1_120,
            "jti": "assertion-1",
        },
    )

    identity = verify_gulong_sso_assertion(token, now=1_050)

    assert identity.subject == "gulong-user-1"
    assert identity.display_name == "导演"
    assert identity.role == "developer"
    assert identity.jti == "assertion-1"


def test_rejects_tampered_or_expired_assertions(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-sso-secret-that-is-longer-than-32-bytes"
    monkeypatch.setenv("SHORT_DRAMA_SSO_SECRET", secret)
    payload = {
        "iss": "https://sologle.com",
        "aud": "gulong-short-drama",
        "sub": "gulong-user-1",
        "iat": 1_000,
        "exp": 1_120,
        "jti": "assertion-2",
    }
    token = _token(secret, payload)

    with pytest.raises(GulongSsoError, match="signature"):
        verify_gulong_sso_assertion(f"{token[:-1]}x", now=1_050)
    with pytest.raises(GulongSsoError, match="expired"):
        verify_gulong_sso_assertion(token, now=1_200)
