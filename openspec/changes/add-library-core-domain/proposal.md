# Proposal

## Why

프로젝트 방향이 무인 서점 에이전트에서 **사서 없는 작은도서관용 AI 사서**로 바뀌었다 (`docs/design.md` "문제 정의와 방향을 바꾼 이유"). 지금 코드와 스펙은 이전 도메인(책방 재고, 손님 문의, 기관 납품)을 기준으로 되어 있어서, 새 도메인에는 맞지 않는다.

- 기관(도서관) 개념이 없다.
- 소장 사본 개념이 없다.
- 대출 개념이 없다.
- 로그인 개념이 없다.

이후 AI 사서·운영 에이전트·평가가 모두 "로그인한 도서관의 장서와 대출" 위에서 동작한다. 그래서 1주차에는 이전 도메인을 정리하고, **기관 분리가 코드와 DB에서 강제되는 장서·대출 기반**을 먼저 만든다.

## What Changes

- **BREAKING** 이전 도메인을 정리한다.
  - 지우는 것: 무인 서점의 테이블 11개, 그 모델·service·API·시드·테스트, 컨텍스트 경계 검사
  - 지우는 스펙: 6개 capability
  - 초기 마이그레이션은 새 도메인 기준으로 다시 만든다. 운영 배포 전이라 이전 데이터를 옮기지 않는다.
- **기관(libraries)과 기관 분리**
  - 모든 기관 데이터는 `library_id`를 가진다.
  - 조회·쓰기는 로그인한 계정의 기관 범위로 강제한다.
  - 다른 기관의 데이터는 존재하지 않는 것처럼 404로 응답한다.
  - 대출·사본·회원이 서로 다른 기관을 가리키지 못하도록 DB에서도 막는다.
- **관리자·키오스크 인증**
  - 기관별 직원 계정(staff_users)에는 관리자(`admin`)와 도서관 PC용 키오스크(`kiosk`) 역할이 있다.
  - 비밀번호로 로그인하면 bearer 토큰을 발급하고, 로그아웃할 수 있다.
  - 키오스크는 조회와 대출만 할 수 있고, 관리 작업은 관리자만 한다.
- **도서(books, 기관 공통)**
  - 도서를 ISBN이 아니라 내부 id로 식별한다. ISBN이 없는 책(오래된 책, 기증 도서, 지역 자료)도 등록할 수 있게 하기 위해서다. 경로가 `/books/{isbn}`에서 `/books/{id}`로 바뀐다 (**BREAKING**).
  - ISBN이 있으면 1주차의 ISBN 규칙(정규화, 체크 디지트, 중복 금지)을 그대로 적용한다.
  - 정가도 선택으로 바꾼다. 기증 도서는 ISBN과 정가를 모르는 경우가 많다.
  - 분류와 어린이/일반 구분(`audience`, 근거 `audience_source`)을 추가한다.
  - 자동 분류는 2주차에 한다. 이번에는 기본값 `general`과 관리자 지정만 있다.
- **소장 사본(holdings)**
  - 입수 구분을 가진다: 매입·납품(구입가와 ISBN 필수) 또는 기증(기증처 선택, ISBN·가격 없어도 됨).
  - 등록번호(기관 안에서 유일), 청구기호, 서가 위치, 상태(대출 가능 / 대출 중 / 분실 / 훼손), 출처(직접 등록 / 가져오기)를 가진다.
  - CRUD를 제공하고, 도서 목록에 기관별 소장 여부와 대출 가능 권수를 붙인다.
- **회원(members)**: 기관 안에서 유일한 회원번호와 이름만 가진다 (최소 정보).
- **대출(loans)**: 빌림·반납·대출 중 표시까지만 한다.
  - 자체 대출 기관(`loan_mode = internal`)만 대출을 처리한다.
  - 대출 가능 상태의 사본만 빌릴 수 있다.
  - 반납 예정일은 기관의 기본 대출 기간으로 계산한다.
- **시드 데이터**: 두 기관과 기관별 계정을 만든다. 공통 도서, 기관별 사본·회원·대출(연체 포함)도 만든다.
  - 두 기관 중 하나는 자체 대출 기관, 하나는 가져오기 기관이다.

