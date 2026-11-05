# Tasks

## 1. 이전 도메인 정리

- [x] 1.1 로컬 개발 DB와 테스트 DB를 이전 리비전이 있는 상태에서 `uv run alembic downgrade base`로 내린다. 두 DB 모두 `alembic_version`이 비어 있는지 확인한다
- [x] 1.2 이전 도메인 코드를 지운다. 지운 뒤 `uv run python -c "import app.main"`이 실패하는 지점이 새 코드로 채울 곳뿐인지 확인한다
  - `app/models/{catalog,storefront,owner_ops,supply}.py`
  - `app/services/{catalog,supply}/`
  - `app/api/{catalog,supply}.py`
  - `app/seed/{catalog,supply}.py`
  - `migrations/versions/*896d5140154e*`
  - `tests/{catalog,storefront,owner_ops,supply}/`
  - `tests/platform/test_boundaries.py`
- [x] 1.3 `app/matching/isbn.py`를 `app/core/isbn.py`로 옮기고 import를 고친다. `tests/matching/test_isbn.py`도 `tests/core/test_isbn.py`로 옮겨 통과시킨다

## 2. 설정과 인증 기반

- [x] 2.1 `app/core/config.py`에 설정을 추가하고 `.env.example`에도 함께 적는다
  - `ADMIN_TOKEN_HOURS`, `KIOSK_TOKEN_HOURS`
  - `LIBRARY_TIMEZONE`(기본 `Asia/Seoul`)
  - `SEED_ADMIN_PASSWORD`, `SEED_KIOSK_PASSWORD`
  - `PASSWORD_SCRYPT_N`(테스트에서 낮출 수 있게)
- [x] 2.2 `app/core/security.py`(scrypt 해시·검증, 토큰 생성·SHA-256)와 `app/core/clock.py`(`today()`)를 작성한다. `tests/core/test_security.py`로 다음을 확인한다
  - 해시에 원문이 없음
  - 틀린 비밀번호는 거부
  - 같은 비밀번호도 해시가 다름
- [x] 2.3 `app/services/errors.py`의 도메인 예외는 그대로 두고, `app/core/deps.py`를 작성한다. 동작은 2.4 이후의 API 테스트로 확인한다
  - `CurrentStaff`: 토큰 → `StaffContext`, 실패 시 401
  - `require_admin`: 키오스크면 403

## 3. 모델과 마이그레이션

- [x] 3.1 `app/models/library.py`(Library, StaffUser, StaffSession), `catalog.py`(Book, Holding), `circulation.py`(Member, Loan)를 design.md 5번 표대로 작성한다
  - StrEnum, CHECK, 복합 외래 키, 부분 UNIQUE 인덱스를 포함한다
  - `app/models/__init__.py`에 `SHARED_TABLES`, `TENANT_TABLES`를 둔다
- [x] 3.2 초기 리비전을 autogenerate하고 검토한다. 확인할 것: CHECK, 복합 FK, 부분 인덱스, server default. 개발 DB에서 `alembic upgrade head` → `downgrade base` → `upgrade head`와 `alembic check`가 되는지 확인한다
- [x] 3.3 `tests/conftest.py`와 `tests/helpers.py`를 새 도메인으로 바꾼다
  - 두 기관 fixture, 기관별 admin·kiosk 계정과 인증 클라이언트
  - DB 직접 쓰기 도우미 (`add_library`, `add_book`, `add_holding`, `add_member`)
- [x] 3.4 `tests/platform/test_database_schema.py`에 platform/database-schema delta의 시나리오를 테스트로 작성하고 통과시킨다
  - 7개 테이블, downgrade 후 재적용, autogenerate diff 없음
  - 기관 데이터 테이블 구분, library_id 누락
  - 다른 기관 사본·회원으로 대출 직접 저장

## 4. 기관과 인증 API

- [x] 4.1 `app/services/auth.py`(로그인, 로그아웃, 내 정보)와 `app/api/auth.py`를 작성한다. `tests/library/test_auth_api.py`에 [library/staff-auth] 시나리오를 작성해 통과시킨다
  - 로그인과 토큰: 정상, 틀린 비밀번호와 없는 아이디, 사용 중지, 내 정보
  - 토큰 검증과 로그아웃: 토큰 없음, 만료, 로그아웃 후, 사용 중지 후 기존 토큰
- [x] 4.2 `app/services/library.py`와 `app/api/library.py`(`GET`·`PATCH /library`)를 작성한다. `tests/library/test_library_api.py`에 [library/libraries] 기관 정보와 운영 방식 시나리오 4개를 작성해 통과시킨다
- [x] 4.3 `app/services/staff.py`와 `app/api/staff.py`(`GET`·`POST /staff`, `PATCH /staff/{id}`)를 작성한다. `tests/library/test_staff_api.py`에 다음을 작성해 통과시킨다
  - [library/staff-auth] 직원 계정 관리 시나리오 4개
  - [library/staff-auth] 비밀번호 변경 후 기존 토큰 401 (변경 시 그 계정 세션 전부 끊기)
  - 비밀번호 원문 미저장
  - 허용되지 않은 역할 (DB 직접 쓰기)
  - 다른 기관 직원 수정 404

## 5. 도서와 사본

