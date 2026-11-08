# 01 · 현재 구현과 차이

확인일: 2026-11-06. 코드를 읽어 확인한 정적 상태다. 외부 OAuth 로그인 성공은 별도 검증이 필요하다.

## 프런트엔드

- `frontend/src/App.tsx`: React 단일 화면 흐름. 선택형 조건, 예시 기반 생성, 결과·저장·편집·삭제 UI가 있다. 생성은 `setTimeout` 후 예시 데이터를 선택하며 실제 AI·장소·경로 API를 호출하지 않는다.
- 날짜 입력은 화면에 있으나 현재 생성 모의 함수가 날짜별 결과를 만들지 않는다. 인원 `<select>`는 상태에 연결되지 않았다. API 전환 시 필수 날짜·인원 구간·이동수단 필드를 화면과 연동해야 한다.
- `frontend/src/supabase.ts`: 환경 변수가 있으면 Supabase 클라이언트를 만들고 Google OAuth를 시작한다. Supabase SDK 기본 설정으로 인증 세션은 브라우저에 유지된다. Kakao 로그인 버튼은 아직 없다.
- 로그인 세션이 생기면 프런트가 `PUT /api/users/me`로 Supabase 토큰을 FastAPI에 보내 사용자 행을 저장한다. 서버 저장 실패 시 앱은 로그인 상태로 전환하지 않는다. 개발 중 `/api`는 Vite가 FastAPI로 프록시한다.
- 저장 일정은 Supabase 사용자 ID별 `localStorage`에 보관된다. 최대 3개는 브라우저 상태에서 검사한다. 다른 기기 동기화나 서버 측 소유권·동시 저장 보장은 없다.
- 지도와 동선은 모의 그림이다. 장소 검색용 외부 지도 링크가 있으나 내장 지도·이동시간 재계산은 실제 API 결과가 아니다.
- `frontend/src/community.tsx`와 `App.tsx`: 게시·하트·정렬이 `localStorage` 기반으로 동작한다. 다른 사용자·기기 사이에 데이터가 공유되지 않는다.
- `frontend/README.md`와 `SUPABASE_SETUP.md`는 Google OAuth가 실제 인증 경로이며 일정·커뮤니티는 브라우저 모의 저장이라는 경계를 구분한다. 실제 외부 로그인 성공은 별도 실행 검증이 필요하다.

## 백엔드

- `backend/app/main.py`: `GET /health`는 DB 연결을 확인한다. `PUT /api/users/me`는 Supabase Auth에 토큰을 검증하고 Google·Kakao 계정이면 PostgreSQL `users` 행을 생성·갱신한다. 신원을 클라이언트 본문에서 받지 않는다.
- `backend/app/config.py`, `db.py`: `.env`의 `DATABASE_URL`을 읽고 SQLAlchemy async 엔진을 만든다.
- Alembic에 `users` 테이블 생성 마이그레이션이 있고, 2026-11-05 대상 DB의 현재 리비전이 `0001_users (head)`임을 확인했다. 장소, 생성, 일정, 커뮤니티 API는 없다.

## 목표와의 핵심 차이

| 주제 | 현재 | MVP 목표 |
|---|---|---|
| 인증 | Supabase Google OAuth와 FastAPI 사용자 저장 API 연결. Kakao 버튼은 미구현 | Google·Kakao, 서버 권한 검사 |
| 일정 생성 | 예시 데이터와 대기 시간 | 근거 있는 장소·경로 조회와 생성 |
| 개인 일정 | 브라우저 저장 | 계정별 서버 저장과 3개 한도 |
| 지도 | 모의 그림과 외부 검색 링크 | 실제 위치·동선 검증 |
| 커뮤니티 | 같은 브라우저의 모의 게시·하트 | 계정·기기 간 실제 공유 |

`outputs`의 2026-10-28 보고서는 당시 OAuth를 임시 버튼으로 미루기로 했지만, 현재 코드에는 이후 작성된 Supabase Google OAuth 경로가 있다. 진행 상태는 코드에, 제품 목표는 최신 사용자 결정과 PRD에 맞춰 구분한다.
