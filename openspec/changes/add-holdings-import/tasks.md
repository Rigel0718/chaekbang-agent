# Tasks

## 1. 의존성

- [ ] 1.1 `pyproject.toml`에 `openpyxl`, `python-multipart`를 추가한다. `uv sync` 후 `uv run python -c "import openpyxl, multipart"`가 성공하는지 확인한다

## 2. 모델과 마이그레이션

- [ ] 2.1 모델을 design.md 4번대로 바꾼다
  - `HoldingStatus.WITHDRAWN`, `AcquisitionType.UNKNOWN`, `AudienceSource.IMPORT_LABEL`
  - `HoldingImport` 모델, `TENANT_TABLES`에 `holding_imports` 추가
- [ ] 2.2 리비전을 손으로 작성한다: 새 테이블, enum CHECK 3개와 `acquisition_fields` 교체, downgrade 시 행 변환. 개발 DB에서 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다
- [ ] 2.3 `tests/platform/test_database_schema.py`를 8개 테이블로 고치고 통과시킨다. 시드와 기존 테스트가 모두 통과하는지 `uv run pytest`로 확인한다

## 3. 사본·도서 규칙 변경

- [ ] 3.1 `holdings` service와 스키마를 고친다
  - `check_acquisition`에 `unknown`, 직접 등록의 `unknown` 422, 수정 시 규칙
  - `withdrawn` 상태 전이, 목록 기본값에서 제적 제외
  - `missing_fields` 계산, `incomplete` 필터
- [ ] 3.2 `tests/catalog/test_holdings_api.py`에 [catalog/holdings] 입수 구분·사본 상태·사본 조회의 새 시나리오와 빠진 정보 표기 시나리오를 작성해 통과시킨다. 기관 분리(`incomplete` 목록에 다른 기관 사본 없음)도 확인한다
- [ ] 3.3 `app/services/books.py`의 소장 권수와 `held`에서 제적 사본을 뺀다. `tests/catalog/test_books_api.py`에 "제적 사본은 소장이 아님"과 근거 우선순위 시나리오를 작성해 통과시킨다

## 4. 파일 해석 (DB 없음)

- [ ] 4.1 `app/importing/reader.py`를 작성한다. `tests/importing/test_reader.py`에 다음을 작성해 통과시킨다: [catalog/holdings-import] 파일 형식 시나리오 전부, 크기·행 수 상한
- [ ] 4.2 `app/importing/columns.py`를 작성한다. `tests/importing/test_columns.py`에 필수 열과 머리글 인식 시나리오 전부와 열 직접 지정 시나리오를 작성해 통과시킨다. `대출자`가 어떤 표준 열로도 인식되지 않는지 함께 확인한다
- [ ] 4.3 `app/importing/normalize.py`를 작성한다. `tests/importing/test_normalize.py`에 ISBN 정규화 시나리오 전부와 상태·입수 구분 표기 변환 표를 작성해 통과시킨다
- [ ] 4.4 `app/importing/classify.py`를 작성한다. `tests/importing/test_classify.py`에 별치기호·자료실·부가기호 판단 표를 작성해 통과시킨다 (부가기호 첫 자리 4(청소년)는 근거가 아님 포함)
- [ ] 4.5 `app/importing/rows.py`를 작성한다. `tests/importing/test_rows.py`에 행 분류의 건너뜀 시나리오 2개와 입수 구분 인식 표기를 작성해 통과시킨다

## 5. 미리 보기와 적용

- [ ] 5.1 `app/services/holding_imports.py`의 미리 보기와 `app/api/holding_imports.py`의 업로드·조회를 작성한다. `tests/catalog/test_holding_imports_api.py`에 다음을 작성해 통과시킨다
  - 가져오기 대상과 권한 시나리오 2개
  - 미리 보기는 장서를 바꾸지 않음
  - 가져오기 기록 조회 시나리오 2개
- [ ] 5.2 적용을 작성한다 (기관 행 잠금, 현재 DB와 재비교, 도서 찾기·만들기, 사본 반영, `last_synced_at`). `tests/catalog/test_holding_imports_apply.py`에 다음을 작성해 통과시킨다
  - 미리 보기와 적용의 적용·두 번 적용
  - 도서 찾기와 만들기 시나리오 전부
  - 사본 값 반영 시나리오 전부
  - 입수 구분 인식 시나리오 전부
  - 인식하지 못한 열은 저장하지 않음 (`대출자` 이름이 DB 어디에도 없음)
- [ ] 5.3 제적과 대량 제적 확인을 작성한다. 같은 테스트 파일에 시나리오 전부를 작성해 통과시킨다. 다른 기관 사본이 제적되지 않는지 함께 확인한다
- [ ] 5.4 적용에 어린이 분류를 연결한다. 어린이 도서 분류 근거 시나리오 전부를 작성해 통과시킨다

## 6. 평가와 문서

- [ ] 6.1 `evals/holdings_import/`를 작성하고 `uv run python -m evals.holdings_import`가 파일별 지표 표를 출력하는지 확인한다. 어린이 분류 정밀도가 1.0이 아니면 원인을 고친다
- [ ] 6.2 문서를 고친다. README의 가져오기 절차를 따라 시드의 푸른숲 계정으로 가상 파일을 올려 미리 보기 → 적용까지 실제 서버에서 해 본다
  - `README.md`: 가져오기 사용법, 필수 열
  - `CLAUDE.md`: 현재 단계, 입수 구분 용어(`unknown`, 가져온 사본의 예외), 제적
  - `docs/design.md`: 파일에서 빠진 사본의 제적, 데이터 모델의 입수 구분

## 7. 최종 점검

- [ ] 7.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-book-enrichment`를 YES24 API 정보를 받은 뒤 제안한다.