- [x] 5.1 `app/services/books.py`와 `app/api/books.py`를 작성한다
  - 기존 도서 CRUD를 옮긴다
  - 바뀌는 것: 내부 id PK와 `/books/{id}` 경로, ISBN·정가 선택 입력(ISBN이 있으면 정규화·중복 검사), `?isbn=` 조회, ISBN 수정 허용(매입 사본이 있으면 비우기 거부)
  - 추가: 분류기호·대상 구분, 관리자만 쓰기, 기관별 소장·대출 가능 권수, `held`·`audience` 필터
  - 사본이 있으면 삭제 거부
- [x] 5.2 `tests/catalog/test_books_api.py`와 `tests/catalog/test_books_schema.py`에 [catalog/books] 시나리오를 모두 작성해 통과시킨다
  - 기존 요구사항: 등록(ISBN 없이, 정가 없이 등록 포함), ISBN, 중복(ISBN 없는 도서 여러 권 포함), 조회, 수정(ISBN 나중에 채우기 포함), 저장 제약
  - 새 요구사항: 기관별 소장 권수, 소장 도서만 거르기, 소장 사본이 있는 도서의 삭제 금지, 어린이/일반 도서 구분
- [x] 5.3 `app/services/holdings.py`와 `app/api/holdings.py`를 작성한다
  - 등록(도서 id, 등록번호, 청구기호), 입수 구분 규칙(매입: 구입가·ISBN 필수, 기증: 기증처), 등록번호 유일성, 상태 전이 제한, 조회 필터(`book_id`, `status`), 수정·삭제
  - 공통 헬퍼 `get_owned`를 이 단계에서 만든다
- [x] 5.4 `tests/catalog/test_holdings_api.py`에 다음을 작성해 통과시킨다
  - [catalog/holdings] 시나리오 전부
  - [library/libraries] 다른 기관의 사본 조회
  - 다른 기관 사본 수정·삭제 404, 키오스크 쓰기 403

## 6. 회원과 대출

- [x] 6.1 `app/services/members.py`와 `app/api/members.py`를 작성한다. `tests/circulation/test_members_api.py`에 다음을 작성해 통과시킨다
  - [circulation/members] 시나리오 전부 (대출 행은 DB 직접 쓰기로 만든다)
  - 삭제 시 반납된 대출 기록의 회원 연결을 같은 트랜잭션에서 끊는다
  - [library/libraries] 기관 데이터 분리: 목록에 다른 기관 데이터 없음, 요청 본문의 library_id 무시, 다른 기관 데이터 수정
  - 키오스크 목록 조회 403
- [x] 6.2 `app/services/loans.py`와 `app/api/loans.py`를 작성한다
  - 대출: 사본 잠금, 운영 방식 확인, 반납 예정일
  - 반납: 등록번호로 미반납 대출 찾기·잠금, 운영 방식 확인 (키오스크·관리자 공용 `POST /loans/return`)
  - 목록(active·overdue·returned, 회원이 삭제된 기록은 회원번호 비움)
  - 부분 UNIQUE 위반 → 409
- [x] 6.3 `tests/circulation/test_loans_api.py`에 다음을 작성해 통과시킨다
  - [circulation/loans] 시나리오 전부 (`clock.today`를 바꿔 끼워 연체를 만든다)
  - [library/staff-auth] 역할별 접근 제한 시나리오 2개 (키오스크 조회 허용, 관리 작업 403)
  - 키오스크 대출·반납 허용

## 7. 시드

- [x] 7.1 `app/seed/{library,catalog,circulation}.py`와 `runner.py`를 design.md 8번대로 다시 작성한다. 전제 조건 확인 로직은 유지한다
- [x] 7.2 `tests/platform/test_seed.py`를 [platform/dev-seed-data] 시나리오에 맞춰 고치고 통과시킨다
  - 시드 데이터 생성 (건수, 운영 방식 2가지, 연체 1건 이상)
  - 도메인 규칙 (ISBN, 정가·구입가, 매입 사본의 구입가와 ISBN, 대출 중 사본 상태, 시드 계정 로그인)
  - 두 번 실행 시 건수 불변
  - 기존 전제 조건 시나리오 4개
- [x] 7.3 개발 DB에서 `uv run python scripts/seed.py`를 두 번 실행해 두 번째에 생성 0건인지 확인한다. 시드 계정으로 서버에 로그인해 Swagger에서 키오스크 계정으로 대출 → 반납(등록번호)을 한 번 해 본다

## 8. 문서와 최종 점검

- [x] 8.1 `README.md`를 새 도메인에 맞춰 고친다
  - 실행 순서, 시드 계정, 이전 스키마에서 넘어올 때 `downgrade base` 안내, 인증 사용법
- [x] 8.2 `CLAUDE.md` 디렉터리 구조를 실제 코드에 맞춘다: `core/`의 security·deps·clock·isbn, `models/`의 library·catalog·circulation
- [x] 8.3 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인한다. 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 점검한다. REMOVED 시나리오는 제외한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- archive 후 처리할 것
  - 요구사항이 모두 제거된 이전 도메인 스펙 폴더 6개가 비어 남으면 지운다.
  - `catalog/books`, `platform/*` 스펙의 Purpose에 남은 "책방"·"매장" 표현을 새 도메인에 맞게 고친다. Purpose는 delta로 바뀌지 않는다.
