# ADR 0005 · Supabase Auth를 유지하고 BFF에서 OAuth 세션 관리

2026-11-16. 상태: 사용자 승인 후 구현. [ADR 0004](0004-supabase-sdk-token-handoff.md)의 브라우저 SDK 로그인·토큰 인계를 대체한다.

## 결정

Supabase Auth가 Google·Kakao 인증을 계속 담당한다. FastAPI는 로그인 시작, PKCE 코드 교환, 토큰 암호화 저장·갱신과 앱 세션을 담당한다. 브라우저 Supabase SDK와 토큰 인계 API는 제거한다. Supabase access/refresh token과 PKCE verifier는 브라우저 JavaScript에 전달하지 않는다.

1. React가 같은 Origin의 `POST /api/auth/login/{provider}`를 호출한다. 서버는 Origin·제공자·허용된 복귀 화면을 확인한다.
2. 서버는 임의 state, PKCE verifier와 challenge를 만들고 PostgreSQL에 state·브라우저 쿠키의 해시 및 암호화한 verifier를 10분 동안 보관한다. HttpOnly 브라우저 연계 쿠키와 Supabase authorize URL을 반환한다.
3. 브라우저가 Supabase와 제공자를 거쳐 `/api/auth/callback?state=...&code=...`으로 돌아온다. Supabase 자체 OAuth state는 덮어쓰지 않고 앱 state를 고정 redirect_to 쿼리에 넣는다.
4. 서버는 브라우저 연계·만료·미사용 상태를 잠금 하에 확인하고 먼저 소비 처리한다. verifier를 DB에서 지운 뒤 코드와 verifier로 Supabase 토큰을 교환하고 사용자 신원을 확인한다.
5. 서버는 토큰을 암호화 저장하고 무작위 앱 세션 쿠키를 발급한다. 고정된 앱 화면으로 303 리다이렉트한다. 실패 시 제공자 오류 원문·코드를 URL에 복사하지 않으며 기존 앱 세션을 보존한다.

업무 API는 HttpOnly·Secure·SameSite=Lax 쿠키를 사용한다. 쓰기는 정확한 Origin과 세션 결합 CSRF 토큰을 확인한다. 세션 ID는 해시로, Supabase 토큰은 서버 전용 Fernet 키로 암호화해 저장한다. 로그인 복귀 화면은 home/form/saved만 허용한다.

## 이유와 영향

이미 업무 요청을 FastAPI로 통일했으므로 브라우저 토큰 인계 단계를 없앤다. 브라우저 토큰 탈취 경로를 줄이지만 XSS에 의한 사용자 권한 요청까지 막아 주지는 않는다. 서버의 토큰 저장·암호화 키·CSRF·동시 갱신·쿠키 프록시 설정을 관리해야 한다.

요청 시에만 갱신·재검증하고 기존 비용 기본값을 유지한다. 브라우저별 로그인 시작과 계정별 세션 발급을 각각 60초당 5회로 제한한다. 쿠키를 지우는 자동화 요청까지 막는 전역 봇 방어는 아니다. 트래픽 남용이 발생하면 신뢰할 수 있는 프록시 계층의 제한을 추가한다.

기존 Google/Kakao에 등록한 Supabase `/auth/v1/callback`은 유지한다. Supabase의 앱 Redirect URLs에는 새 BFF 콜백을 허용해야 한다. `0003_bff_oauth` 마이그레이션이 필요하며 배포 설정은 [06 구현·운영](../specs/06-implementation.md)을 따른다. 서비스 요금제 변경이나 운영 DB 적용을 포함하지 않는다.

근거: [Supabase PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow), [리다이렉트 허용 규칙](https://supabase.com/docs/guides/auth/redirect-urls), [Auth 코드 교환 구현](https://github.com/supabase/auth/blob/master/internal/api/token.go).
