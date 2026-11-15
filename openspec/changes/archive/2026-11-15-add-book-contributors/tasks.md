## 0. 시작 전

- [ ] 0.1 issue 번호를 받는다(제안 승인 뒤 design을 요약한 issue 제목·본문을 텍스트로 준다)
- [x] 0.2 `main`에서 브랜치 `add-book-contributors`를 만든다
- [x] 0.3 기준 수치를 남긴다: `uv run pytest` 통과 수, `uv run python -m evals.catalog_search` 결과(1위, 5위 안, MRR, 오탐), 표본 87권의 서명·저자 찾기 키(변경 뒤 비교용, 스크래치 파일)
  - 2026-11-13: 954 통과, 7 건너뜀, 1 실패(`test_volatile_values_not_stored`. 행 전체 덤프의 시각 문자열에 `9.5`가 섞이면 실패하는 시간 의존 테스트로, 다시 돌리면 통과한다. 범위 밖이라 따로 둔다). 찾기 평가 1위: exact 100%, spacing 96.2%, prefix 94.9%, word 87.7%, author 88.6%, vowel 84.0%, final 82.9%, key 81.3%, suggest 87.6%, found 98.7%, unrelated 0%

## 1. 정규화 (`app/core/text.py`)

- [x] 1.1 PostgreSQL `normalize(text, NFC)`와 `translate`를 생성 열 식에 쓸 수 있는지(IMMUTABLE) 테스트 DB에서 확인한다. 안 되면 IMMUTABLE SQL 함수로 감싸는 방법으로 정하고 design 결정 2에 적는다
- [x] 1.2 `clean_spaces`에 NFC, `compact`에 NFC와 전각 → 반각을 더한다. 전각 표 상수를 둔다. `compact_sql`을 같은 규칙으로 고친다
- [x] 1.3 `match_key`(비교용 + 글자·숫자가 아닌 것 제거), `kdc_key`를 더한다. 모듈 설명을 세 단계 기준으로 고쳐 쓴다
- [x] 1.4 테스트(`tests/core/test_text.py`): 저장용(공백, NFD, 표기 유지), 비교용(띄어쓰기·대소문자, 전각, NFD, 호환 자모 유지), 이름 맞춤 키(띄어 쓴 이름, 마침표·대소문자, 시리즈명, 다른 음역, 기호뿐), KDC 키(같은 값, 소수점 없음, 읽을 수 없음)
- [x] 1.5 코드·SQL 일치 테스트의 표본 문자열에 전각, NFD를 더한다(비교용 키, 자모 키, 낱말 시작 키)

## 2. 역할 표와 해석기

- [x] 2.1 `app/core/contributors.py`: `ContributorRole`, 역할 표, `Contributor`, 공통 조각(끝의 역할 읽기, 이름 나누기, `외`·`공`·`등` 처리), `parse_author_text`(이름표·괄호·끝 낱말 꼴), `author_keys`
- [x] 2.2 `app/central/external/yes24/contributors.py`: `parse_yes24_author`
- [x] 2.3 테스트(`tests/core/test_contributors.py`): 같은 역할의 여러 표기, 역할 표기 없음, 글과 그림을 함께, 그 밖의 역할, 표에 없는 표기, 이름표 꼴, 괄호 꼴, 이름만, 읽을 수 없는 꼴
- [x] 2.4 테스트(`tests/external/test_yes24_contributors.py`): 글·그림·역, 원저와 감수, 외·등저·공역, 괄호가 있는 이름, design Context의 꼴마다 대표 표기
- [x] 2.5 표본 전체 테스트(`tests/samples/`, 표본이 없으면 건너뜀): 87권 모두 기여자 1명 이상, 역할 표기가 이름에 붙어 남은 것 없음, 역할별 건수 고정

## 3. 스키마

