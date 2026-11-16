# 01 · 현재 구현과 남은 차이

2026-11-16 코드 기준. 최신 인증 결정은 [ADR 0005](../adr/0005-supabase-bff.md), 설정은 [06 구현·운영](06-implementation.md)을 따른다.

## 프런트엔드

- `auth.ts`: BFF 로그인 시작 API를 호출하고 Supabase authorize URL로 이동한다. 브라우저에서 코드 교환·토큰 보관을 하지 않는다.
- `api.ts`: 쿠키·CSRF API 호출, 세션 복원, 공개 조회 시 만료 쿠키 정리 후 한 번 재조회. 이전 인증 항목 정리는 사용자 확인으로 완료했으며 localStorage 정리 코드는 제거했다.
- `App.tsx`: 서버 일정·커뮤니티·하트·닉네임 연결, 저장 실패 표시, 1~7일·인원·이동수단 선택. 실제 생성·편집은 준비 중으로 표시한다.
- `WorldMap.tsx`: React Simple Maps와 로컬 Natural Earth 기반 world-atlas, 서버에서 읽은 저장 일정 핀.
- `GoogleMap.tsx`: 기존 서울 전용 로더를 재사용한 모든 여행지 바탕 지도. 장소·실제 동선 마커는 후속 단계다.

## 백엔드

- `auth.py`: Supabase OAuth 시작·PKCE 코드 교환·암호화·불투명 쿠키 세션·요청 시 갱신·CSRF·현재 기기 로그아웃.
- `domain.py`: 일정 조회·삭제·검증 초안 저장/재저장 경계, 3개 한도·멱등성·버전·소유권, 공개 닉네임·게시 사본·하트.
- `planning.py`: 기존 선택 여행지 49곳, 중심 좌표와 안정적 ID, 날짜·선택지 검증. 지역별 실제 경로 지원은 아직 검증하지 않았다.
- `models.py`, `0002_server_storage`: 사용자 닉네임·auth_sessions·trips·posts·post_hearts·idempotency_keys. 기존 users 보존. `0003_bff_oauth`에 일회용 로그인 트랜잭션 추가.
- `main.py`, `config.py`: 오류 구조, 정확한 Origin·CORS, no-store, 환경설정 집중. `/health` DB 실패 503.

## 후속 범위

OpenAI SDK 생성, 실제 장소·영업시간·경로 검증, 편집·재생성 작업 저장소, 실제 경로 표시. 운영에서는 미검증 초안을 저장할 수 없고 개발 테스트에서만 검증 초안을 공급한다. 이 단계는 전체 MVP 완료 선언이 아니다.

실제 Google/Kakao OAuth 왕복, 운영 Vercel Set-Cookie 전달과 Google Maps 렌더링, 운영 DB 마이그레이션은 별도 배포 환경 확인이 필요하다. 과거 2026-11-05 검증 결과를 현재 변경의 검증 근거로 재사용하지 않는다.
