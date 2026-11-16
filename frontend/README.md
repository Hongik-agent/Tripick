# Tripick frontend

React 19 + Vite + Tailwind CSS. Supabase Auth의 Google·Kakao 로그인을 FastAPI BFF로 연결한다. OAuth 코드 교환·토큰 저장·갱신은 서버가 맡고 브라우저는 HttpOnly 세션 쿠키를 사용한다. 인증 토큰·PKCE verifier를 브라우저 저장소에 보관하지 않는다.

## 개발

`pnpm install`, `pnpm exec tsc --noEmit`, `pnpm build`. `.env.example`을 참고해 Google Maps 키를 설정한다. 개발 `/api`는 Vite가 FastAPI 8000 포트로 프록시한다. 운영은 Vercel 대시보드의 기존 `/api` → Railway rewrite를 사용한다.

## 현재 기능

로그인·내 일정 조회/삭제·공개 닉네임·게시/게시 취소·하트·10개씩 조회와 홈 세계지도, 49개 여행지 Google Maps 바탕을 연결했다. 실제 AI 생성·장소/경로 검증과 편집은 후속 단계다. 운영 모의 결과의 생성 성공·저장은 제공하지 않는다. 서버 저장 CRUD는 테스트에서 검증 초안을 주입해 확인한다.

홈 지도 라이브러리·데이터에는 사용료가 없고 Google Maps API 사용료는 별도다. 기존 브라우저 모의 여행 자료는 자동 이전·삭제하지 않는다.

설정과 검증 범위는 [구현·운영 문서](../docs/specs/06-implementation.md), 인증 결정은 [ADR 0005](../docs/adr/0005-supabase-bff.md)를 따른다.
