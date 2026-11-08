# Tripick API·JSON 계약

> 기준: 2026-11-06 코드, [제품 범위](00-overview.md), [목표 구조](02-design-and-decisions.md), AI Ready PRD v0.9 및 2026-11-06 사용자 결정. **구현됨**과 **설계안**을 구별한다. 이 문서의 설계안은 현재 호출 가능한 API가 아니다.

## 읽기 원칙

- 브라우저는 Supabase Auth로 로그인하고 FastAPI에는 `Authorization: Bearer <Supabase access token>`을 보낸다. FastAPI 자체 OAuth·쿠키 세션 경로는 사용하지 않는다.
- FastAPI는 검증된 Supabase 사용자 ID로 소유권을 판단한다. 요청 본문의 `userId`, `ownerId`, `email`은 신원 근거로 받지 않는다.
- 날짜별 일정은 `days[]`로 전달한다. 현재 프런트엔드의 평면 `places[]`, 모의 좌표·시간·거리, `Date.now()` ID는 API 계약이 아니다.
- 장소·영업시간·경로·이동시간은 서버가 조회 근거를 검증한 값만 확정 결과에 넣는다. 생성 결과와 저장 일정은 다른 자원이다.
- 인증이 필요한 쓰기 요청은 성공 응답을 받은 뒤 화면 상태를 갱신한다. 실패 시 저장 원본과 사용자 작업 내용을 유지한다.

## 현재 구현된 API

### `GET /health` · 구현됨

요청 본문과 인증이 없다. DB `SELECT 1` 성공 시 `200 {"status":"ok"}`, DB 오류 시 `503 {"detail":"database unavailable"}`. 코드: `backend/app/main.py`.

### `PUT /api/users/me` · 구현됨

프런트엔드는 Supabase 인증 상태 변경 후 본문 없이 호출한다.

```http
PUT /api/users/me
Authorization: Bearer <Supabase access token>
```

```json
{"id":"550e8400-e29b-41d4-a716-446655440000","email":null}
```

`id`는 Supabase Auth 사용자 UUID다. `email`은 문자열 또는 `null`이다. 서버는 Supabase `/auth/v1/user`로 토큰을 확인하고 Google·Kakao 제공자만 받아 `users` 행을 생성·갱신한다. 프런트는 응답 `id`가 현재 Supabase 세션의 사용자 ID와 같을 때만 로그인 상태로 전환한다.

| HTTP | FastAPI `detail` | 의미 |
|---|---|---|
| 401 | `invalid session` | Bearer 토큰 누락·형식 오류·세션 무효 |
| 403 | `unsupported login provider` | Google·Kakao 외 제공자 |
| 502 | `authentication service unavailable` 또는 `invalid authentication response` | Supabase 호출·응답 오류 |
| 503 | `database unavailable` | DB 쓰기 실패 |

현재 DB에는 `users(id, email, created_at)`만 있다. 일정·생성·게시·하트 API와 테이블은 아직 없다.

## 공통 설계 규칙 · 설계안

