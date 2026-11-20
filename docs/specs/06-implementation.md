# 06 · 구현과 운영 설정

2026-11-16. 인증은 [ADR 0005](../adr/0005-supabase-bff.md)가 최신 결정이다. Supabase Auth를 유지하고 OAuth·토큰 관리를 FastAPI BFF로 이전한다. 개인 일정·게시물·하트는 FastAPI→PostgreSQL로 저장한다.

## 구현 경계

- 서버 OAuth 시작·PKCE 코드 교환·암호화·HttpOnly 세션·CSRF·CORS·요청 시 갱신·로그아웃.
- 기존 `0001_users` 보존, `0002_server_storage`에 세션·일정·게시물·하트·멱등키와 닉네임 추가. `0003_bff_oauth`에 일회용 OAuth 트랜잭션 추가.
- 일정 소유권, 최대 3개 원자적 한도, 버전 충돌, 멱등 재시도, 공개 사본, 원본 삭제 cascade.
- 닉네임은 공백 없이 완성형 한글·영문·숫자 2~20자. 대소문자를 구분하며 내 계정에서 변경한다.
- 커뮤니티는 정해진 순서로 10개씩 offset 조회. 순위 변동 시 페이지 중복·누락 가능, 새로고침 시 재조회하며 UI는 ID 중복 제거.
- 42개 여행지 선택(한국 우선, 인도네시아·에든버러·세비야·리옹·타이중 제외), 1~7일, 인원 1/2/3/4/5_plus, 도보/대중교통/자차. 지역별 실제 경로 지원은 미검증이므로 `destinations[].transportModes`는 빈 배열이고 생성은 비활성이다.
- 홈 세계지도는 React Simple Maps와 로컬 world-atlas. 조건 요약에서는 외부 장소 검색에 사용할 지도 서비스를 선택한다. Google Maps는 샘플 결과와 저장·게시 상세의 바탕 지도다. [샘플 일정과 장소 검색](01-current-state.md#샘플-일정과-장소-검색) 참고. 장소 마커·경로·AI 생성·편집 재검증은 후속 단계다.
- 운영에서는 생성 503, 검증되지 않은 초안 저장 409. 개발 테스트에서만 신뢰 초안 공급 dependency를 교체한다. 모의 결과를 운영에서 성공·저장 가능 상태로 표시하지 않는다.
- 브라우저의 기존 모의 여행 데이터는 자동 업로드·일괄 삭제하지 않는다. 이전 Supabase 인증 항목 정리 완료를 사용자에게 확인받아 임시 정리 코드와 프런트 Supabase URL 설정을 제거했다.

## 배포

1. 백엔드 `.env.example`의 필수값을 설정한다. Supabase URL·publishable/anon 키는 백엔드 인증에 사용한다. 프런트에는 제한된 Google Maps 브라우저 키가 필요하고 Supabase SDK 키는 제거한다. 기본값과 같은 비용 설정은 `.env.example`에서 생략했다.
2. Google/Kakao 제공자에 등록한 Supabase `/auth/v1/callback`은 유지한다. **Supabase Authentication → URL Configuration → Redirect URLs**에는 `https://tripick-dun.vercel.app/api/auth/callback\?state=*`를 추가한다. 역슬래시는 glob의 `?`를 리터럴로 취급하며, `*`는 임의 state 값만 허용한다. 자체 호스팅이면 같은 패턴을 Auth의 redirect allow list에 적용한다. Site URL은 프런트 앱 주소다. 개발은 실제 localhost Origin으로 동일한 콜백 패턴을 추가한다. 제공자 콜백과 앱 콜백은 서로 다른 설정이다. [Supabase 리다이렉트 규칙](https://supabase.com/docs/guides/auth/redirect-urls)을 참고한다.
3. Vercel 대시보드의 기존 `^/api/(.*)$` → Railway `/api/$1` rewrite를 유지한다. 브라우저 API는 상대 경로 `/api`다. 외부 rewrite 캐싱을 비활성화하고 `Set-Cookie`, `Cache-Control: private, no-store`가 전달되는지 확인한다. 새 중복 rewrite 파일은 추가하지 않는다.
4. Railway의 `FRONTEND_ORIGIN`은 실제 Vercel Origin(끝 슬래시 없음). 브라우저에 보이는 Vercel 호스트 전용 Secure·HttpOnly·SameSite=Lax 쿠키를 사용한다. 개발은 localhost/127.0.0.1 HTTP만 Secure 예외를 허용한다.
5. `SESSION_ENCRYPTION_KEY`는 `cryptography.fernet.Fernet.generate_key()`로 만든 서버 비밀값이다. `.env`/서버 비밀 설정에만 저장한다. 키를 바꾸면 이전 세션 토큰은 복호화할 수 없어 재로그인이 필요하다.
6. DB 백업 후 `alembic upgrade head`. 운영 DB 적용은 이 작업에서 실행하지 않는다. `alembic upgrade head --sql`은 자격증명 없이 가능하다.
7. OAuth 콜백 쿼리의 일회용 code·state가 접근 로그에 남지 않게 Uvicorn은 `--no-access-log`로 실행하고 외부 프록시·모니터링도 쿼리/쿠키/인증 헤더를 기록하지 않도록 설정한다.
8. Supabase 프로젝트 설정은 이 저장소에서 자동 변경하지 않는다. 자체 호스팅 여부·요금제는 확인하지 않았으며 호출을 줄이는 설정만 제공한다. Supabase JWT 기본 수명을 불필요하게 짧게 줄이지 않는다.

## 비용 설정

모두 초 단위이며 `config.py`에 주석이 있다. 유휴 86400, 절대 604800, 재검증 1800, 활동 기록 300, OAuth 600, 갱신 여유 60, 브라우저별 로그인 시작·계정별 세션 발급 제한 각각 60초당 5회, 멱등키 보관 86400이다. 주기 작업·브라우저 폴링은 없으며 사용 중인 세션만 필요할 때 갱신한다. 유휴 기록 간격 때문에 최대 5분 일찍 만료될 수 있다. Supabase 재조회 주기는 외부 Google/Kakao 로그아웃 탐지 SLA가 아니다. 브라우저 쿠키를 지우면 시작 제한은 초기화되므로 전역 봇 방어로 간주하지 않는다. 비용 설정은 호출량을 줄이며 호스팅 기본료를 없애는 설정은 아니다.

React Simple Maps(MIT), world-atlas(ISC), Natural Earth(public domain)는 라이선스 사용료가 없다. 데이터 라이선스 고지를 `frontend/public/maps`에 포함한다. Google Maps, Vercel, Railway, Supabase의 호스팅·API 요금은 별도이며 전체 서비스 무료를 보장하지 않는다.

## 지도 데이터 출처

world-atlas 2.0.2 `countries-110m.json`은 Natural Earth 4.1.0 기반 세계 개요다. [world-atlas](https://github.com/topojson/world-atlas), [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), [React Simple Maps](https://github.com/zcreativelabs/react-simple-maps).

여행지 중심은 [GeoNames](https://www.geonames.org/about.html)의 CC BY 데이터를 바탕으로 소수점 정밀도를 줄이거나 대표점을 선택했다. 국가별 도시 표(JP, CN, TW, KR, FR, IT, ES, GB, US, ID)와 개별 지명 좌표를 검토했다. 오키나와는 [UNT 지명 기록](https://digital.library.unt.edu/explore/locations/p19247/), 강릉은 [NGA 지명 기록](https://geonames.nga.mil/geon-ags/rest/services/RESEARCH/GIS_OUTPUT/MapServer/0/4675322)을 사용했다. 제주는 섬, 발리는 섬 대표점이다. 이 데이터는 장소·경로 근거가 아니다.

## 공개 검토 범위

현재 docs의 문서에서 실제 키·토큰·비밀번호·개인정보는 발견하지 못했다. 접근할 수 없는 로컬 절대경로는 원본 문서명으로 바꿨다. 과거 Git 이력과 저장소 밖의 원본 자료는 이 검토 범위에 포함되지 않는다. 실제 Supabase 프로젝트 URL은 문서에 추가하지 않는다.

## 2026-11-16 검증 결과

- PostgreSQL 18 전용 로컬 DB에서 빈 DB→head, 기존 0001_users→head, 테스트 DB downgrade→upgrade 통과.
- 백엔드 통합 테스트 16개 통과: 서버 PKCE 교환·암호화·state/브라우저 연계·콜백 재사용/동시 교환 1회·취소·동시 갱신 1회·세션 만료·시작/발급 제한·CSRF/CORS·타인 접근·버전·멱등성·동시 저장 3개 한도·닉네임·공개 필드·하트·cascade·무효 초안.
- 프런트 TypeScript 검사와 Vite 배포 빌드 통과. 브라우저 SDK와 이전 토큰 인계 테스트는 제거하고 BFF 테스트로 대체했다.
- 실제 OAuth·운영 쿠키·Google 지도 렌더링·운영 DB 적용은 수행하지 않았다.
