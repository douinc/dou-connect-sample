# Plan — 새록 파트너 API 표준 v1.1 반영 (`partner-api`)

계약 SSOT: dou-connect `resources/docs/saylog/guide.md` (파트너 API 등록 `PUT/GET /v1/partner-api`,
담당 환자 목록·직원 조회 POST 본문 + `next` 커서, 스코프 `partner-api:read/write`).
짝 PR: douinc/dou-connect#20.

## 태스크 (실행 방식: 부모 인라인 순차 — 한 PR 안의 강결합 사슬, 독립 PR 단위 없음)

| # | 태스크 | 상태 |
|---|---|---|
| 1 | 클라이언트: `identity-provider` → `partner-api` 스키마(`service`/`oauth`/`endpoints`)·메서드, `validate_partner_api(sample)` | [x] |
| 2 | 서버: `POST /api/patients` 본문 + `next` 커서(두 모드), `POST /api/employee`(서비스 토큰), `no-store`, 422 미반향 | [x] |
| 3 | 서비스 토큰 검증기(dou-connect JWKS, EdDSA, iss/aud/scopes/exp, provider_code) — PyJWT | [x] |
| 4 | 스크립트: `register_partner_api.py`(user/service 두 모드), `e2e.py`·`local_oauth_demo.py`·`validate_api.py` | [x] |
| 5 | README·`.env.example`: IdP 용어 → 파트너 API, 두 모드, POST 본문·커서, 스코프 | [x] |
| 6 | 잔존 grep 0, verify(서버 기동 + curl), PR | [x] |

## 판단 기록

- **환자 목록 인증 모드는 설정(`PATIENTS_AUTH_MODE=user|service`)으로 고정** — 계약상 한 파트너는 한 모드로만
  호출되므로 토큰 종류로 분기하지 않고 명시 설정. 직원 조회는 항상 서비스 토큰.
- **서비스 토큰 검증에 PyJWT 추가** — dou-connect 토큰은 EdDSA(리소스 서버 가이드)이고 python-jose는 EdDSA
  미지원. 가이드의 Python 예시도 PyJWT. 파트너 IdP 쪽(RS256 발급·검증)은 기존 python-jose 유지.
- **페이지 파라미터 한쪽만 와도 422가 아니라 기본값 적용**(page=1, pageSize=50, 최대 100 clamp) — 가이드는
  "둘 다 없으면 전체"만 규정. 기존 샘플의 "쌍으로만" 400 규칙은 폐기.
- **`next`는 항상 키 존재**(마지막·전체 반환이면 `null`) — 검증기가 `next` 필드 존재를 본다.
- **`provider_code` 불일치는 404 무본문**(리소스 서버 가이드 "매핑 없는 병원 404") — 단일 병원 샘플은
  `DOU_CONNECT_PROVIDER_CODE`와 대조, 미설정이면 검사 생략.
- 가정(미확정): carevoice main의 검증기는 아직 GET+쿼리 — 새록 측 구현 반영 전까지 e2e 3단계는 실패할 수 있음.

## 완료 기록

- 테스트 163 passed (기존 110 + 53), ruff·mypy strict clean, 잔존 grep 0.
- verify: uvicorn 실서버 기동 — service 모드(직원 200/404 무본문/422 미반향/커서 3페이지
  75명 무중복/403 scope/타 병원 404), user 모드(`python -m app` + local_oauth_demo) 확인.
- 기존 "page/pageSize 한쪽만 오면 400" 규칙 폐기 → 기본값 적용 (가이드에 그런 규칙 없음).