- 향후 경로는 기존 `/api/users/me`와 맞춰 `/api/...`를 사용한다. 옛 `Tripick_03_API_데이터계약.md`의 `/api/v1`·서비스 세션 쿠키는 현행 구현 계약이 아니다.
- JSON 필드명은 `camelCase`, ID·선택지는 언어와 무관한 문자열, 날짜는 `YYYY-MM-DD`, 시각은 시간대가 포함된 ISO 8601 문자열, 거리·소요 시간은 숫자형 `distanceMeters`·`durationMinutes`를 제안한다. 한국어 UI 문구(`"3일"`, `"구글맵"`)는 표시값이다.
- `mapProvider`: `google | naver | kakao`. 해외에서는 `google`만 허용한다. Google 우선 검증 후 국내 3종 선택을 MVP에 포함한다.
- 인증된 API는 매 요청마다 Bearer 토큰을 검증한다. 읽기·편집·삭제 대상이 없거나 타인 소유면 동일한 404로 처리해 타인 데이터 존재 여부를 노출하지 않는다.
- 계정의 기준은 Supabase가 검증한 사용자 UUID다. Google·Kakao의 이메일이 같거나 다르다는 사실로 서버가 별도 병합·분리하지 않는다.
- 예산은 2026-11-06 사용자 결정으로 이번 MVP의 입력·검증·JSON에서 제외한다. 이전 PRD F01의 예산 필수 조건보다 이 결정이 우선한다.
- 인원은 `1 | 2 | 3 | 4_plus` 구간이다. `4_plus`를 정확히 4명으로 계산하지 않는다. 이동수단은 `walking | transit | driving`이다.
- 이동수단 하나를 일정 전체에 적용한다. `driving`은 도로 경로·예상 이동시간만 뜻하며 렌터카 예약·주차·통행료 계산은 MVP 범위 밖이다. `4_plus`로 인원별 비용·좌석 수를 보증하지 않는다.
- 여행 기간은 시작일과 종료일을 포함해 1~14일이다. 선택한 수단으로 실제 경로를 확인할 수 없으면 다른 수단으로 바꾸지 않고 생성 작업을 실패 처리한다. 실패·부분 결과는 저장할 수 없다.
- 한 일정에는 여행지 하나만 허용한다. 현재 프런트엔드 선택 화면의 여행지 목록을 서버 `destinations[]`의 기준으로 삼고 자유 검색·다중 여행지는 MVP에서 제외한다. 제주·발리처럼 도시가 아닌 지역도 있으므로 API 필드명은 `destination`을 사용한다.
- 생성·최초 저장·재저장 등 재시도로 중복 비용이나 데이터가 생길 수 있는 요청에는 `Idempotency-Key`를 사용한다. 같은 계정·키·본문 재시도는 기존 결과를 반환하고 같은 키로 다른 본문을 보내면 409다.
- 저장·삭제는 서버 트랜잭션으로 처리한다. 활성 저장 일정은 계정당 최대 3개이며 생성·재생성은 슬롯을 차지하지 않는다. 같은 일정을 재저장해도 개수는 그대로다.
- 기본 오류는 새 API에서 `{"error":{"code":"...","message":"...","retryable":false}}`로 제안한다. 현재 구현된 두 API는 FastAPI 기본 `{"detail":"..."}`을 반환하므로 혼동하지 않는다.

## MVP API 목록 · 설계안

이 표의 모든 경로는 미구현이다. ID는 서버 발급 문자열이며 프런트의 `Date.now()` 숫자 ID를 보내지 않는다.

| Method·경로 | 역할 | 인증 |
|---|---|---|
| `GET /api/planning-options` | 허용 목적지·동행·인원 구간·취향·밀도·이동수단 선택지 | 필요 |
| `POST /api/generations` | 조건 검증·새 일정 생성 요청 | 필요 |
| `GET /api/generations/{generationId}` | 생성 진행·실패 상태 | 본인만 |
| `GET /api/drafts/{draftId}` | 생성 결과와 검증 근거 | 본인만 |
| `GET /api/places?destinationId=&query=` | 저장 일정 편집용 실제 장소 후보 | 필요 |
| `GET /api/trips` / `GET /api/trips/{tripId}` | 내 저장 일정 목록·상세 | 본인만 |
| `POST /api/trips` | 검증된 생성 결과 최초 저장 | 필요 |
| `POST /api/trips/{tripId}/edit-drafts` | 저장 일정의 변경을 재검증할 작업본 생성 | 본인만 |
| `GET /api/trips/{tripId}/edit-drafts/{editDraftId}` | 변경 작업본 상태·결과 | 본인만 |
| `PUT /api/trips/{tripId}` | 유효 작업본을 같은 일정에 재저장 | 본인만 |
| `DELETE /api/trips/{tripId}` | 저장 일정 전체 삭제 | 본인만 |
| `PUT /api/users/me/nickname` | 공개 닉네임 설정·변경 | 필요 |
| `GET /api/posts` / `GET /api/posts/{postId}` | 공개 게시 일정 목록·상세 | 불필요 |
| `POST /api/trips/{tripId}/publication` / `DELETE /api/trips/{tripId}/publication` | 게시·게시 취소 | 본인만 |
| `PUT /api/posts/{postId}/heart` / `DELETE /api/posts/{postId}/heart` | 하트 추가·취소 | 필요 |

### 선택지와 생성 요청

