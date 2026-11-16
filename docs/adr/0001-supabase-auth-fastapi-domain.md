# Supabase Auth를 유지하고 도메인 권한은 FastAPI에서 검사

> 최신 인증 경계는 [ADR 0005](0005-supabase-bff.md)를 따른다.

> 상태: 부분 대체됨(2026-11-15). 브라우저 세션·Bearer 전달 및 별도 백엔드 세션을 만들지 않는 결정은 [ADR 0002](0002-server-session.md)로 대체한다. Supabase Auth 제공자 유지·검증된 UUID 사용·FastAPI 소유권 검사는 유지한다. 아래 본문은 당시 결정의 기록이다.

2026-11-05 갱신. 프런트엔드의 Supabase Google 로그인을 유지하고, Kakao도 같은 Supabase Auth 경로로 추가한다. Supabase 브라우저 SDK가 인증 세션을 보관하며 FastAPI 자체 OAuth·세션은 만들지 않는다. FastAPI는 Supabase Auth의 `/auth/v1/user`에 접근 토큰을 검증하고 `users` 테이블에 Supabase 사용자 ID와 선택적 이메일을 저장한다. 향후 일정·게시·하트의 소유권은 FastAPI가 이 ID로 검사한다. Supabase가 확인된 같은 이메일의 제공자 신원을 연결하면 하나의 Tripick 계정으로 본다. 이 결정은 2026-11-04의 제공자별 계정 분리 규칙을 대체한다. Kakao 버튼과 실제 제공자 설정은 후속 작업이다.
