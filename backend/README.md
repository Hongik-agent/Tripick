# Tripick backend

Python 3.14, FastAPI, SQLAlchemy, asyncpg, Alembic을 사용하는 로컬 개발환경입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

`.env`의 `DATABASE_URL`에서 `YOUR_PASSWORD`를 `tripick` 계정 비밀번호로 바꾸고, 프런트엔드 `.env.local`과 같은 Supabase URL·publishable key를 설정합니다. 비밀번호에 `@`, `/`, `:` 등의 특수문자가 있으면 URL 인코딩합니다. `.env`는 Git에서 제외됩니다.

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`http://127.0.0.1:8000/health`가 `{"status":"ok"}`를 반환하면 DB 연결도 정상입니다. DB에 연결할 수 없으면 503을 반환합니다.

`PUT /api/users/me`는 `Authorization: Bearer <Supabase access token>`을 받습니다. FastAPI가 Supabase Auth에 토큰을 확인한 뒤 `users` 테이블에 사용자 ID와 선택적 이메일을 저장하고 같은 값을 응답합니다. Google·Kakao 모두 이 API를 사용하며 Kakao 로그인 버튼과 제공자 설정은 아직 없습니다. 별도 백엔드 세션은 없습니다. 401은 잘못된 토큰, 403은 미지원 로그인 제공자, 502는 Supabase 오류, 503은 DB 오류입니다.

```powershell
.\.venv\Scripts\alembic.exe current
```

Alembic의 첫 마이그레이션이 `users` 테이블을 만듭니다. `id`는 Supabase Auth 사용자 UUID를 기본 키로 사용하며 이메일은 Kakao의 이메일 미제공 경우를 위해 nullable입니다. Supabase가 확인된 같은 이메일의 신원을 연결하면 하나의 Tripick 계정으로 봅니다.