`GET /api/planning-options`는 서버가 허용하는 ID와 한국어 표시명을 반환한다. 프런트는 표시명을 API 값으로 보내지 않는다. 목적지 목록·최대 여행일수 등 미정 범위는 PRD D04 결정 후 고정한다. `optionsVersion`은 선택지 갱신 중 오래된 폼 제출을 감지한다.

```json
{
  "optionsVersion": "v1",
  "maxTripDays": 14,
  "destinations": [{"id":"jp-tokyo","label":"도쿄","countryCode":"JP","timeZone":"Asia/Tokyo","mapProviders":["google"],"transportModes":["walking","transit","driving"]}],
  "companionTypes": [{"id":"friends","label":"친구와"}],
  "partySizes": [{"id":"1","label":"1명"},{"id":"2","label":"2명"},{"id":"3","label":"3명"},{"id":"4_plus","label":"4명 이상"}],
  "interests": [{"id":"food","label":"맛집 탐방"}],
  "paces": [{"id":"relaxed","label":"여유롭게"}],
  "transportModes": [{"id":"walking","label":"도보"},{"id":"transit","label":"대중교통"},{"id":"driving","label":"자동차"}]
}
```

위 선택지는 API 필드 형태를 설명한다. `destinations[]`의 전체 후보는 현재 `frontend/src/App.tsx`의 여행지 선택 목록을 옮기며, 각 항목에 안정적인 ID·국가 코드·시간대·허용 지도/이동수단을 부여한다. 이 화면에 없는 여행지를 임의 문자열로 요청할 수 없다. 지역별 이동수단·지도 제공 여부는 실제 외부 API 검증 후 옵션에 반영한다. UI가 필수 선택지를 받지 못하면 생성 버튼을 활성화하지 않는다.

현재 프런트엔드의 한국어 선택값은 다음 ID로 바꿔 전송한다. 목적지 ID는 `destinations[]`가 준 값을 사용하며 표시 이름을 그대로 보내지 않는다.

| 화면 선택 | API 값 |
|---|---|
| 혼자 / 친구와 / 연인과 / 가족과 | `solo` / `friends` / `partner` / `family` |
| 1명 / 2명 / 3명 / 4명 이상 | `1` / `2` / `3` / `4_plus` |
| 맛집 탐방 / 자연과 휴식 / 예술과 문화 | `food` / `nature` / `culture` |
| 쇼핑 / 액티비티 / 현지문화 | `shopping` / `activity` / `local_culture` |
| 여유롭게 / 알차게 / 빼곡하게 | `relaxed` / `balanced` / `packed` |
| 네이버 지도 / 카카오맵 / 구글맵 | `naver` / `kakao` / `google` |
| 도보 / 대중교통 / 자동차 | `walking` / `transit` / `driving` |

`POST /api/generations`는 `Idempotency-Key`와 아래 JSON을 받는다. `startDate`·`endDate`는 필수다. `dayCount`는 날짜로 서버가 계산하므로 클라이언트가 `"3일"`을 보내지 않는다. 현재 UI의 인원 `<select>`는 상태에 연결되지 않았으므로 구현 때 `party.sizeBand`와 연동해야 한다.

```json
{
  "optionsVersion": "v1",
  "destinationId": "jp-tokyo",
  "startDate": "2026-12-01",
  "endDate": "2026-12-01",
  "party": {"typeId":"friends","sizeBand":"2","withChildren":false,"withSeniors":false},
  "interestIds": ["food"],
  "paceId": "relaxed",
  "transportMode": "transit",
  "mapProvider": "google"
}
```

서버는 날짜 역전·1~14일 범위·필수값·허용 ID·국내/해외 지도 제한·인원 구간·지역별 이동수단 지원을 Agent나 유료 Tool 호출 전에 검사한다. `solo` 동행 유형이면 인원 구간은 `1`만 허용한다. 저장 일정이 이미 3개여도 생성·재생성은 허용한다. 정상 수락은 `202`다.

```json
{"generationId":"gen_123","status":"queued"}
```

`GET /api/generations/{generationId}`는 다음 형태다. `completed`는 작업 종료만 뜻한다. 저장 가능 여부는 초안의 `status`와 서버 검증 결과로 판단한다.

```json
{"generationId":"gen_123","status":"completed","draftId":"draft_123","error":null}
```

