# Tasks

## 1. 패키지 이동 (동작 변경 없음)

- [x] 1.1 공용 모듈을 `app/core/`로 옮긴다 (`models/base.py`, `services/errors.py`, `services/tenancy.py`, `schemas/common.py`). `uv run pytest`가 489개 통과하는지 확인한다
- [x] 1.2 `app/central/`을 만들고 `Book`, `ExternalSource`, `external/yes24`를 옮긴다. `uv run pytest`가 통과하는지 확인한다
- [x] 1.3 `app/library/`를 만들고 `api`, `services`, `schemas`, `importing`, 기관 모델, `core/deps.py`를 옮긴다. `app/models.py`를 조립 모듈로 만들고 `migrations/env.py`, `scripts/`, `evals/`, 테스트 import를 고친다. `uv run pytest`와 `alembic check`가 통과하는지 확인한다

## 2. 운영자 층 경계

- [x] 2.1 `app/central/enrichment.py`에 `EnrichmentTargets`와 실행을 작성하고 `app/library/enrichment_targets.py`에 구현과 처리 현황을 옮긴다. `scripts/enrich_books.py`를 고친다. 기존 채움 테스트가 그대로 통과하는지 확인한다
- [x] 2.2 `tests/platform/test_package_layers.py`에 [platform/package-layers] 거꾸로 된 import 금지(`core`, `central`만 먼저)와 운영자 코드의 기관 모델 참조 없음 시나리오를 작성해 통과시킨다

## 3. 어린이 기능 분리

- [x] 3.1 `app/features/children/models.py`와 리비전을 작성한다: 테이블 생성, 값 이동, 열 삭제. 개발 DB를 백업한 뒤 `&&`로 이어 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하고 값이 유지되는지 확인한다
- [x] 3.2 `app/library/hooks.py`를 작성하고 등록, ISBN 수정, 가져오기에서 훅을 부르게 한다. `ParsedRow`를 파일 값으로 바꾸고 공통 코드에서 어린이 구분을 뺀다
- [x] 3.3 `app/features/children/`의 규칙, service, 훅, API를 작성하고 `app/main.py`에서 조립한다
- [x] 3.4 어린이 테스트를 `tests/features/children/`로 옮기고 [features/children] 시나리오 전부를 작성해 통과시킨다. 기관 분리 시나리오를 빠뜨리지 않는다
- [x] 3.5 `tests/catalog/test_library_books_api.py`와 가져오기 테스트를 고쳐 [catalog/library-books], [catalog/holdings-import]의 남은 시나리오를 통과시킨다
- [x] 3.6 시드와 `evals/holdings_import/`를 고친다. [platform/dev-seed-data], [platform/database-schema] 시나리오를 통과시키고 `uv run python -m evals.holdings_import`가 지표 표를 출력하는지 확인한다. 가상 파일 수치라 실제 성능으로 쓰지 않는다
- [x] 3.7 [library/staff-auth] 키오스크의 어린이 구분 조회를 통과시킨다

## 4. 경계 검증

- [x] 4.1 `tests/platform/test_package_layers.py`의 의존 방향 표를 `library`까지 넓히고, 기능 없이 등록과 가져오기, 공통 응답에 어린이 값 없음 시나리오를 작성해 통과시킨다
- [x] 4.2 훅 호출을 일부러 빼거나 운영자 연결에서 훅을 부르게 바꿔 테스트가 실패하는지 확인하고 되돌린다

## 5. 문서

- [x] 5.1 문서를 고치고 README 절차대로 명령이 실행되는지 확인한다
  - `CLAUDE.md`: 디렉터리 구조, 설계 원칙 1·2, 현재 단계, change 순서
  - `README.md`: 도메인 표, 어린이 API 경로
  - `docs/design.md`: 세 층 패키지, 어린이 기능의 위치와 API, 데이터 모델 표

## 6. 최종 점검

- [x] 6.1 일회용 DB에서 실제 서버로 확인한다: 시드, 기관 도서 등록, `/children` API, 가져오기. 운영자 스크립트는 공식 서지가 있는 ISBN으로 외부 호출 없이 연결만 확인한다
- [x] 6.2 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `alembic check`가 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다
- [x] 6.3 어린이 구분 저장을 upsert로 바꿔 동시 지정이 500이 되지 않게 한다. 자동 근거는 동시에 들어온 관리자 지정을 덮어쓰지 않는다. `tests/features/children/test_children.py`로 확인한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-librarian-agent`로 넘어간다. 그 전에 저자 구조화를 어디서 할지 정한다.
