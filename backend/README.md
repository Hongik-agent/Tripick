# Tripick backend

FastAPI + SQLAlchemy async + asyncpg + Alembic. Supabase Auth의 Google·Kakao OAuth를 BFF로 중계하고 서버에서 교환한 토큰을 PostgreSQL에 암호화 보관하고 업무 API의 세션·소유권·저장 한도·CSRF를 검사한다.

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# .env.example을 참고해 .env 작성. 실제 값은 커밋하지 않는다.
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --no-access-log
```

`SESSION_ENCRYPTION_KEY`는 서버 전용 Fernet 키이며 `.env`에만 보관한다. 설정 로딩·검증·비용 기본값은 `app/config.py`에 모은다. 개발 `FRONTEND_ORIGIN`은 Vite의 실제 localhost Origin으로 지정한다. 운영에서는 HTTPS Origin만 허용한다.

기존 `0001_users`를 유지하고 `0002_server_storage`에 세션·일정·커뮤니티, `0003_bff_oauth`에 PKCE 트랜잭션을 추가했다. 오프라인 `alembic upgrade head --sql`은 DB 자격증명을 읽지 않는다. `/health`는 DB 연결 실패 시 503이다.

## 검증

`requirements-dev.txt`를 설치한다. 테스트는 운영 `.env`를 사용하지 않고 **127.0.0.1:55440의 전용 PostgreSQL**을 사용한다. 테스트용 서버를 띄운 뒤 `python tests/run_local.py`를 실행하면 `tripick_test`, `tripick_test_fresh` DB를 만들고 head 마이그레이션과 unittest를 실행한다. `--reset-test-schema`를 붙이면 이 두 전용 테스트 DB를 초기화하고 기존 0001→head 및 빈 DB→head 경로도 검사한다. 실제 운영 DB URL로 변경하지 않는다.

운영의 실제 생성 공급자는 연결하지 않았다. `verified_drafts` dependency 기본 구현은 저장을 거부하며, 테스트만 검증 초안을 주입한다. 프런트에서 검증됐다는 플래그를 받아 저장하는 우회 API는 없다.

설정/배포와 Supabase callback 구분은 [구현·운영 문서](../docs/specs/06-implementation.md)를 따른다.