작업 상태는 `queued | running | completed | failed`, 초안 상태는 `success | partial | needs_input | failed`다. `partial`, `needs_input`, `failed`는 저장할 수 없다. 전체 실패 때 프런트는 기존 조건과 이전 결과를 유지하고 사용자가 다시 요청할 때만 재생성한다.

선택 수단의 경로가 실제 조회에서 나오지 않으면 `{"generationId":"gen_123","status":"failed","draftId":null,"error":{"code":"ROUTE_UNAVAILABLE","message":"선택한 이동수단의 경로를 확인할 수 없습니다.","retryable":false}}`처럼 실패 이유를 반환한다. 수단을 자동 대체하지 않는다.

### 초안·저장 일정 JSON

`GET /api/drafts/{draftId}`의 **형태 예시**다. 장소 이름·좌표·시간·경로 ID는 설명용 값이며 실제 근거를 뜻하지 않는다. 실제 API는 조회 제공자, 확인 시각, 검증 상태가 일치하는 항목만 `success`로 반환한다. `date`는 앞서 선택한 실제 여행 날짜다.

```json
{
  "id": "draft_123",
  "version": 1,
  "status": "success",
  "destination": {"id":"jp-tokyo","name":"도쿄","countryCode":"JP","timeZone":"Asia/Tokyo"},
  "mapProvider": "google",
  "transportMode": "transit",
  "days": [{
    "day": 1,
    "date": "2026-12-01",
    "items": [{
      "id": "item_1",
      "order": 1,
      "place": {"id":"place_1","provider":"google","providerPlaceId":"example_place_id","name":"예시 장소","address":"예시 주소","latitude":35.0,"longitude":139.0,"checkedAt":"2026-11-06T10:00:00+09:00"},
      "startTime": "10:00",
      "endTime": "11:00",
      "reason": "선택한 취향에 맞는 방문 장소"
    }],
    "legs": []
  }],
  "warnings": [],
  "unmetConstraints": []
}
```

두 방문 장소 사이의 `legs[]` 항목은 `{"fromItemId":"item_1","toItemId":"item_2","mode":"transit","durationMinutes":20,"distanceMeters":1200,"provider":"google","checkedAt":"2026-11-06T10:00:00+09:00","status":"verified"}` 형태다. 모든 구간의 `mode`는 요청한 일정 전체의 `transportMode`와 일치한다. 경로 조회 실패를 0분·0m로 대체하지 않는다. 제공자별 표시·저장 약관 확인 전에는 저장 금지 원본 필드를 확정 DB에 복제하지 않는다.

### 저장·조회·편집

`POST /api/trips`는 `Idempotency-Key`와 `{"draftId":"draft_123","draftVersion":1}`을 받는다. 저장 버튼 클릭이 명시적 승인이다. 서버는 본인 소유의 `success` 초안과 버전·근거를 확인하고, 같은 계정의 활성 저장 개수를 트랜잭션에서 잠근 뒤 저장한다. 정상은 `201`이다.

```json
{"id":"trip_123","version":1,"savedCount":1,"limit":3,"remainingSlots":2}
```

`GET /api/trips`는 본인 일정 요약과 저장 한도를 함께 반환한다. `GET /api/trips/{tripId}`는 같은 요약 정보에 초안과 동일한 `days[]` 구조, 여행 조건·저장 버전·게시 여부를 더한다. 타인·없는·삭제된 일정은 404다.

```json
{
  "items": [{"id":"trip_123","version":1,"destinationName":"도쿄","startDate":"2026-12-01","endDate":"2026-12-01","dayCount":1,"publishedPostId":null}],
  "capacity": {"limit":3,"savedCount":1,"remainingSlots":2}
}
```

상세 응답에서는 `id`, `version`, `conditions`, `mapProvider`, `transportMode`, `days[]`, `publishedPostId`를 반환한다. `conditions`는 생성 요청에서 서버가 승인한 선택 ID와 날짜·인원 구간을 담고, `days[]`의 각 item·leg는 위 초안 JSON과 같은 형태다. 목록의 요약만으로 방문 시각이나 경로를 재구성하지 않는다.

