# Tasks

## 1. 모델과 마이그레이션

- [ ] 1.1 `app/models/catalog.py`를 design.md 5번대로 바꾼다 (`AudienceSource.EXTERNAL_CATEGORY`, `ExternalSource`, `EnrichmentStatus`, `books` 새 열). `BookRead`에 새 필드를 추가한다
- [ ] 1.2 리비전을 손으로 작성한다: 열 추가, `audience_source` CHECK 교체, downgrade의 행 변환. `set -eo pipefail`로 개발 DB에서 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다
- [ ] 1.3 `uv run pytest`로 기존 테스트와 시드가 모두 통과하는지 확인한다

## 2. 어린이 근거 우선순위

- [ ] 2.1 `app/services/holding_imports.py`의 근거 조건에 `external_category`를 넣는다. `tests/catalog/test_holding_imports_apply.py`에 [catalog/holdings-import] "외부 분류 근거보다 우선" 시나리오를 작성해 통과시킨다
- [ ] 2.2 `tests/catalog/test_books_api.py`에 [catalog/books] 근거 우선순위 시나리오를 작성한다. 근거 enum 값이 저장되는지도 함께 확인한다. 어린이/일반 구분의 기존 시나리오가 그대로 통과하는지 확인한다

## 3. YES24 호출 코드 (DB 없음)

- [ ] 3.1 `app/core/config.py`에 `yes24_api_key: SecretStr | None`, `yes24_base_url`을 추가한다. `.env.example`의 값이 비어 있는지 확인한다
- [ ] 3.2 `app/external/yes24/definitions.py`, `parsing.py`를 작성한다. `tests/external/test_yes24_parsing.py`에 응답 값 정규화 시나리오 전부를 작성해 통과시킨다. 줄인 실제 응답 구조를 픽스처로 쓴다
- [ ] 3.3 `app/external/yes24/classify.py`를 작성한다. `tests/external/test_yes24_classify.py`에 표본에서 본 값 표를 작성해 통과시킨다 (근거: `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` / 근거 아님: `국내도서-청소년`, `국내도서-전집`, `국내도서-중고등학습서-중학교`, 빈 값, 성인물)
- [ ] 3.4 `app/external/yes24/client.py`, `goods.py`를 작성한다. `tests/external/test_yes24_client.py`에 design.md 7번의 오류 구분 표 전부, 호출 속도 제한 시나리오 2개, 키 헤더 전송 시나리오를 `httpx.MockTransport`로 작성해 통과시킨다

## 4. 서지정보 채움

- [ ] 4.1 `app/services/book_enrichment.py`의 실행을 작성한다. `tests/catalog/test_book_enrichment.py`에 다음을 작성해 통과시킨다
  - 실행 권한과 대상 시나리오 전부 (기관 분리, 제적, ISBN 없음)
  - 나눠서 처리 시나리오 전부
  - 빈 필드만 채우기, 추가 서지정보 보관, 저장하지 않는 값 시나리오 전부
  - ISBN 일치 확인, 찾지 못한 도서 시나리오 전부
- [ ] 4.2 외부 분류 판단을 실행에 연결한다. 같은 파일에 외부 분류 판단 시나리오 전부를 작성해 통과시킨다
- [ ] 4.3 중단 처리를 작성한다. 외부 장애 시 중단 시나리오 전부와 키 미설정, 오류에 키 없음 시나리오를 작성해 통과시킨다. 테스트 키 값이 응답과 `caplog`에 없는지 확인한다
- [ ] 4.4 `app/services/books.py`의 ISBN 변경 처리를 고친다. ISBN 변경 시 다시 대기 시나리오를 작성해 통과시킨다. 가져오기와 분리 시나리오는 `tests/catalog/test_holding_imports_apply.py`에 외부 호출 0건으로 확인한다

## 5. API와 현황

- [ ] 5.1 `app/api/book_enrichment.py`, `ServiceUnavailableError` 핸들러, `get_yes24_client` 의존성을 작성하고 `app/main.py`에 연결한다. 라우터에 로직이 없는지 확인한다
- [ ] 5.2 현황 조회를 작성한다. `tests/catalog/test_book_enrichment_api.py`에 처리 현황 조회 시나리오 전부와 출처 표시 시나리오 전부를 작성해 통과시킨다. 다른 기관 도서가 건수에 없는지 확인한다

## 6. 문서

- [ ] 6.1 문서를 고치고 README 절차대로 명령이 실행되는지 확인한다
  - `README.md`: 서지정보 채움 사용법, 키 설정, 호출 한도와 다시 실행
  - `CLAUDE.md`: 디렉터리 구조의 `external/`, 어린이 근거 `external_category`, 외부 데이터 저장 조건
  - `docs/design.md`: 어린이 분류의 외부 근거를 `goodsSortNm`으로, 외부 API 표에 쓰는 기능과 이용 조건

## 7. 최종 점검

- [ ] 7.1 실제 서버에서 확인한다: 개발 DB에 실제 ISBN(`9788986621136`) 도서를 소장 사본과 함께 넣고 관리자로 실행해 소개·표지·출처가 채워지고 근거가 `external_category`인지 본다. 키 값은 출력하지 않는다. 호출은 몇 건으로 제한한다
- [ ] 7.2 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-librarian-agent`로 넘어간다.
- 구매 요청서 change에서 작성 시점의 가격 조회를 다룬다.
- 여러 기관에 실제로 서비스하기 전에 기관 공통 도서의 YES24 데이터 사용을 YES24에 확인한다.
