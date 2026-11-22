import os
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

database_url = os.environ["DATABASE_URL"]
supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
supabase_publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

def positive(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment or parsed.username
            or parsed.password or "*" in value):
        raise ValueError("FRONTEND_ORIGIN must be an exact origin without a path")
    return value


frontend_origin = origin(os.environ["FRONTEND_ORIGIN"])
cookie_secure = frontend_origin.startswith("https://")
if not cookie_secure and urlsplit(frontend_origin).hostname not in ("localhost", "127.0.0.1"):
    raise ValueError("HTTP is allowed only for local development")
session_cookie = "__Host-tripick-session" if cookie_secure else "tripick-session"
oauth_cookie = "__Host-tripick-oauth" if cookie_secure else "tripick-oauth"
oauth_callback_url = frontend_origin + "/api/auth/callback"
token_cipher = Fernet(os.environ["SESSION_ENCRYPTION_KEY"].encode())

# 초 단위. 유휴 24시간: 여행 계획 중 잦은 재로그인/토큰 교환을 줄인다.
session_idle_seconds = positive("SESSION_IDLE_SECONDS", 86400)
# 절대 7일: 활동 여부와 무관하게 재로그인을 요구하는 상한이다.
session_absolute_seconds = positive("SESSION_ABSOLUTE_SECONDS", 604800)
# 요청이 들어온 때에만 최대 30분마다 Supabase를 재조회한다. 외부 로그아웃 탐지 보장은 아니다.
session_recheck_seconds = positive("SESSION_RECHECK_SECONDS", 1800)
# 매 요청 UPDATE 대신 5분마다 활동 시각 기록. 유휴 만료에 최대 이 간격의 오차가 있다.
session_touch_seconds = positive("SESSION_TOUCH_SECONDS", 300)
# BFF 로그인 시작→콜백 10분. 서버가 state·브라우저 연계·PKCE의 만료를 검사한다.
oauth_ttl_seconds = positive("OAUTH_TTL_SECONDS", 600)
# 만료 60초 전부터 다음 사용자 요청에서만 갱신한다. 주기 갱신 작업은 없다.
token_refresh_margin_seconds = positive("TOKEN_REFRESH_MARGIN_SECONDS", 60)
# 브라우저별 로그인 시작 및 계정별 세션 발급을 1분 5회로 제한한다. IP 헤더는 신뢰하지 않는다.
login_window_seconds = positive("LOGIN_WINDOW_SECONDS", 60)
login_limit = positive("LOGIN_LIMIT", 5)
# 멱등키 결과를 24시간 보존한다.
idempotency_ttl_seconds = positive("IDEMPOTENCY_TTL_SECONDS", 86400)
if session_touch_seconds >= session_idle_seconds or session_idle_seconds > session_absolute_seconds:
    raise ValueError("Require touch < idle <= absolute session timeout")
cors_methods = ["GET", "POST", "PUT", "DELETE"]
cors_headers = ["Content-Type", "X-CSRF-Token", "Idempotency-Key", "If-Match"]

openai_key = os.getenv("OPENAI_API_KEY", "")
maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