- [x] 3.1 `app/central/models.py`: `BookContributor`(관계는 두지 않는다, design 결정 6). `app/models.py`의 `SHARED_TABLES`에 `book_contributors`를 더한다
- [x] 3.2 `app/library/models/catalog.py`: `LibraryBook.author_keys`(NOT NULL, 기본값 없음), `@validates("author")`로 저자 키 계산, `@validates("kdc")`로 분류기호 맞춤
- [x] 3.3 마이그레이션 하나: `contributor_role` enum과 `book_contributors`, `library_books.author_keys`(기본값 `'{}'`로 더한 뒤 기본값 제거), `ko_jamo_starts`(와 필요하면 `ko_jamo`) 교체, 찾기 키 생성 열 넷 다시 만들기. downgrade는 이전 정의로 되돌린다
- [x] 3.4 개발 DB를 `pg_dump`로 백업하고 경로를 알린다
- [x] 3.5 `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- [x] 3.6 `tests/platform/test_database_schema.py`: 테이블 21개, 기관 공통 테이블에 `book_contributors`(`library_id` 없음), 기여자 테이블의 저장 계층 규칙(중복 순서, 빈 이름, 없는 공식 서지), 저자 키 없는 기관 도서 직접 저장 거부, 찾기 키 열의 전각·분해형 처리, 공식 서지와 함께 삭제

## 4. 공식 서지 기여자

- [x] 4.1 `app/central/contributors.py`: 출처별 해석기 고르기, `sync_contributors`(다르면 다시 넣고 같으면 쓰지 않음, 바뀌었는지 돌려준다)
- [x] 4.2 `app/central/enrichment.py`의 `_create_official`이 새 공식 서지에 `sync_contributors`를 부른다
- [x] 4.3 테스트(`tests/catalog/test_book_contributors.py`): 채움 실행 뒤 기여자와 순서, 저자 원문 유지, 이름 맞춤 키, 같은 값으로 다시 부르면 쓰지 않음
- [x] 4.4 `tests/platform/test_package_layers.py`가 그대로 통과하는지 확인한다(`central`은 `library`를 모른다)

## 5. 기관 도서 저자 키와 분류기호

- [x] 5.1 등록, 수정, 가져오기 경로를 확인해 validator로 저자 키와 분류기호가 채워지는지 본다. 가져오기의 `_fill_book`(빈 분류기호 채우기)도 같은 규칙을 거친다
- [x] 5.2 테스트(`tests/catalog/test_library_books_api.py`, `test_holding_imports_apply.py`): 저자 키의 등록, 저자 수정, 가져오기, 지은이가 없는 원문, 응답에 없음. 분류기호의 등록, 수정, 가져오기, 읽을 수 없는 값
- [x] 5.3 불변식 테스트: 등록·수정·가져오기 적용 뒤 그 기관의 모든 행에서 `author_keys == author_keys(author)`. `app/`에 저자를 값으로 주는 `update(LibraryBook)`가 없는지 소스 검사
- [x] 5.4 다른 테스트 도우미가 Core로 기관 도서를 만드는 곳이 있으면 저자 키를 넣게 고친다

## 6. 같은 저자 조회

- [x] 6.1 `app/library/recommendation/authors.py`: 책의 지은이 키 식(연결된 책은 기여자, 아니면 저자 키), `same_author_books`
- [x] 6.2 테스트(`tests/library/test_same_author.py`): 연결된 책끼리, 역자만 같은 책, 연결된 책과 연결되지 않은 책, 연결된 책은 공식 값, 원저, 다른 기관의 책, 추천 가능하지 않은 책, 다른 기관의 기준 책

## 7. 시드, 평가 표본 적재, 다시 만들기

- [x] 7.1 `app/seed/catalog.py`: 공식 서지를 넣은 뒤 `sync_contributors`, Core `insert(LibraryBook)`에 저자 키를 넣는다. 두 번 실행해도 기여자가 늘지 않게 한다
- [x] 7.2 `tests/platform/test_seed.py`: 시드 뒤 기여자와 저자 키, 두 번 실행해도 기여자 건수가 같음
- [x] 7.3 `evals/librarian/catalog.py`의 `load_catalog`가 공식 서지에 `sync_contributors`를 부른다
- [x] 7.4 `scripts/rebuild_contributors.py`: 기본 실행과 `--check`, 고친·다른 건수 출력, 종료 코드 0/1, DB 연결·마이그레이션 안내. 기관 도서 쪽 다시 계산 함수는 `app/library/services/`에 둔다
- [x] 7.5 테스트(`tests/catalog/test_rebuild_contributors.py`): 처음 채우기, 다시 실행 0건, 확인 방식, 기관의 값은 그대로, 마이그레이션 전 실행
- [x] 7.6 개발 DB에서 `uv run python scripts/rebuild_contributors.py && uv run python scripts/rebuild_contributors.py --check`를 돌리고 건수를 보고한다

## 8. 찾기 영향 확인

- [x] 8.1 테스트(`tests/library/test_book_lookup.py`): 전각 질의, 전각으로 저장된 서명, 분해형으로 저장된 서명
- [x] 8.2 `uv run python -m evals.catalog_search`를 다시 돌려 0.3의 수치와 비교하고, 표본의 찾기 키가 변경 전후로 같은지 센다. 다르면 멈추고 이유와 전후 수치를 알린다
  - 2026-11-13: 표본 162행(기관 도서 87, 공식 서지 75)의 서명·저자 찾기 키가 변경 전후로 모두 같다. 찾기 평가 표는 종류 11개의 1위·5위 안·MRR·결과에 있음·결과 있음·기준선이 모두 0.3과 같다(결과 폴더 경로만 다름)

## 9. 문서와 마무리

- [x] 9.1 `app/central/README.md`(기여자 표, 출처별 해석기를 더하는 방법), `app/library/README.md`(저자 키, 같은 저자 조회, 읽는 규칙), `app/core/text.py` 설명
- [x] 9.2 CLAUDE.md: 디렉터리 구조(`core/contributors`, `central/contributors`, `scripts/rebuild_contributors.py`), 자주 쓰는 명령, 도메인 용어(기여자, 저자 키), 현재 단계
- [x] 9.3 `docs/design.md`: 데이터 모델에 `book_contributors`와 `library_books`의 저자 키, 못 푸는 것(음역, 동명이인)
- [x] 9.4 스펙 시나리오마다 테스트가 있는지 점검한다(테스트 docstring에 요구사항 이름)
- [x] 9.5 `uv run pytest`와 `uv run ruff check . && uv run ruff format .`가 통과하는지 확인하고, 통과 수를 0.3과 비교해 보고한다
  - 2026-11-13: 1059 통과, 7 건너뜀(임베딩 서버가 꺼져 있어 실제 서버 테스트). 0.3의 955개(시간 의존 실패 1건 포함)에 새 테스트 104개. 린트·포맷 통과
