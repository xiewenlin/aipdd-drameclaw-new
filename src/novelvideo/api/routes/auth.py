"""认证端点：注册 / 登录 / 登出 / 当前用户 / 会话管理。"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from novelvideo.api.auth import (
    AUTH_COOKIE_NAME,
    get_api_user,
    resolve_auth_cookie_from_request,
)
from novelvideo.ports import get_auth_port
from novelvideo.ports.auth_contract import AuthError, AuthFailureReason
from novelvideo.gulong_sso import GulongSsoError, verify_gulong_sso_assertion
from novelvideo.shared.runtime_env import cookie_secure as runtime_cookie_secure

router = APIRouter()
logger = logging.getLogger("novelvideo.api.routes.auth")

_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _cookie_secure() -> bool:
    return runtime_cookie_secure()


def _require_local_auth_enabled() -> None:
    if os.environ.get("SHORT_DRAMA_SSO_SECRET", "").strip() and os.environ.get(
        "ALLOW_LOCAL_AUTH", ""
    ).strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=410, detail="请使用古龙统一账号登录或注册")


def _set_auth_cookie(response: Response, cookie_value: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        max_age=_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def _set_embedded_auth_cookie(response: Response, cookie_value: str) -> None:
    """Set a CHIPS cookie that remains usable inside the Gulong iframe."""

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    for index in range(len(response.raw_headers) - 1, -1, -1):
        key, value = response.raw_headers[index]
        if key.lower() == b"set-cookie" and value.startswith(f"{AUTH_COOKIE_NAME}=".encode()):
            if b"Partitioned" not in value:
                response.raw_headers[index] = (key, value + b"; Partitioned")
            break


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=_cookie_secure(),
    )


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=256)
    email: str | None = None
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class GulongSsoExchangeRequest(BaseModel):
    token: str = Field(min_length=64, max_length=4096)


@router.post("/auth/gulong/exchange")
async def exchange_gulong_sso(request: Request, body: GulongSsoExchangeRequest):
    try:
        identity = verify_gulong_sso_assertion(body.token)
    except GulongSsoError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    auth_port = get_auth_port()
    exchange = getattr(auth_port, "exchange_gulong_identity", None)
    if not callable(exchange):
        raise HTTPException(status_code=503, detail="Gulong SSO requires the MongoDB backend")
    try:
        result = await exchange(
            identity,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        status = 403 if exc.reason == AuthFailureReason.USER_SUSPENDED else 401
        raise HTTPException(status_code=status, detail=exc.detail or "SSO exchange failed") from exc

    response = JSONResponse(
        {
            "ok": True,
            "data": {
                "user": result.user.to_legacy_dict(),
                "session_id": result.session_id,
            },
        }
    )
    response.headers["Cache-Control"] = "no-store"
    _set_embedded_auth_cookie(response, result.raw_cookie)
    return response


@router.post("/auth/register")
async def register(request: Request, body: RegisterRequest):
    _require_local_auth_enabled()
    auth_port = get_auth_port()
    try:
        result = await auth_port.register(
            username=body.username.strip(),
            password=body.password,
            email=body.email.strip() if body.email else None,
            display_name=body.display_name.strip() if body.display_name else None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.detail or "Registration failed")

    response = JSONResponse({
        "ok": True,
        "data": {
            "user": result.user.to_legacy_dict(),
            "session_id": result.session_id,
        },
    })
    _set_auth_cookie(response, result.raw_cookie)
    return response


@router.post("/auth/login")
async def login(request: Request, body: LoginRequest):
    _require_local_auth_enabled()
    auth_port = get_auth_port()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = await auth_port.login(
            username=body.username.strip(),
            password=body.password,
            ip_address=client_ip,
            user_agent=user_agent,
        )
    except AuthError as exc:
        if exc.reason == AuthFailureReason.USER_SUSPENDED:
            raise HTTPException(status_code=403, detail=exc.detail or "Account suspended")
        raise HTTPException(status_code=401, detail=exc.detail or "Invalid credentials")

    response = JSONResponse({
        "ok": True,
        "data": {
            "user": result.user.to_legacy_dict(),
            "session_id": result.session_id,
        },
    })
    _set_auth_cookie(response, result.raw_cookie)
    return response


@router.post("/auth/logout")
async def logout(request: Request, user: dict = Depends(get_api_user)):
    cookie_value = resolve_auth_cookie_from_request(request)
    if cookie_value:
        await get_auth_port().revoke_session(cookie_value)

    response = JSONResponse({"ok": True})
    _clear_auth_cookie(response)
    return response


@router.get("/auth/me")
async def me(user: dict = Depends(get_api_user)):
    credit_balance = 0
    user_id = str(user.get("user_id") or user.get("id") or "").strip()
    if user_id:
        from novelvideo.ports.registry import get_port
        balance = await get_port("usage_meter").get_user_credit_balance(user_id)
        credit_balance = balance if balance is not None else 0

    return JSONResponse({
        "ok": True,
        "data": {
            "username": user["username"],
            "role": user["role"],
            "credit_balance": credit_balance,
            "credential_kind": user.get("credential_kind") or "user",
            "current_scope_kind": user.get("current_scope_kind"),
            "current_project_id": user.get("current_project_id"),
            "scopes": user.get("scopes"),
        },
    })


@router.get("/auth/sessions")
async def list_sessions(user: dict = Depends(get_api_user)):
    user_id = str(user.get("user_id") or user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_port = get_auth_port()
    sessions = await auth_port.list_user_sessions(user_id)
    return JSONResponse({"ok": True, "data": sessions})


@router.post("/auth/sessions/{session_id}/revoke")
async def revoke_session(session_id: str, user: dict = Depends(get_api_user)):
    user_id = str(user.get("user_id") or user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_port = get_auth_port()
    success = await auth_port.revoke_user_session(user_id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse({"ok": True})
