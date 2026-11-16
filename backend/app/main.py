from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import config as cfg
from .auth import router as auth_router, clear_cookie
from .domain import router as domain_router
from .db import engine

app = FastAPI(title='Tripick API')
app.add_middleware(CORSMiddleware, allow_origins=[cfg.frontend_origin],
    allow_credentials=True, allow_methods=cfg.cors_methods, allow_headers=cfg.cors_headers)
app.include_router(auth_router)
app.include_router(domain_router)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    # OAuth 코드/쿠키/개인 응답을 프록시 CDN과 브라우저에 캐시하지 않는다.
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['x-vercel-enable-rewrite-caching'] = '0'
    if response.status_code == 401 and request.url.path != '/api/auth/callback':
        clear_cookie(response, cfg.session_cookie)
    return response


@app.exception_handler(HTTPException)
async def api_error(request, exc):
    detail = exc.detail if isinstance(exc.detail, dict) else dict(code='REQUEST_FAILED', message=str(exc.detail), retryable=False)
    return JSONResponse({'error': detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic의 input 필드에 요청/비밀 데이터가 포함될 수 있어 그대로 응답하지 않는다.
    return JSONResponse({'error': dict(code='INVALID_SELECTION', message='입력값과 필수 항목을 확인해 주세요.', retryable=False)}, status_code=422)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse({'error': dict(code='DATABASE_UNAVAILABLE', message='저장소에 연결하지 못했습니다.', retryable=True)}, status_code=503)


@app.get('/health')
async def health():
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))
    return {'status': 'ok'}
