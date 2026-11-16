# Supabase SDK 로그인 유지와 인증 토큰 서버 인계

> 이후 사용자 승인으로 [ADR 0005](0005-supabase-bff.md)의 BFF 방식으로 대체했다. 아래는 당시 결정 기록이다.

2026-11-16 사용자 정정으로 채택. Supabase 브라우저 SDK로 Google·Kakao 로그인과 PKCE 코드 교환을 유지하고, 받은 access/refresh token은 localStorage에 저장하지 않고 FastAPI로 보내 PostgreSQL에 암호화 보관한다. ADR 0002의 OAuth 시작·콜백을 FastAPI로 이전하는 부분을 대체하며, 서버 세션·소유권·CSRF 원칙은 유지한다.

SDK는 세션을 메모리에만 저장하는 사용자 storage 어댑터를 쓴다. 리다이렉트 왕복에 필요한 PKCE 검증값만 sessionStorage에 짧게 보관하며 인증 토큰은 sessionStorage에도 저장하지 않는다. 현재 SDK는 `persistSession:false`이면 사용자 storage를 무시하므로 `persistSession:true`와 메모리 어댑터를 함께 사용한다. 자동 갱신과 자동 URL 세션 감지를 끄고 콜백을 한 번만 처리한다. 서버 인계 후 메모리를 비우고 페이지를 새로 열며, 서버가 보관할 refresh token을 폐기하는 브라우저 `signOut()`은 호출하지 않는다.

FastAPI는 Origin·Supabase 신원·refresh token의 동일 사용자 여부를 확인하고 새 불투명 세션 쿠키를 발급한다. 이후 업무 API는 HttpOnly 쿠키와 메모리 CSRF 토큰으로 호출한다. 로그인 중 토큰은 브라우저 JavaScript 메모리에 있으므로 완전히 JavaScript에 노출되지 않는 BFF 방식이라고 설명하지 않는다.

비용을 줄이기 위해 요청이 있을 때만 갱신·재검증하며 유휴 24시간·절대 7일·재검증 30분·활동 기록 5분·로그인 10분을 기본으로 사용한다. 장기간 세션과 느린 재검증은 외부 폐기 확인 지연을 감수하는 선택이다. 모든 값과 이유는 `backend/app/config.py`에 주석과 함께 둔다.