**범위 밖 (이번 change에서 하지 않음)**

- 장서 가져오기(엑셀·CSV), 외부 API 서지정보 채움, 어린이 도서 자동 분류 → `add-holdings-import`
- LLM 호출, 에이전트, 임베딩(pgvector), 추천 노출 기록 → 3주차 이후
- 큐레이션, 희망도서, 구매 요청서, 승인 흐름, 대화 기록 테이블 → 해당 change에서 만든다
- 예약·연장·연체료, 비밀번호 재설정, 기관 생성 API (기관은 시드나 관리 스크립트로 만든다)

## Capabilities

### New Capabilities

- `library/libraries`: 기관 정보, 운영 방식(`loan_mode`), 기본 대출 기간. 기관 데이터 분리 규칙(로그인한 기관 범위, 다른 기관 데이터는 404)
- `library/staff-auth`: 직원 계정과 역할(admin / kiosk), 로그인·로그아웃, 토큰 만료, 역할별 접근 제한, 직원 계정 관리
- `catalog/holdings`: 소장 사본 등록·조회·수정·삭제, 등록번호 유일성, 상태, 도서별 소장·대출 가능 권수
- `circulation/members`: 회원 등록·조회·수정·삭제, 기관 안 회원번호 유일성
- `circulation/loans`: 대출·반납, 대출 가능 조건, 반납 예정일, 운영 방식에 따른 대출 차단, 대출 목록

### Modified Capabilities

- `catalog/books`
  - 도서를 기관 공통 서지정보로 정의하고, 내부 id로 식별한다. ISBN과 정가는 선택이 된다.
  - 분류·어린이/일반 구분 필드를 추가한다.
  - 쓰기는 관리자만 할 수 있게 한다.
  - 삭제 거부 기준을 "매장 재고"에서 "소장 사본"으로 바꾼다.
- `platform/database-schema`
  - "컨텍스트별 테이블 소유"와 "컨텍스트 간 참조 방향"을 없앤다.
  - 대신 "기관 데이터 테이블은 library_id를 가진다"와 "기관 간 참조 금지"를 둔다.
  - 테이블 수를 새 구성으로 바꾼다.
- `platform/dev-seed-data`: 생성 데이터를 새 도메인(기관, 계정, 도서, 사본, 회원, 대출)으로 바꾼다.
- 이전 도메인 capability 6개는 요구사항을 모두 제거한다.
  - `catalog/store-inventory`
  - `storefront/customer-interactions`
  - `owner-ops/curation-content`
  - `supply/institutions`
  - `supply/order-lists`
  - `supply/quote-drafts`

## Impact

- **지우는 코드**
  - `app/models/{catalog,storefront,owner_ops,supply}.py`
  - `app/services/{catalog,supply}/`
  - `app/api/{catalog,supply}.py`
  - `app/seed/{catalog,supply}.py`
  - 관련 테스트, `tests/platform/test_boundaries.py`
  - 초기 마이그레이션 `896d5140154e`
- **새 코드**
  - `app/core/security.py`: 비밀번호 해시, 토큰
  - `app/core/deps.py`: 현재 직원, 기관, 역할 의존성
  - 도메인별 models·schemas·services·api: libraries, staff, books, holdings, members, loans
  - 새 초기 마이그레이션, 새 시드
- **새 API**
  - 인증: `/auth/login`, `/auth/logout`, `/auth/me`
  - 기관과 직원: `/library`, `/staff`
  - 장서와 대출: `/books`, `/holdings`, `/members`, `/loans`
- **설정**: `.env`에 토큰 만료 시간(관리자·키오스크)과 시드 계정 비밀번호를 추가한다.
- **의존성**: 새로 추가하지 않는다. 비밀번호 해시는 표준 라이브러리 `hashlib.scrypt`를 쓴다.
- **로컬 DB**: 이 change를 적용하기 전에 `alembic downgrade base`로 이전 스키마를 내려야 한다 (tasks에 포함).
- **문서**: `README.md`의 실행 안내와 도메인 설명, `CLAUDE.md` 디렉터리 구조를 새 코드에 맞춘다.
