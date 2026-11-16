import asyncio
import base64
import re
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, insert, update, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from . import config as cfg
from .db import engine
from .errors import fail
from .models import auth_sessions as sessions, users, oauth_transactions as oauth

router = APIRouter(prefix="/api/auth")


def now():
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt(value: dict) -> str:
    return cfg.token_cipher.encrypt(json.dumps(value).encode()).decode()


def decrypt(value: str) -> dict:
    try:
        return json.loads(cfg.token_cipher.decrypt(value.encode()))
    except (InvalidToken, ValueError):
        fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")


def provider_request(path: str, token: str | None = None, body: dict | None = None):
    headers = {"apikey": cfg.supabase_publishable_key, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = URLRequest(cfg.supabase_url + "/auth/v1/" + path,
                         headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(request, timeout=8) as response:
            if response.status == 204:
                return {}
            value = json.load(response)
            if not isinstance(value, dict):
                raise ValueError()
            return value
    except HTTPError as exc:
        if exc.code in (400, 401, 403):
            fail(401, "AUTH_REQUIRED", "로그인이 만료되었습니다.")
        fail(502, "EXTERNAL_DATA_UNAVAILABLE", "인증 서비스에 연결하지 못했습니다.", True)
    except (URLError, TimeoutError, ValueError):
        fail(502, "EXTERNAL_DATA_UNAVAILABLE", "인증 서비스에 연결하지 못했습니다.", True)


def identity(value: dict):
    try:
        uid = UUID(value["id"])
        email = value.get("email") or None
        providers = value["app_metadata"]["providers"]
        if email is not None and (not isinstance(email, str) or len(email) > 320):
            raise ValueError()
        if not isinstance(providers, list):
            raise ValueError()
        if not any(p in ("google", "kakao") for p in providers):
            fail(403, "UNSUPPORTED_PROVIDER", "지원하지 않는 로그인 제공자입니다.")
        return uid, email
    except (KeyError, TypeError, ValueError):
        fail(502, "EXTERNAL_DATA_UNAVAILABLE", "인증 응답을 확인할 수 없습니다.")


def token_values(value: dict):
    try:
        if not all(isinstance(value[k], str) and value[k] for k in ("access_token", "refresh_token")):
            raise ValueError()
        ttl = int(value["expires_in"])
        if ttl <= 0:
            raise ValueError()
        # 공급자 원본 응답/프로필을 통째로 보관하지 않는다.
        return encrypt({k: value[k] for k in ("access_token", "refresh_token")}), now() + timedelta(seconds=ttl)
    except (KeyError, TypeError, ValueError):
        fail(502, "EXTERNAL_DATA_UNAVAILABLE", "인증 응답을 확인할 수 없습니다.")


def set_cookie(response, name, value, max_age):
    response.set_cookie(name, value, max_age=max_age, secure=cfg.cookie_secure,
                        httponly=True, samesite="lax", path="/")


def clear_cookie(response, name):
    response.delete_cookie(name, path="/", secure=cfg.cookie_secure, httponly=True, samesite="lax")


def check_origin(request):
    if request.headers.get("origin") != cfg.frontend_origin:
        fail(403, "CSRF_FAILED", "요청 출처를 확인할 수 없습니다.")


def check_csrf(request, session):
    check_origin(request)
    token = request.headers.get("x-csrf-token", "")
    if not token.isascii() or not secrets.compare_digest(token, session["csrf"]):
        fail(403, "CSRF_FAILED", "화면을 새로고침한 뒤 다시 시도해 주세요.")


async def authenticate(request: Request, optional=False, write=False):
    raw = request.cookies.get(cfg.session_cookie, "")
    if not raw and optional:
        return None
    if not raw or len(raw) > 256:
        fail(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
    key = digest(raw)
    error = None
    async with engine.begin() as conn:
        session = (await conn.execute(select(sessions).where(sessions.c.hash == key).with_for_update())).mappings().first()
        stamp = now()
        if not session:
            fail(401, "AUTH_REQUIRED", "로그인이 필요합니다.")
        if write:
            check_csrf(request, session)
        if session["expires_at"] <= stamp or (stamp - session["last_seen"]).total_seconds() >= cfg.session_idle_seconds:
            await conn.execute(delete(sessions).where(sessions.c.hash == key))
            error = HTTPException(401, {"code": "AUTH_REQUIRED", "message": "로그인이 만료되었습니다.", "retryable": False})
        else:
            changes = {}
            try:
                tokens = None
                refreshed = False
                if session["token_expires_at"] <= stamp + timedelta(seconds=cfg.token_refresh_margin_seconds):
                    tokens = decrypt(session["tokens"])
                    renewed = await asyncio.to_thread(provider_request, "token?grant_type=refresh_token", None,
                                                      {"refresh_token": tokens["refresh_token"]})
                    encrypted, expires = token_values(renewed)
                    tokens = decrypt(encrypted)
                    changes.update(tokens=encrypted, token_expires_at=expires)
                    refreshed = True
                if refreshed or (stamp - session["checked_at"]).total_seconds() >= cfg.session_recheck_seconds:
                    tokens = tokens or decrypt(session["tokens"])
                    profile = await asyncio.to_thread(provider_request, "user", tokens["access_token"])
                    uid, _ = identity(profile)
                    if uid != session["user_id"]:
                        fail(401, "AUTH_REQUIRED", "다시 로그인해 주세요.")
                    changes["checked_at"] = stamp
                if (stamp - session["last_seen"]).total_seconds() >= cfg.session_touch_seconds:
                    changes["last_seen"] = stamp
            except HTTPException as exc:
                if exc.status_code in (401, 403):
                    await conn.execute(delete(sessions).where(sessions.c.hash == key))
                # 갱신 토큰 회전 후 재검증 일시 실패 시 새 토큰은 보존한다.
                error = exc
            if changes and (error is None or error.status_code == 502):
                await conn.execute(update(sessions).where(sessions.c.hash == key).values(**changes))
    if error:
        raise error
    return dict(session)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    returnTo: Literal['home', 'form', 'saved'] = 'home'


@router.post('/login/{provider}')
async def login(provider: str, body: LoginRequest, request: Request):
    check_origin(request)
    if provider not in ('google', 'kakao'):
        fail(403, 'UNSUPPORTED_PROVIDER', '지원하지 않는 로그인 제공자입니다.')
    browser = request.cookies.get(cfg.oauth_cookie, '')
    # shortcut: 쿠키 초기화로 시작 제한을 우회할 수 있다. 남용 시 프록시 계층 제한을 추가한다.
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', browser):
        browser = secrets.token_urlsafe(32)
    state, verifier, stamp = secrets.token_urlsafe(32), secrets.token_urlsafe(48), now()
    browser_hash = digest(browser)
    async with engine.begin() as conn:
        # 같은 브라우저의 동시 시작도 제한에 포함한다. 임의 프록시 IP는 사용하지 않는다.
        await conn.execute(select(func.pg_advisory_xact_lock(int(browser_hash[:15], 16))))
        await conn.execute(delete(oauth).where(oauth.c.expires_at <= stamp))
        count = await conn.scalar(select(func.count()).select_from(oauth).where(
            oauth.c.browser_hash == browser_hash,
            oauth.c.created_at > stamp-timedelta(seconds=cfg.login_window_seconds)))
        if count >= cfg.login_limit:
            fail(429, 'RATE_LIMITED', '잠시 후 다시 로그인해 주세요.', True)
        await conn.execute(insert(oauth).values(state_hash=digest(state), browser_hash=browser_hash,
            verifier=encrypt({'verifier': verifier}), provider=provider, return_to=body.returnTo,
            created_at=stamp, expires_at=stamp+timedelta(seconds=cfg.oauth_ttl_seconds)))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    # Supabase가 관리하는 OAuth state를 덮어쓰지 않고 앱 state를 고정 콜백 쿼리에 결합한다.
    params = dict(provider=provider, redirect_to=cfg.oauth_callback_url+'?state='+state,
                  code_challenge=challenge, code_challenge_method='s256')
    if provider == 'google':
        params['prompt'] = 'select_account'
    response = JSONResponse({'url': cfg.supabase_url+'/auth/v1/authorize?'+urlencode(params)})
    set_cookie(response, cfg.oauth_cookie, browser, cfg.oauth_ttl_seconds)
    return response


@router.get('/callback')
async def callback(request: Request, state: str = '', code: str = '', error: str = ''):
    failure = cfg.frontend_origin+'/?authError=login_failed'
    browser = request.cookies.get(cfg.oauth_cookie, '')
    if (not re.fullmatch(r'[A-Za-z0-9_-]{43}', state)
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}', browser) or len(code) > 8192):
        return RedirectResponse(failure, status_code=303)
    async with engine.begin() as conn:
        txn = (await conn.execute(select(oauth).where(oauth.c.state_hash == digest(state),
            oauth.c.browser_hash == digest(browser), oauth.c.expires_at > now(),
            oauth.c.consumed_at.is_(None)).with_for_update())).mappings().first()
        if not txn:
            return RedirectResponse(failure, status_code=303)
        # 외부 교환에 실패해도 재사용하지 않는다. PKCE 비밀은 소비 즉시 DB에서 지운다.
        await conn.execute(update(oauth).where(oauth.c.state_hash == txn['state_hash']).values(
            consumed_at=now(), verifier=None))
    if error or not code:
        return RedirectResponse(failure, status_code=303)
    try:
        result = await asyncio.to_thread(provider_request, 'token?grant_type=pkce', None,
            {'auth_code': code, 'code_verifier': decrypt(txn['verifier'])['verifier']})
        encrypted, expires = token_values(result)
        uid, email = identity(await asyncio.to_thread(provider_request, 'user', result['access_token']))
        raw, csrf, stamp = secrets.token_urlsafe(32), secrets.token_urlsafe(32), now()
        async with engine.begin() as conn:
            statement = pg_insert(users).values(id=uid, email=email)
            await conn.execute(statement.on_conflict_do_update(index_elements=[users.c.id], set_={'email': email}))
            profile = (await conn.execute(select(users).where(users.c.id == uid).with_for_update())).mappings().one()
            active_window = profile['session_window_start'] and (stamp-profile['session_window_start']).total_seconds() < cfg.login_window_seconds
            count = profile['session_issue_count'] if active_window else 0
            if count >= cfg.login_limit:
                fail(429, 'RATE_LIMITED', '잠시 후 다시 로그인해 주세요.', True)
            await conn.execute(update(users).where(users.c.id == uid).values(session_issue_count=count+1,
                session_window_start=profile['session_window_start'] if active_window else stamp))
            old = request.cookies.get(cfg.session_cookie)
            if old:
                await conn.execute(delete(sessions).where(sessions.c.hash == digest(old)))
            await conn.execute(delete(sessions).where(sessions.c.user_id == uid, sessions.c.expires_at < stamp))
            await conn.execute(insert(sessions).values(hash=digest(raw), user_id=uid, tokens=encrypted, csrf=csrf,
                created_at=stamp, last_seen=stamp, checked_at=stamp, token_expires_at=expires,
                expires_at=stamp+timedelta(seconds=cfg.session_absolute_seconds)))
    except HTTPException:
        # 제공자 오류/토큰/코드를 프런트 URL에 복사하지 않고 기존 로그인도 보존한다.
        return RedirectResponse(failure, status_code=303)
    response = RedirectResponse(cfg.frontend_origin+'/?view='+txn['return_to'], status_code=303)
    set_cookie(response, cfg.session_cookie, raw, cfg.session_absolute_seconds)
    return response


@router.get("/me")
async def me(request: Request):
    session = await authenticate(request)
    async with engine.connect() as conn:
        profile = (await conn.execute(select(users).where(users.c.id == session["user_id"]))).mappings().one()
    return {"user": {"id": str(profile["id"]), "email": profile["email"], "nickname": profile["nickname"]},
            "csrfToken": session["csrf"]}


@router.post("/logout")
async def logout(request: Request):
    check_origin(request)
    raw = request.cookies.get(cfg.session_cookie, "")
    async with engine.begin() as conn:
        session = (await conn.execute(select(sessions).where(sessions.c.hash == digest(raw)).with_for_update())).mappings().first()
        if session:
            check_csrf(request, session)
            await conn.execute(delete(sessions).where(sessions.c.hash == session["hash"]))
    response = Response(status_code=204)
    clear_cookie(response, cfg.session_cookie)
    if session:
        try:
            await asyncio.to_thread(provider_request, 'logout?scope=local', decrypt(session['tokens'])['access_token'], {})
        except HTTPException:
            pass  # 서버 세션은 이미 폐기됐다. 제공자 장애로 로컬 로그아웃을 되돌리지 않는다.
    return response
