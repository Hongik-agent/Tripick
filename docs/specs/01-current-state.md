# 01 · 현재 구현과 남은 차이

2026-11-21 코드 기준이며, 국내 방문지 후보 연동은 2026-11-24에 확인했다. 최신 인증 결정은 [ADR 0005](../adr/0005-supabase-bff.md), 설정은 [06 구현·운영](06-implementation.md)을 따른다.

## 프런트엔드

- `auth.ts`: BFF 로그인 시작 API를 호출하고 Supabase authorize URL로 이동한다. 브라우저에서 코드 교환·토큰 보관을 하지 않는다.
- `api.ts`: 쿠키·CSRF API 호출, 세션 복원, 공개 조회 시 만료 쿠키 정리 후 한 번 재조회. 이전 인증 항목 정리는 사용자 확인으로 완료했으며 localStorage 정리 코드는 제거했다.
- `App.tsx`: 서버 일정·커뮤니티·하트·닉네임 연결, 저장 실패 표시, 1~7일 여행 조건 입력과 선택한 모델로 AI 일정 생성. 이동수단은 결과 화면에서 구간별로 선택한다.
- `WorldMap.tsx`: React Simple Maps와 로컬 Natural Earth 기반 world-atlas, 서버에서 읽은 저장 일정 핀.
- `GoogleMap.tsx`: 기존 서울 전용 로더를 재사용한 모든 여행지 바탕 지도. 장소·실제 동선 마커는 후속 단계다.

### AI 일정 생성과 장소 검색

조건 요약에서 모델을 선택하고 **AI 일정 생성**을 누르면 서버가 작업을 접수한다. 검증이 끝나면 결과 화면에 날짜별 방문 장소와 시각, 확인된 구간의 도보 시간·거리를 표시한다. 이동수단 버튼에서 도보·대중교통·자동차의 경로를 확인하고 변경할 수 있다. 검증 실패나 사용 한도 초과 시에는 한국어 안내를 표시한다. [일정 생성 명세](07-openai-agents.md)

**국내 방문지 후보**는 한국관광공사의 국문 관광정보 OpenAPI(TourAPI)를 활용한다. 백엔드로 도시별 장소명·분류·좌표를 미리 조회한다. 일정 요청이 들어오면 사용자의 여행지와 취향에 맞춰 서로 가까운 장소를 추려 모델에 참고 후보로 전달한다. 해당 조건에 맞는 API 자료가 아직 없으면 기본 후보를 사용한다. 최종 방문 장소와 도보 경로는 각각 Google Places와 Google Routes로 확인한다. [한국관광공사 국문 관광정보 서비스](https://www.data.go.kr/data/15101578/openapi.do)

오른쪽 🗺️ 버튼은 여행지와 바로 위 장소명을 함께 검색한다. 마지막 장소에도 표시한다. 국내 여행에서는 구글맵·네이버 지도·카카오맵 중 선택할 수 있고, 해외 여행에서는 구글맵을 사용한다. 외부 검색 링크에는 지도 API 키가 필요 없다. 검색 서비스 선택은 결과 화면에 내장한 Google 바탕 지도와 독립적이다. [장소 검색 링크 #11](https://github.com/Hongik-agent/Tripick/issues/11)

구글맵 검색 링크에는 장소명(`query`)과 검증된 Google Place ID(`query_place_id`)를 함께 전달한다. 이렇게 하면 동명 장소를 구분하고 일정에 담긴 장소의 상세 카드를 열 가능성이 가장 높다. [Google Maps URL 가이드](https://developers.google.com/maps/architecture/maps-url)

## 백엔드

- `auth.py`: Supabase OAuth 시작·PKCE 코드 교환·암호화·불투명 쿠키 세션·요청 시 갱신·CSRF·현재 기기 로그아웃.
- `domain.py`: 일정 조회·삭제·검증 초안 저장/재저장 경계, 3개 한도·멱등성·버전·소유권, 공개 닉네임·게시 사본·하트.
- `planning.py`: 선택 여행지 42곳, 중심 좌표와 안정적 ID, 날짜·선택지 검증. 지역별 실제 경로 지원은 아직 검증하지 않았다.
- `models.py`, `0002_server_storage`: 사용자 닉네임·auth_sessions·trips·posts·post_hearts·idempotency_keys. 기존 users 보존. `0003_bff_oauth`에 일회용 로그인 트랜잭션 추가.
- `main.py`, `config.py`: 오류 구조, 정확한 Origin·CORS, no-store, 환경설정 집중. `/health` DB 실패 503.

## 후속 범위

일정 편집 후 재검증, 지도 위 장소 마커와 실제 경로 표시가 남아 있다.

실제 Google/Kakao OAuth 왕복, 운영 Vercel Set-Cookie 전달과 Google Maps 렌더링, 운영 DB 마이그레이션은 별도 배포 환경 확인이 필요하다. 과거 2026-11-05 검증 결과를 현재 변경의 검증 근거로 재사용하지 않는다.
