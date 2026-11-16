## 1. 기준 기록

- [x] 1.1 고치기 전 기준을 확인한다: `uv run pytest` 1198 통과·7 건너뜀, `uv run python -m evals.catalog_search` 결과 `evals/catalog_search/data/runs/20261116-035252`(이전 기준 `20261116-033720`과 같음), `uv run python -m evals.recommendation topic --split all --variants current,hybrid-k60` 결과 `evals/recommendation/data/runs/20261116-035334`. 브랜치가 그 뒤로 코드 변경 없이 같으면 다시 돌리지 않고 이 경로를 기준으로 쓴다

## 2. 정렬 규칙과 확인

- [x] 2.1 `app/core/text.py`에 `KOREAN_COLLATION = "ko-x-icu"`와 `korean_order(expr)`를 더하고, `tests/core/test_text.py`에 서명 정렬 순서 시나리오 넷(가나다순, 숫자·한글·영문, 영문 대소문자, 숫자는 글자 순서)을 DB에서 `korean_order`로 줄 세워 확인하는 테스트를 둔다. docstring은 `[platform/text-normalization] 서명 정렬 순서 / <시나리오>`. `uv run pytest tests/core/test_text.py` 통과
- [x] 2.2 `app/core/migrations.py`에 `require_collation(connection, name)`을 두고, 그것을 부르는 확인 마이그레이션(스키마 변화 없음, downgrade 없음)을 만든다. `tests/platform/test_database_schema.py`에 있는 이름은 통과하고 없는 이름은 이름을 담은 오류가 나는 테스트, 기존 테이블 수 테스트가 그대로 통과하는지를 확인한다. docstring은 `[platform/database-schema] 한국어 정렬 규칙 확인 / <시나리오>`. `uv run pytest tests/platform/test_database_schema.py` 통과
- [x] 2.3 개발 DB를 `/home/pollux/chaekbang-backups/`에 `pg_dump`로 백업하고 경로를 알린 뒤 `&&`로 이어 `uv run alembic upgrade head`를 적용한다. `uv run alembic current`가 새 head인지 확인

## 3. 정렬하는 곳에 적용

- [x] 3.1 `lookup.py`의 `find_books` 2곳, `suggest_books` 1곳, `found_in_text` 2곳의 서명 정렬 키를 `korean_order`로 감싼다. `tests/library/test_book_lookup.py`에 `[catalog/book-lookup] 찾기 결과 순서 / 같은 방식 안에서는 가나다순`, `같은 방식 안에서 숫자·한글·영문`, `[catalog/book-lookup] 자동완성 / 같은 단계 안에서는 가나다순` 테스트를 더한다. `uv run pytest tests/library/test_book_lookup.py tests/library/test_chat_lookup.py` 통과
- [x] 3.2 `search.py`의 `ranked_query` 서명 정렬 키를 감싼다. `tests/library/test_collection_search.py`에 `[catalog/collection-search] 결과 순서와 개수 / 같은 점수는 가나다순`, `같은 점수에 숫자·한글·영문`, `[catalog/collection-search] 키워드 없는 둘러보기 / 둘러보기는 가나다순` 테스트를 더한다. `uv run pytest tests/library/test_collection_search.py tests/library/test_topic_recommendation.py` 통과
- [x] 3.3 `library_books.py`의 `list_library_books` 정렬 키를 감싼다. `tests/catalog/test_library_books_api.py`에 `[catalog/library-books] 기관 도서 단건과 목록 조회 / 목록은 가나다순`, `목록에 숫자·한글·영문`, `목록은 표시 서명 기준` 테스트를 더한다. `uv run pytest tests/catalog/test_library_books_api.py` 통과
- [x] 3.4 `authors.py`의 `same_author_books`가 SQL에서 `korean_order(표시 서명), id` 순으로 받고 Python에서는 겹치는 지은이 수로만 안정 정렬하게 바꾼다. `tests/library/test_same_author.py`에 `[catalog/book-contributors] 같은 저자 조회 / 겹치는 지은이 수가 같으면 가나다순`, `겹치는 지은이 수가 같고 숫자·한글·영문` 테스트를 더한다. `uv run pytest tests/library/test_same_author.py` 통과
- [x] 3.5 `[platform/text-normalization] 서명 정렬 순서 / 비교는 그대로` 테스트를 `tests/library/test_book_lookup.py`에 둔다(서명 `Apple`을 `apple`로 찾으면 서명 전체 일치). `grep -rn "order_by\|sorted(" app/`로 서명을 직접 정렬하는 곳이 8곳 말고 없는지 다시 확인한다

## 4. 전체 확인과 보고

- [x] 4.1 테스트 DB에 `VACUUM ANALYZE`를 한 뒤 `uv run pytest`와 `uv run ruff check . && uv run ruff format --check .`가 통과하는지 확인한다. 기대 순서를 고친 기존 테스트가 있으면 목록과 이유를 적는다
- [x] 4.2 `uv run python -m evals.catalog_search`를 다시 돌려 1.1 기준과 비교한다. 바뀐 수치(word·author 1위 등)마다 전후와 이유(동점으로 앞뒤가 바뀐 질의와 책)를 보고하고 평가는 고치지 않는다
- [x] 4.3 `uv run python -m evals.recommendation topic --split all --variants current,hybrid-k60`을 다시 돌려 1.1 기준과 비교하고 바뀐 수치만 보고한다(고치지 않는다. 임베딩 서버 없이 질의 벡터 캐시로 돈다)
- [x] 4.4 CLAUDE.md의 "현재 단계"에서 `fix-korean-title-order`를 끝난 change로 옮기고, `app/core/` 설명에 정렬 규칙(`korean_order`)을 더한다. 메모리의 한글 서명 정렬 항목을 끝난 것으로 고친다

## Workflow follow-up

- 사용자가 확인한 뒤 `/opsx:archive`로 archive하고 `openspec/specs/`에 반영되었는지 본다.
- PR은 사용자가 요청하면 제목과 본문 텍스트만 쓴다(`Close #<issue 번호>`).
