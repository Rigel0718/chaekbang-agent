# Tasks

## 1. 모델과 마이그레이션

- [x] 1.1 `app/models/catalog.py`를 design.md 8번대로 바꾼다 (`AudienceSource.EXTERNAL_CATEGORY`, `ExternalSource`, `EnrichmentStatus`, `books`와 `library_books` 새 열). `LibraryBookRead`에 새 필드를 추가한다
- [x] 1.2 리비전을 손으로 작성한다: 열 추가, CHECK 교체, upgrade와 downgrade의 행 변환. 개발 DB를 백업한 뒤 `&&`로 이어 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다
- [x] 1.3 `app/seed/catalog.py`에서 연결된 기관 도서를 `enriched`로 만든다. `uv run pytest`로 기존 테스트와 시드가 모두 통과하는지 확인한다

## 2. 연결과 어린이 근거

- [x] 2.1 `app/services/audience.py`를 작성한다. `tests/catalog/test_audience.py`에 [catalog/library-books] 외부 분류 근거의 값 표를 작성해 통과시킨다 (근거: `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` / 근거 아님: `국내도서-청소년`, `국내도서-전집`, `국내도서-중고등학습서-중학교`, `국내도서-소설/시/희곡`, 빈 값)
- [x] 2.2 `app/services/library_books.py`에 `apply_official`을 작성하고 등록, ISBN 수정에서 쓰게 한다. 저장 전 `None` 근거를 `default`로 다룬다. `tests/catalog/test_library_books_api.py`에 [catalog/library-books] 공식 서지 연결, 어린이/일반 도서 구분, 외부 분류 근거의 새 시나리오를 작성해 통과시킨다. 기존 시나리오가 그대로 통과하는지 확인한다
- [x] 2.3 `app/importing/classify.py`에서 부가기호 6을 넣고 별치기호 `어`, `c`를 뺀다. `tests/importing/test_classify.py`와 `tests/catalog/test_holding_imports_apply.py`에 [catalog/holdings-import] 초등 학습참고서 부가기호, 중·고등 부가기호, 출처가 없는 별치기호 시나리오를 작성해 통과시킨다
- [x] 2.4 `app/services/holding_imports.py`의 `_new_book`이 `apply_official`을 쓰게 하고 근거 조건에 `external_category`를 넣는다. `tests/catalog/test_holding_imports_apply.py`에 [catalog/holdings-import] "외부 분류 근거보다 우선", [catalog/library-books] "새로 가져오는 도서", [catalog/book-enrichment] 가져오기와 분리 시나리오를 외부 호출 0건으로 작성해 통과시킨다

## 3. YES24 호출 코드 (DB 없음)

- [x] 3.1 `app/core/config.py`에 `yes24_api_key: SecretStr | None`, `yes24_base_url`을 추가한다. `.env.example`의 값이 비어 있는지 확인한다
- [x] 3.2 `app/external/yes24/definitions.py`, `parsing.py`를 작성한다. `tests/external/test_yes24_parsing.py`에 응답 값 정규화 시나리오 전부를 작성해 통과시킨다. 줄인 실제 응답 구조를 픽스처로 쓴다
- [x] 3.3 `app/external/yes24/client.py`, `goods.py`를 작성한다. `tests/external/test_yes24_client.py`에 design.md 10번의 오류 구분 표 전부, 호출 속도 제한 시나리오, 키 헤더 전송 시나리오를 `httpx.MockTransport`로 작성해 통과시킨다

## 4. 채움 실행

- [x] 4.1 `app/services/book_enrichment.py`의 대상 선택과 실행을 작성한다. `tests/catalog/test_book_enrichment.py`에 다음을 작성해 통과시킨다
  - 채움 실행과 대상 시나리오 전부 (같은 ISBN 한 번, 제적, ISBN 없음)
  - 나눠서 처리의 limit, 이어서 처리 시나리오
  - 이미 있는 공식 서지 사용 시나리오
  - 공식 서지 만들기, 저장하지 않는 값 시나리오 전부
  - ISBN 일치 확인, 찾지 못한 도서 시나리오 전부
- [x] 4.2 운영자 실행이 `connect_official`만 쓰게 고치고, [catalog/library-books] "운영자 실행은 바꾸지 않음" 시나리오를 작성해 통과시킨다
- [x] 4.3 외부 장애 시 중단 시나리오 전부를 같은 파일에 작성해 통과시킨다. 이미 처리한 결과가 남고 남은 ISBN이 대기인지 확인한다

## 5. 스크립트와 현황

- [x] 5.1 `scripts/enrich_books.py`를 작성한다. `tests/catalog/test_enrich_script.py`에 잘못된 limit, 키 미설정, 오류에 키 없음 시나리오와 design.md 11번의 종료 코드를 작성해 통과시킨다. 테스트 키 값이 출력과 `caplog`에 없는지 확인한다
- [x] 5.2 `app/api/book_enrichment.py`의 현황 조회를 작성하고 `app/main.py`에 연결한다. 라우터에 로직이 없는지 확인한다. `tests/catalog/test_book_enrichment_api.py`에 처리 현황 조회 시나리오 전부, 출처 표시 시나리오 전부, "기관 API 경로 없음" 시나리오를 작성해 통과시킨다

- [x] 5.3 `refresh_audience`와 `POST /library-books/audience/refresh`를 작성한다. `tests/catalog/test_library_books_api.py`에 [catalog/library-books] 어린이 구분 갱신 시나리오 전부를 작성해 통과시킨다. 다른 기관의 값이 바뀌지 않는지 확인한다

## 6. 문서

- [x] 6.1 문서를 고치고 README 절차대로 명령이 실행되는지 확인한다
  - `README.md`: 서지정보 채움 사용법(운영자 실행), 키 설정, 호출 한도와 다시 실행, `GET /book-enrichment`
  - `CLAUDE.md`: 디렉터리 구조의 `external/`, 운영자 층과 기관 층 구분, 어린이 도서 정의, 근거 `external_category`, 자주 쓰는 명령
  - `docs/design.md`: 어린이 구분은 기관 층의 기능임을 명시, 어린이 도서 정의, 외부 근거 `goodsSortNm`, 부가기호 6·7, 외부 API 표에 쓰는 기능과 이용 조건, 운영자 실행
  - [catalog/books] 공식 서지 쓰기 제한의 기존 테스트가 통과하는지 확인한다

## 7. 최종 점검

- [x] 7.1 일회용 DB에서 실제로 확인한다: 실제 ISBN(`9788986621136`) 기관 도서와 사본을 넣고 스크립트를 실행해 소개·표지·출처가 채워지고 어린이 구분은 그대로인지 본 뒤, 기관의 갱신으로 근거가 `external_category`가 되는지 본다. 키 값은 출력하지 않고, 호출은 몇 건으로 제한한다
- [x] 7.2 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다. `app/external/`, `app/services/book_enrichment.py`, `scripts/enrich_books.py`, `Book` 모델에 어린이 구분 코드(`audience`, `children`)가 없는지 확인한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-librarian-agent`로 넘어간다. 그 전에 저자 구조화(이름·역할 분리, 저자 검색)를 어디서 할지 정한다.
- 구매 요청서 change에서 작성 시점의 가격 조회를 다룬다.
- 여러 기관에 실제로 서비스하기 전에 공식 서지의 YES24 데이터 사용을 YES24에 확인하고, 어느 기관도 소장하지 않은 공식 서지의 정리 기준을 정한다.