저장 후 편집은 클라이언트가 결과를 직접 덮어쓰지 않는다. `GET /api/places?destinationId=jp-tokyo&query=...`로 장소 후보의 서버 참조를 받은 뒤 `POST /api/trips/{tripId}/edit-drafts`에 `baseTripVersion`과 `operations[]`를 보낸다. 장소 후보 응답 형태는 `{"items":[{"placeRef":"place_123","name":"예시 장소","address":"예시 주소","latitude":35.0,"longitude":139.0,"provider":"google","checkedAt":"2026-11-06T10:00:00+09:00"}]}`이다. 연산은 장소 추가·제거·방문 순서 변경으로 제한한다. 서버는 영향 구간과 시간·영업 상태를 다시 검증한다. 예시는 순서 변경이다.

```json
{"baseTripVersion":1,"operations":[{"type":"reorder","day":1,"itemIds":["item_2","item_1"]}]}
```

정상 수락은 `202 {"editDraftId":"edit_123","status":"running"}`. `GET /api/trips/{tripId}/edit-drafts/{editDraftId}`는 `status`, `version`, `baseTripVersion`, 변경된 `days[]`, `warnings[]`를 반환한다. 서버 검증이 끝난 `valid` 작업본만 `PUT /api/trips/{tripId}`로 재저장한다.

연산별 본문 요소는 장소 추가 `{"type":"add","day":1,"placeRef":"place_123","afterItemId":"item_1"}`, 방문 제거 `{"type":"remove","itemId":"item_1"}`, 순서 변경 `{"type":"reorder","day":1,"itemIds":["item_2","item_1"]}`이다. 서버는 `placeRef`와 item 소유권·순서를 검증하고 변경된 이동 구간을 다시 조회한다.

```json
{"editDraftId":"edit_123","editVersion":1,"baseTripVersion":1}
```

`PUT` 요청은 `Idempotency-Key`와 `If-Match: 1`을 사용한다. 정상은 같은 `tripId`와 증가한 `version`을 반환하며 저장 개수는 변하지 않는다. 버전이 오래됐거나 작업본이 무효면 409, 실패하면 원본을 유지한다. `DELETE /api/trips/{tripId}`는 `If-Match`를 요구하고 성공 시 204다. 원본 일정 전체 삭제는 연결된 게시물·하트를 같은 트랜잭션에서 삭제한 후 저장 슬롯을 반환한다.

### 공개 닉네임·커뮤니티

`PUT /api/users/me/nickname`은 `{"nickname":"여행하는곰"}`을 받아 현재 사용자의 공개 닉네임을 설정·변경하고 `200 {"nickname":"여행하는곰"}`을 반환한다. 앞뒤 공백을 제거한 뒤 2~20자이며 한글·영문·숫자·단어 사이 공백만 허용한다. 닉네임은 전체 사용자 간 유일하며 첫 게시 전에 필요하다. 중복은 409. 닉네임 변경 시 기존 게시물 조회에도 새 이름을 표시한다.

`POST /api/trips/{tripId}/publication`은 본문 없이 저장된 본인 일정을 즉시 게시한다. 생성 결과나 타인 일정은 게시할 수 없고 같은 저장 일정의 중복 게시를 막는다. 게시 사본에는 여행지·일수·테마·방문 장소·순서와 지도에 필요한 공개 좌표·장소 ID만 넣는다. `mapPlaceId`는 공개 응답용 불투명 ID이며 제공자 원본 ID와 별개다. 정확한 여행 날짜·개인 조건·계정 ID·이메일은 공개 응답에 넣지 않는다. 정상은 `201 {"postId":"post_123"}`이다. `DELETE /api/trips/{tripId}/publication`은 본인 게시물을 취소하고 성공 시 204다. 다시 게시하면 새 게시 시각과 하트 0개로 시작한다.

`GET /api/posts`와 `GET /api/posts/{postId}`는 비로그인 상태에서도 읽을 수 있다. 로그인 사용자가 Bearer 토큰을 보내면 `heartedByMe`를 계산한다. 목록은 하트 수 내림차순 → 게시 시각 오름차순 → 게시물 ID 오름차순이다. 상세는 목록 항목과 같은 공개 필드를 단일 객체로 반환한다. 응답의 `authorNickname`은 작성자의 **현재** 닉네임이다. 아래 예시에는 비공개 사용자 ID나 실제 여행 날짜가 없다.

