# ADR 0002 · Supabase 인증 토큰과 세션을 FastAPI에서 관리

> 2026-11-16: OAuth 시작·코드 교환을 FastAPI로 이동하는 부분은 사용자 정정에 따라 [ADR 0004](0004-supabase-sdk-token-handoff.md)로 대체한다. 이후 최종 승인된 인증 방식은 [ADR 0005](0005-supabase-bff.md)다. 아래는 이전 결정 기록이다.

날짜: 2026-11-15. 상태: 사용자 요청의 보안 판단 위임에 따른 목표 방향 채택, 미구현. ADR 0001의 브라우저 인증 세션 유지 부분을 대체한다.

## 배경과 결정

사용자는 localStorage 저장을 없애고 프런트엔드 → FastAPI → PostgreSQL 흐름으로 바꾸도록 요청했다. 현재 서버는 이미 검증된 Supabase ID로 사용자를 식별한다. 사용자 ID 자체를 숨기는 것보다 장기 인증 토큰을 브라우저 JavaScript가 읽을 수 없게 만드는 데 보안상 이점이 있다.

Supabase의 Google·Kakao 로그인을 유지하되 FastAPI가 OAuth 로그인 트랜잭션·PKCE 코드 교환·토큰 갱신·로그아웃을 담당한다. 브라우저의 Supabase 인증 세션 유지를 제거하고, 무작위 불투명 세션 식별자만 HttpOnly 쿠키에 넣는다. 서버 DB에는 세션 식별자의 해시와 사용자 FK를 저장한다. 공급자 인증 토큰은 서버 전용 키로 암호화하고 응답·로그에 넣지 않는다. 세션 쿠키는 사용자 ID가 아니다.

## 필수 조건

- OAuth 로그인은 일회성 state와 브라우저 연계, PKCE·짧은 만료로 보호한다. Supabase의 실제 리다이렉트·PKCE 동작은 구현 시 검증한다. 임의 return URL을 허용하지 않는다.
- 인증 성공 시 새 세션 식별자를 발급해 세션 고정을 막는다. 매 요청에서 만료·폐기 상태와 소유권을 검사한다. 유휴·절대 만료와 제공자 폐기 재검증 주기는 구현 전에 정한다.
- 운영은 프런트엔드·백엔드를 별도 서버로 배포한다. 쿠키는 Secure·HttpOnly·브라우저에 보이는 API 응답 호스트의 host-only를 사용하고, SameSite는 실제 사이트 관계에 따라 Lax 또는 None으로 정한다. 서로 다른 사이트는 None·Secure 및 서드파티 쿠키 차단 검증이 필요하다. 구체 배포 계약은 [CORS 문서](../specs/05-cors.md)를 따른다. 쓰기는 Origin과 세션 결합 CSRF 토큰을 검사한다. HttpOnly도 XSS를 통한 사용자 권한의 요청 실행까지 막지는 않으므로 출력 안전성과 CSRF 보호를 유지한다.
- 서버 토큰 갱신은 세션별 동시성을 제어하고, 실패·폐기 시 재로그인을 요구한다. 로그아웃은 현재 서버 세션을 먼저 폐기하고 쿠키를 지운다. 모든 기기 로그아웃은 별도 요구가 생기기 전 추가하지 않는다.
- 사용자 ID는 필요하면 본인의 프로필 응답에 반환할 수 있으나 요청의 ID를 신원 증거로 신뢰하지 않는다. 권한은 서버 세션에서 얻은 사용자로 검사한다.

## 선택 이유와 비용

기존 Bearer 방식은 구현이 작지만 브라우저의 인증 저장·갱신에 의존한다. 서버 세션 방식은 인증 토큰의 JavaScript 노출을 줄이고 서버에서 세션을 폐기할 수 있다. 대신 인증 라우트·세션 DB·토큰 암호화·갱신 동시성·CSRF·쿠키 배포 설정을 함께 구현해야 한다. 브라우저 SDK에 HttpOnly 옵션만 추가하는 변경으로 끝나지 않는다.

전환 전에는 기존 인증을 유지하고, 새 흐름 검증 후 프런트와 API를 함께 전환한다. 기존 사용자에게 재로그인을 안내하고 앱이 소유한 이전 인증 저장 항목만 정리한다. 사용자의 전체 브라우저 저장소를 삭제하지 않는다.

근거: [OWASP 세션 관리](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [Supabase 서버 인증·PKCE](https://supabase.com/docs/guides/auth/server-side/advanced-guide). 이 ADR은 해당 보안 원칙을 Tripick의 FastAPI 구조에 적용한 설계 판단이다.
