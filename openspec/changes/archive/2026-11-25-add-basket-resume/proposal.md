# Proposal

## Why

책 몇 권을 검색해 담고 서가에서 30분쯤 꺼내 읽고 돌아오면, 이용 상한(로그인부터 3분)으로 이미 로그아웃되어 담은 책이 비어 있다. 지금 담은 책은 화면 메모리에만 있어 처음부터 다시 검색해야 한다. 24e `add-member-login`으로 회원 세션이 생겼으니 담은 책을 회원에 붙여 짧게 보관할 수 있다(roadmap 24c, 2026-11-24 탐색).

## What Changes

- **담은 책 보관**: 새 테이블 `basket_items`. 회원·기관 도서·담은 시각만 저장하고 검색어·대화는 저장하지 않는다. 담은 시각부터 **3시간** 고정으로 보관하고(다시 담아도 늘지 않음), 한 회원이 **10권**까지 담는다. 회원을 지우면 함께 지운다.
- **API** `/basket`(직원 토큰 + 회원 세션 `X-Member-Token`, 없거나 끝나면 403): 불러오기 `GET`, 담기 `PUT /basket/{id}`, 빼기 `DELETE /basket/{id}`, 비우기 `DELETE /basket`. 불러올 때 책 값은 지금 상태로 새로 만들고(대출 중이면 "모두 대출 중", 제적·분실로 추천할 수 없는 책은 숨김), 응답에 회원 값이 없다.
- **이용자 화면**
  - 로그인 전에는 카드의 [담기]가 없다. 로그인하면 담은 책을 자동으로 불러온다(문구 없이 숫자만).
  - 담기·빼기는 서버가 성공한 뒤 화면에 반영한다. 실패 문구는 둘(10권 상한, "잠시 뒤 다시 눌러 주세요")이다.
  - 담은 책 칸에 [모두 빼기]가 있고, 외부 대출 기관의 줄에는 "대출 상태 … 기준"이 보인다.
  - 로그아웃(버튼·무입력·상한·403)은 화면의 담은 책만 비우고 서버에는 남긴다. [새 대화]는 그대로다.
  - 로그인 전 [담기]가 사라지므로 "로그인 전에 누른 [담기]를 로그인 뒤 이어서 함"을 없앤다(빌리기·희망도서만 남음).
- **경계**: 담은 책은 추천·AI 사서·운영 에이전트 분석·노출 기록·대화 기록·로그 어디에도 쓰지 않는다. 테이블을 언급할 수 있는 파일을 허용 목록으로 소스 검사한다.
- **스키마 스펙 정리**: `platform/database-schema` 본문이 `member_sessions`를 빠뜨려 28개로 어긋나 있어 `basket_items`와 함께 30개로 맞춘다.
- **받아들이는 위험**: 비밀번호 없는 번호 로그인이라 번호를 아는 사람은 남의 담은 책을 3시간 동안 볼 수 있다. 문자 인증·실패 횟수 제한과 함께 미룬다(보관을 3시간으로 짧게 두고 [모두 빼기]를 주는 것으로 줄임).
- **범위 밖**(design의 미룰 일): 담은 책 칸의 [빌리기]·서가 순 정렬·출력, 찾을 수 없게 된 책 알림, 동시 담기의 상한 잠금, 보관 시간·상한 조정, 자연어 SQL 허용 테이블 관리, Playwright.

## Capabilities

### New Capabilities

- `circulation/member-basket`: 회원별 담은 책 보관(3시간, 10권), 담기·빼기·비우기·불러오기, 기관 분리, 지금 상태로 보이기, 어디에도 쓰지 않는 경계

### Modified Capabilities

- `platform/web-ui`: 브라우저 저장, 로그인이 필요한 동작, 두 시계의 로그아웃 뜻, 회원 토큰의 행선지, 기존 API 목록, 담은 책 화면
- `platform/database-schema`: 테이블 목록(`member_sessions`, `basket_items`)과 기관 간 참조

## Impact

- 스키마: 새 `basket_items`(Alembic 마이그레이션 하나), `TENANT_TABLES` 등록. 개발 DB는 백업한 뒤 `&&`로 이어 적용한다.
- 서버: `app/library/models/circulation.py`(모델), `services/basket.py`·`api/basket.py`·`schemas/basket.py`(새), `recommendation/cards.py`(재사용, 바꾸지 않음), `services/chat.py`(1분 정리 작업에 만료 행 삭제 한 줄), `app/core/config.py`(`basket_keep_hours`, `basket_limit`), `app/main.py`(라우터), `app/models.py`.
- 화면: `app/web/public/shared/api.js`, `librarian/basket.js`·`main.js`·`index.html`·`librarian.css`, 카드 [담기]의 로그인 표시 연동.
- 테스트: 새 `tests/circulation/test_member_basket.py`, 경계 테스트, `test_database_schema.py`(30개), `test_web_ui.py`.
- 문서: `app/library/README.md`, `app/web/README.md`, `docs/glossary.md`, `docs/roadmap.md`, `CLAUDE.md`.
- 외부 API·LLM 호출: 없음(evals 없음).
