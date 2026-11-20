# 01 · 현재 구현과 남은 차이

2026-11-20 코드 기준. 최신 인증 결정은 [ADR 0005](../adr/0005-supabase-bff.md), 설정은 [06 구현·운영](06-implementation.md)을 따른다.

## 프런트엔드

- `auth.ts`: BFF 로그인 시작 API를 호출하고 Supabase authorize URL로 이동한다. 브라우저에서 코드 교환·토큰 보관을 하지 않는다.
- `api.ts`: 쿠키·CSRF API 호출, 세션 복원, 공개 조회 시 만료 쿠키 정리 후 한 번 재조회. 이전 인증 항목 정리는 사용자 확인으로 완료했으며 localStorage 정리 코드는 제거했다.
- `App.tsx`: 서버 일정·커뮤니티·하트·닉네임 연결, 저장 실패 표시, 1~7일 여행 조건 입력과 샘플 일정 미리보기. 이동수단은 결과 화면에서 구간별로 선택한다.
- `WorldMap.tsx`: React Simple Maps와 로컬 Natural Earth 기반 world-atlas, 서버에서 읽은 저장 일정 핀.
- `GoogleMap.tsx`: 기존 서울 전용 로더를 재사용한 모든 여행지 바탕 지도. 장소·실제 동선 마커는 후속 단계다.

### 샘플 일정과 장소 검색

여행 조건 확인 화면에는 조건 요약, 지도 선택, 안내, 샘플 일정 만들기 버튼 사이에 여백을 둔다. 지도는 결과 화면에서 여행지 중심의 Google 바탕 지도로 표시한다. [지도 표시 시점 #8](https://github.com/Hongik-agent/Tripick/issues/8) · [패널 여백 #9](https://github.com/Hongik-agent/Tripick/issues/9)

[프런트엔드 샘플 데이터](../../frontend/src/sampleItinerary.ts)의 `sampleStops`는 국가 코드와 여행 일차를 받아 화면용 장소 ID, 이름, 방문 시각을 반환한다. 홍콩 첫날은 미드레벨 에스컬레이터 → 침차이키 → 센트럴 마켓 순서이고, 다른 여행지와 일차에는 산책 코스·현지 식당·전망 명소를 사용한다. `sampleDistances`는 두 구간의 예시 거리(m), `sampleModes`는 도보·대중교통·자동차의 아이콘과 구간별 예시 시간(분)을 제공한다.

샘플 결과에서 두 장소 사이의 왼쪽 버튼을 누르면 해당 구간의 이동수단을 바꿀 수 있다. 홍콩 첫 구간의 기본 표시는 ‘도보 · 2분 · 153m’다. 선택은 일차와 구간별로 유지하며 새 샘플을 만들면 초기화한다. 샘플 생성은 브라우저 안에서 처리하며 서버에 저장하거나 게시하지 않는다. OpenAI Agents SDK 연동과 실제 경로 검증은 후속 작업이다. [구간별 이동수단 #10](https://github.com/Hongik-agent/Tripick/issues/10)

오른쪽 🗺️ 버튼은 여행지와 바로 위 장소명을 함께 검색한다. 마지막 장소에도 표시한다. 국내 여행에서는 구글맵·네이버 지도·카카오맵 중 선택할 수 있고, 해외 여행에서는 구글맵을 사용한다. 외부 검색 링크에는 지도 API 키가 필요 없다. 검색 서비스 선택은 결과 화면에 내장한 Google 바탕 지도와 독립적이다. [장소 검색 링크 #11](https://github.com/Hongik-agent/Tripick/issues/11)

실제 일정 생성 연동 후에는 장소 검증 과정에서 Google Places API가 반환한 `googleMapsUri`가 있으면 구글맵 버튼에 그대로 사용한다. 직접 검색 링크를 구성할 때는 장소명(`query`)과 검증된 Google Place ID(`query_place_id`)를 함께 전달한다. 이렇게 하면 동명 장소를 구분하고 일정에 담긴 장소의 상세 카드를 열 가능성이 가장 높다. [Google Maps URL 가이드](https://developers.google.com/maps/architecture/maps-url)

## 백엔드

- `auth.py`: Supabase OAuth 시작·PKCE 코드 교환·암호화·불투명 쿠키 세션·요청 시 갱신·CSRF·현재 기기 로그아웃.
- `domain.py`: 일정 조회·삭제·검증 초안 저장/재저장 경계, 3개 한도·멱등성·버전·소유권, 공개 닉네임·게시 사본·하트.
- `planning.py`: 선택 여행지 42곳, 중심 좌표와 안정적 ID, 날짜·선택지 검증. 지역별 실제 경로 지원은 아직 검증하지 않았다.
- `models.py`, `0002_server_storage`: 사용자 닉네임·auth_sessions·trips·posts·post_hearts·idempotency_keys. 기존 users 보존. `0003_bff_oauth`에 일회용 로그인 트랜잭션 추가.
- `main.py`, `config.py`: 오류 구조, 정확한 Origin·CORS, no-store, 환경설정 집중. `/health` DB 실패 503.

## 후속 범위

OpenAI SDK 생성, 실제 장소·영업시간·경로 검증, 편집·재생성 작업 저장소, 실제 경로 표시. 운영에서는 미검증 초안을 저장할 수 없고 개발 테스트에서만 검증 초안을 공급한다. 이 단계는 전체 MVP 완료 선언이 아니다.

실제 Google/Kakao OAuth 왕복, 운영 Vercel Set-Cookie 전달과 Google Maps 렌더링, 운영 DB 마이그레이션은 별도 배포 환경 확인이 필요하다. 과거 2026-11-05 검증 결과를 현재 변경의 검증 근거로 재사용하지 않는다.
