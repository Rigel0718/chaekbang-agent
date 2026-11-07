# Tasks

각 그룹은 자기 테스트 파일을 통과시킨다. 전체 `uv run pytest`는 그룹 5 뒤에 통과한다.

## 1. 모델과 마이그레이션

- [x] 1.1 `app/models/catalog.py`를 design.md 2번대로 바꾼다 (`LibraryBook`, 표시 값 속성, `Holding.library_book_id`, `Book` 제약). `app/models/__init__.py`의 `TENANT_TABLES`에 `library_books`를 추가한다
- [x] 1.2 리비전을 손으로 작성한다: design.md의 Migration Plan대로 upgrade와 downgrade의 행 변환. 시드가 있는 개발 DB에서 `set -eo pipefail`로 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하고, 사본 수가 그대로인지 확인한다
- [x] 1.3 `tests/helpers.py`에 `add_library_book`을 추가하고 `add_holding`을 고친다. `tests/platform/test_database_schema.py`에 [platform/database-schema] 9개 테이블과 "다른 기관 도서로 사본 직접 저장" 시나리오를 작성해 통과시킨다

## 2. 기관 도서

- [x] 2.1 `app/schemas/catalog.py`에 기관 도서 스키마를 만들고 `app/services/library_books.py`와 `app/api/library_books.py`를 작성한다 (등록, 조회, 수정, 삭제, `link_official`). `/books` 라우터와 service를 지운다. 모든 함수는 `library_id`를 받는지 확인한다
- [x] 2.2 `tests/catalog/test_books_api.py`를 `tests/catalog/test_library_books_api.py`로 옮기고 [catalog/library-books] 등록, ISBN 형식, ISBN 중복, 조회, 삭제, 어린이 구분 시나리오 전부를 통과시킨다. 다른 기관 도서 조회·수정·삭제 404와 기관별 구분을 함께 확인한다
- [x] 2.3 같은 파일에 공식 서지 연결, 표시 값, 부분 수정 시나리오 전부를 작성해 통과시킨다
- [x] 2.4 `tests/catalog/test_books_schema.py`를 공식 서지와 기관 도서의 저장 제약으로 나눠 [catalog/books] 도서 저장 제약, [catalog/library-books] 기관 도서 저장 제약 시나리오 전부를 통과시킨다. [catalog/books] 공식 서지 쓰기 제한 시나리오도 작성한다

## 3. 사본과 대출

- [x] 3.1 `app/services/holdings.py`, `app/api/holdings.py`, 사본 스키마를 고친다 (`library_book_id`, 기관 범위 확인, 표시 값, `missing_fields`). `tests/catalog/test_holdings_api.py`의 [catalog/holdings] 사본 등록, 사본 조회, 빠진 정보 표기 시나리오를 고쳐 통과시킨다. "다른 기관의 도서" 시나리오를 작성한다
- [x] 3.2 대출 응답을 고친다 (`library_book_id`, 표시 서명). `tests/circulation/test_loans_api.py`가 통과하는지 확인한다
- [x] 3.3 [library/staff-auth], [library/libraries] 시나리오의 경로를 고치고 `tests/library/`가 통과하는지 확인한다

## 4. 가져오기

- [x] 4.1 `app/services/holding_imports.py`를 design.md 6번대로 고친다. `tests/catalog/test_holding_imports_apply.py`에 [catalog/holdings-import] 도서 찾기와 만들기 시나리오 전부와 "다른 기관에 영향 없음"을 작성해 통과시킨다
- [x] 4.2 `tests/catalog/test_holding_imports_api.py`의 미리 보기 시나리오를 고쳐 통과시킨다. `uv run python -m evals.holdings_import`가 파일별 지표 표를 출력하는지 확인한다. 가상 파일의 수치이므로 실제 성능으로 쓰지 않는다

## 5. 시드

- [x] 5.1 `app/seed/catalog.py`를 design.md 7번대로 고친다. `tests/platform/test_seed.py`의 [platform/dev-seed-data] 시나리오를 고쳐 통과시킨다. 같은 ISBN을 두 기관이 가진 경우가 있는지 확인한다
- [x] 5.2 `uv run pytest`가 전체 통과하는지 확인한다

## 6. 문서

- [x] 6.1 문서를 고친다. README 절차대로 시드 계정으로 `/library-books`, 사본 등록, 가져오기를 실제 서버에서 해 본다
  - `README.md`: 도메인 표, API 경로, 현재 단계
  - `CLAUDE.md`: 현재 단계, change 순서에 이번 change 추가, 디렉터리 구조, 설계 원칙 2, 용어(공식 서지, 기관 도서)
  - `docs/design.md`: 세 층 구조, 데이터 모델 표, 어린이 분류 위치, 개발 단계 표

## 7. 최종 점검

- [x] 7.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다. `app/`에 기관 범위 없이 `books`를 쓰는 코드가 시드 외에 없는지 확인한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- archive 때 `catalog/books` main 스펙의 Purpose를 공식 서지 기준으로 직접 고친다.
- `add-book-enrichment`를 이 구조에 맞춰 다시 쓴다 (design.md "다음 change에 주는 영향").
