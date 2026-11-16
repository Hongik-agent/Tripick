# 05 · CORS와 쿠키 인증

> 2026-11-16 최종 결정: Supabase Auth를 유지하고 OAuth 시작·코드 교환·토큰 관리를 FastAPI BFF로 이전한다. [ADR 0005](../adr/0005-supabase-bff.md)를 따른다. 홈 세계지도 포함, 닉네임 대소문자 구분, 목록 10개, 비용 설정과 현재 구현 상태는 [06 구현·운영](06-implementation.md)을 따른다.
2026-11-15 목표 설정. 현재 `main.py`는 `config.py`의 `FRONTEND_ORIGIN` 한 개와 GET/POST/PUT/DELETE·Content-Type/CSRF/Idempotency/If-Match 헤더를 허용한다. credentials도 활성화했다. 2026-11-15 사용자 확인에 따르면 운영은 프런트엔드·백엔드를 각각 별도 서버로 운영하며 허용 경로(route) 설정 후 통신 성공을 확인했다. 이 사실과 앞으로 추가할 쿠키 인증·전체 업무 API의 검증 상태를 구분한다. 실제 운영 URL·인프라 설정과 응답 헤더는 이번 문서 수정에서 재확인하지 않았다.

## 별도 서버 통신 구성

브라우저가 프런트엔드 서버에서 화면을 받고, 기존에 허용한 경로를 통해 백엔드 API를 호출한다. 백엔드 주소로 직접 요청하는 구성이라면 API base URL을 프런트엔드 배포 설정으로 관리하고, 운영 프록시를 거친다면 공개 API 경로와 백엔드 전달 대상을 기록한다. 개발 Vite의 `/api` 프록시가 운영에서도 자동 적용된다고 가정하지 않는다.

사용자가 확인한 route 허용은 기존 통신 경로의 확인 기록이다. API 경로의 라우팅·프록시·방화벽 허용과 브라우저의 CORS 출처 허용은 구분해서 관리한다. CORS의 `allow_origins`에는 프런트엔드의 scheme·host·port를 넣으며 `/api/trips` 같은 경로를 넣지 않는다. 백엔드·게이트웨이에서는 [API 계약](04-api.md)의 실제 경로·메서드와 필요한 OPTIONS 통과를 확인한다. CORS는 서버의 인증·권한 검사나 네트워크 접근통제를 대신하지 않는다.

배포 시 실제 프런트엔드 Origin, 백엔드 API base URL, 기존 route 규칙의 적용 위치를 기록한다. 아직 확인하지 않은 주소를 예시 주소로 확정하지 않는다.

## 설정 책임과 허용 범위

API 개수가 늘어난다는 이유로 모든 출처를 허용하지 않는다. 실제 사용하는 메서드·헤더와 쿠키 인증 요구에 맞춰 확장한다.

| 설정 | 목표 |
|---|---|
| `allow_origins` | 환경별 프런트엔드 출처의 명시적 허용 목록. scheme·host·port 일치. `*` 금지 |
| `allow_methods` | `GET`, `POST`, `PUT`, `DELETE`. PATCH는 현재 계약에 없으므로 추가하지 않음 |
| `allow_headers` | `Content-Type`, `X-CSRF-Token`, `Idempotency-Key`, `If-Match`. 기존 Bearer 전환이 끝나 `Authorization`은 허용하지 않음 |
| `allow_credentials` | 서버 세션 쿠키 전송을 위해 `True` |
| `expose_headers` | 현재 응답 계약에 추가 노출 헤더 없음. 버전은 JSON으로 반환 |

`OPTIONS` preflight는 CORSMiddleware가 처리한다. Origin·Access-Control-Request-Method·Access-Control-Request-Headers 조합으로 검증하며 OPTIONS 업무 라우트를 따로 만들지 않는다.

환경변수 로딩·파싱·검증은 `backend/app/config.py`에 집중한다. 기존 `FRONTEND_ORIGIN`을 유지할 수 있으면 유지하고, 여러 출처가 실제 필요한 경우 `FRONTEND_ORIGINS` 목록 설정으로 확장하면서 예제·배포 설정도 변경한다. 출처에는 URL 경로·쿼리를 넣지 않으며 누락·빈 값·와일드카드는 시작 시 거부한다. `main.py`는 검증된 설정을 import해 미들웨어에 전달한다.

## 쿠키·CSRF·배포

- 운영은 프런트엔드·백엔드 별도 서버 구성과 기존 통신 경로를 유지하고 HTTPS를 사용한다. 별도 서버인지와 브라우저에서 같은 사이트인지 여부는 다르다. 실제 도메인·scheme을 확인해 아래 쿠키 정책을 선택한다. 개발에서는 기존 Vite 프록시의 쿠키 전달도 검증한다.
- 운영 세션 쿠키는 `HttpOnly; Secure; Path=/`와 브라우저에 보이는 API 응답 호스트 전용(host-only)으로 설정한다. 프런트·API가 같은 사이트이면 `SameSite=Lax`, 서로 다른 사이트에서 쿠키를 보내야 하면 `SameSite=None; Secure`가 필요하다. `__Host-` 접두사를 사용하면 Domain을 지정하지 않는다. 로컬 HTTP 개발의 Secure 예외는 개발 설정에서만 허용한다.
- 브라우저 요청은 `credentials: "include"`를 사용한다. CORS 허용만으로 로그인·소유권·CSRF가 검증되지는 않는다. 쓰기 요청은 허용 Origin과 세션에 결합된 CSRF 토큰을 함께 검사한다.
- HTTPS의 `app.example.com`과 `api.example.com`은 서로 다른 Origin이지만 같은 사이트인 구성의 예다. 실제 운영 주소는 아니다. 서로 다른 사이트이면 SameSite=None만으로 성공을 보장하지 못하며 브라우저의 서드파티 쿠키 차단을 검증해야 한다. 차단되면 별도 서버는 유지하면서 공통 사이트의 도메인 또는 프록시 제공 방식을 결정한다.
- Google Maps 렌더링 키의 웹사이트 제한은 FastAPI CORS와 별도다. 지도 도메인을 FastAPI의 허용 프런트 출처에 추가하지 않는다.

## 검증

기존 통신 성공은 사용자 확인 기록이며 새 서버 세션의 Set-Cookie 저장·후속 쿠키 전송·로그인 유지까지 검증한 기록은 아니다. 운영 브라우저에서 이를 추가 확인한다. 허용 출처에서 각 메서드·헤더의 preflight, 실제 credential 요청, 인증 오류 응답의 CORS 헤더를 확인한다. 미허용 출처·헤더·메서드는 허용되지 않아야 한다. 세션 없음·위조 CSRF·타인 일정·DB 장애도 각각 올바르게 실패해야 한다. `backend/tests/test_api.py`에서 BFF OAuth·서버 세션·CORS 계약을 검증한다.

근거: [FastAPI CORS 공식 문서](https://fastapi.tiangolo.com/tutorial/cors/).

쿠키 근거: [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