```json
{
  "items": [{
    "id": "post_123",
    "authorNickname": "여행하는곰",
    "destinationName": "도쿄",
    "dayCount": 1,
    "theme": "맛집 탐방",
    "mapProvider": "google",
    "places": [{"mapPlaceId":"place_1","day":1,"order":1,"name":"예시 장소","latitude":35.0,"longitude":139.0}],
    "heartCount": 0,
    "heartedByMe": false,
    "publishedAt": "2026-11-06T10:00:00+09:00"
  }]
}
```

목록 페이지네이션 크기·커서 형태는 미정이다. `heartedByMe`는 비로그인 방문자에게 `false`다. `PUT /api/posts/{postId}/heart`는 현재 계정의 하트를 추가하고, `DELETE`는 취소한다. 본인 게시물에도 하트를 허용한다. 같은 계정·게시물 조합의 중복 하트는 DB 유일성으로 막는다. 두 요청은 `200 {"heartCount":1,"heartedByMe":true}`와 같은 현재 상태를 반환한다.

### 설계안 오류 코드

| HTTP·code | 처리 |
|---|---|
| `401 AUTH_REQUIRED` | 로그인 필요. 저장·게시 요청 자동 재실행 금지 |
| `403 UNSUPPORTED_PROVIDER` | 허용되지 않은 로그인 제공자 |
| `404 RESOURCE_NOT_FOUND` | 타인·없는·삭제된 자원을 같은 방식으로 처리 |
| `409 SAVED_TRIP_LIMIT_EXCEEDED` | 네 번째 신규 저장 차단. 생성·재저장은 허용 |
| `409 VERSION_CONFLICT` | 최신 일정 확인 후 사용자가 다시 결정 |
| `409 INVALID_DRAFT` | 미검증·부분·오래된 생성/편집 작업본 저장 차단 |
| `409 NICKNAME_TAKEN` | 다른 공개 닉네임 선택 |
| `409 ALREADY_PUBLISHED` | 같은 저장 일정 중복 게시 차단 |
| `409 IDEMPOTENCY_CONFLICT` | 같은 키로 다른 본문 재시도 차단 |
| `422 INVALID_SELECTION` | 필수·허용값·날짜·인원·지도 조건 오류 |
| `422 UNSUPPORTED_TRANSPORT` | 선택 지역에서 해당 이동수단 제공 불가 |
| `429 RATE_LIMITED` | 생성 비용·빈도 보호. 저장 슬롯과 별도 |
| `502 EXTERNAL_DATA_UNAVAILABLE` | 인증·장소·경로 등 외부 제공자 오류 |
| `503 DATABASE_UNAVAILABLE` | DB 장애. 저장·삭제 성공으로 표시하지 않음 |

## 미정 계약

- 장소·경로 제공자의 지역·이동수단 지원과 저장·표시 약관: PRD D02/D05, 현재 문서 D-M01.
- 여행지별 지도·이동수단 지원: 현재 선택 목록을 대상으로 실제 외부 API 검증이 필요하다. 인원은 `4_plus`를 정확한 수로 해석하지 않는다. 예산은 이번 MVP에서 제외한다.
- 실행당 Agent·Tool·시간·비용 한도: PRD D06/D12. 저장 3개 제한과 별개다.
- 초안·작업본 만료, 개인정보 삭제·보관, 증거 재조회: PRD D07.
- 미검증/부분 생성 결과는 현재 기준선에서 확정 저장을 차단한다. 부분 결과 허용 변경은 PRD D10 결정이 필요하다.

## 근거와 차이

- `frontend/src/App.tsx`의 조건 입력·화면 흐름, `frontend/src/community.tsx`의 모의 게시 규칙, `backend/app/main.py`의 현재 라우트·오류, `backend/app/models.py`와 첫 Alembic 마이그레이션을 확인했다.
- `C:/ChatGPT/Tripick/outputs/ai_ready_20261025/Tripick_PRD_AI_Ready_v0.9_20261025.md`의 확정/제안/미정 구분을 유지했다.
- `C:/ChatGPT/Tripick/outputs/Tripick_03_API_데이터계약.md`는 이전 설계 참고 자료다. 그 문서의 자체 OAuth·쿠키 세션과 F09 공유 제외는 최신 결정에 따라 이 문서에 옮기지 않았다.
