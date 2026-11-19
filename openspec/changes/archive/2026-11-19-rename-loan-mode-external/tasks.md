# Tasks

design은 두지 않는다. 새 기술 결정 없이 값 하나와 CHECK 제약 하나를 바꾼다. 사본 출처(`holdings.source`, `HoldingSource.IMPORTED`)와 그 CHECK 제약의 `source = 'imported'`는 어느 태스크에서도 바꾸지 않는다.

## 1. 운영 방식 값

- [x] 1.1 `LoanMode.IMPORTED = "imported"`를 `LoanMode.EXTERNAL = "external"`로 바꾸고, 그 값을 쓰는 곳(대출 서비스, 장서 가져오기 서비스, 도서관 안내 서비스, 검색의 `_loan_mode` 비교와 지역 변수 이름, AI 사서 프롬프트 키, 시드 기관)을 고친다(확인: `grep -rn "LoanMode.IMPORTED"`가 0건, `HoldingSource.IMPORTED`는 그대로)
- [x] 1.2 마이그레이션: `libraries.loan_mode`의 CHECK 제약(이름은 DB에서 확인)을 지우고, `imported` 행을 `external`로 바꾼 뒤, `('external', 'internal')`로 제약을 다시 만든다. downgrade는 거꾸로 한다(확인: 개발 DB를 백업한 뒤 `upgrade head → downgrade -1 → upgrade head`를 `&&`로 이어 실행, 푸른숲 기관이 `external`, `alembic check`에 차이 없음)
- [x] 1.3 테스트에 적힌 운영 방식 값 `"imported"`(conftest의 B 기관, 시드·기관 API·AI 사서 API·장서 가져오기 API 테스트)를 `"external"`로 고치고, 시나리오 제목이 바뀐 테스트 docstring 다섯 곳(AI 사서 둘, 검색 하나, 대출 둘)을 새 제목으로 고친다(확인: 스펙 libraries "자기 기관 조회", loans "외부 대출 기관에서 대출·반납", librarian "외부 대출 기관의 카드"·"운영 방식별 프로필", collection-search "외부 대출 기관", holdings-import "자체 대출 기관의 가져오기", dev-seed-data "빈 DB에 시드 실행"의 테스트 통과)
- [x] 1.4 기관 API 테스트에 `PATCH /library`로 운영 방식을 `imported`로 바꾸면 422이고 값이 그대로인 테스트를 더한다(확인: 스펙 libraries "옛 운영 방식 값" 시나리오의 테스트, docstring에 요구사항과 시나리오 이름)

## 2. 용어

- [x] 2.1 코드 주석·docstring의 '가져오기 기관'을 '외부 대출 기관'으로 고친다(`tests/conftest.py`, `app/seed/guide.py`, `app/library/schemas/guide.py`, `app/library/schemas/catalog.py`)(확인: `app`, `tests`, `evals`에서 `grep -rn "가져오기 기관"`이 0건)
- [x] 2.2 문서의 운영 방식 값과 용어를 고친다: `CLAUDE.md`(설계 원칙 5, 도메인 용어), `README.md`, `docs/design.md`, `docs/glossary.md`, `app/library/README.md`. `docs/reports/`와 archive된 change는 그 시점 기록이라 두지 않고 그대로 둔다(확인: 위 문서에서 `loan_mode`와 함께 쓰인 `imported`와 '가져오기 기관'이 0건, 사본 출처를 말하는 `imported`는 남음)

## 3. 검증

- [x] 3.1 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `openspec validate rename-loan-mode-external`이 모두 통과한다

## Workflow follow-up

- 사람이 확인한 뒤 archive한다. archive 때 `docs/roadmap.md`의 change 상태와 `CLAUDE.md` "현재 단계"를 고친다.
- 시나리오 제목 네 곳(collection-search, loans 둘, librarian)은 change 전에 `openspec/specs/`에서 직접 고쳤다. archive 뒤 다시 할 일은 없다.
