# Tasks

## 1. 후보 검색

- [x] 1.1 `app/library/recommendation/search.py`에 추천 가능 조건과 키워드 검색을 작성하고 `tests/library/test_collection_search.py`로 [catalog/collection-search] 시나리오 전부를 통과시킨다. 기관 분리 시나리오를 빠뜨리지 않는다

## 2. 저장소

- [x] 2.1 `app/library/models/chat.py`와 리비전을 작성하고 `app/models.py`의 `TENANT_TABLES`에 넣는다. 개발 DB를 백업한 뒤 `&&`로 이어 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다
- [x] 2.2 `tests/platform/test_database_schema.py`를 15개 테이블로 고치고 [platform/database-schema] 시나리오 전부를 통과시킨다

## 3. AI 사서 프로필

- [x] 3.0 공통 실행기 수정: tool이 DB를 읽은 뒤 도메인 오류를 내면 rollback이 실행 객체를 만료시켜 단계 기록이 실패한다. `add_step`이 실행 id를 값으로 받게 하고 `tests/agent/test_runner.py`에 회귀 테스트를 둔다 (구현 중 추가)
- [x] 3.1 `app/library/tools.py`, `app/library/librarian.py`를 작성한다. 답 구조, 프롬프트, 운영 방식별 프로필, 정리 규칙을 두고 가짜 LLM으로 [agent/librarian] 조회 tool, 최종 답, 쓰기 tool 없음 시나리오를 통과시킨다
- [x] 3.2 `recommendation/checks.py`를 작성하고 [agent/librarian] 소장 검사 시나리오를 통과시킨다
- [x] 3.3 `recommendation/cards.py`를 작성하고 [agent/librarian] 추천 카드와 운영 방식별 안내 시나리오를 통과시킨다

## 4. 어린이 기능

- [x] 4.1 `rules.py`에 어린이 요청 판단을 추가하고 [features/children] 어린이 요청 판단, 대화 안에서 유지 시나리오를 통과시킨다
- [x] 4.2 `children/tools.py`, `children/checks.py`를 작성하고 [features/children] 어린이 도서 검색 tool, 어린이 최종 검사 시나리오를 평가 시나리오만 빼고 통과시킨다
- [x] 4.3 `app/main.py`에서 프로필을 조립하고 [platform/package-layers] 기관 개별 기능 없는 AI 사서 시나리오를 통과시킨다

## 5. 대화

- [x] 5.1 `app/library/privacy.py`를 작성하고 [agent/chat-sessions] 개인정보 가리기 시나리오를 통과시킨다
- [x] 5.2 `services/chat.py`, `api/librarian.py`, 설정, `.env.example`, `LimitExceededError`를 작성하고 [agent/librarian] 대화 요청, 진행 사건의 내용과 [agent/chat-sessions]의 대화 이어 가기, 세션의 기관 범위, 세션 만료, 직접 초기화, 저장 내용, 입력 상한, 턴 상한, 일일 실행 상한, 동시 요청 금지를 통과시킨다
- [x] 5.3 삭제 작업을 `lifespan`에 잇고 [agent/chat-sessions] 끝난 세션의 삭제를 통과시킨다
- [x] 5.4 [library/staff-auth] 키오스크의 AI 사서 대화를 통과시킨다
- [x] 5.5 `recommendation/events.py`를 작성하고 [agent/recommendation-events] 시나리오 전부를 통과시킨다. 기존 기관 도서 삭제 테스트가 그대로 통과하는지 확인한다

## 6. 평가

- [x] 6.0 YES24 상품 검색 함수와 `evals/librarian/fetch_sample.py`를 작성해 표본 약 100권을 받는다. `.gitignore`로 저장소에서 빼고, 함수는 테스트로 확인한다
- [x] 6.1 `evals/librarian/`의 표본 적재, 시나리오, 규칙 검사, 실행 진입점을 작성한다. 규칙 검사는 가짜 LLM 응답으로 테스트하고, 시나리오에 이번 change의 평가 요구사항이 모두 적혀 있는지 `tests/`에서 확인한다
- [x] 6.2 `tests/samples/`에 표본 테스트를 작성한다. `sample` 표시를 달고 표본 파일이 없으면 건너뛴다. 실제 서지로 검색, 어린이 분류, 카드, 가짜 LLM 대화 흐름을 확인하고, `LIBRARIAN_SAMPLE_FILE`에 없는 경로를 주어 건너뛰는지도 확인한다 (저장소에 없는 표본을 옮기다 잃지 않게 파일을 옮기지 않는다)
- [x] 6.3 사람이 승인하면 `uv run python -m evals.librarian`을 실제 LLM으로 돌려 규칙 검사 표를 알린다. 진행을 볼 수 있게 시나리오마다 결과를 `evals/librarian/data/runs/<시각>-<모델>/NN-<id>.json`에 저장하고 `summary.md`를 쓴다 (사람 요청으로 추가). 모델, 토큰 수, 위반 건수를 함께 쓴다. 기관과 사본 상태가 가상이라 실제 서비스 성능으로 말하지 않는다. 위반이 있으면 원인을 알리고 멈춘다

## 7. 문서

- [x] 7.1 `app/library/README.md`, `app/features/README.md`, `README.md`, `.env.example`을 고치고 적은 명령이 실행되는지 확인한다. `docs/design.md`와 스펙이 달라진 곳이 있으면 고친다

## 8. 최종 점검

- [x] 8.1 일회용 DB에서 실제 서버로 확인한다: 키오스크 토큰으로 `공룡 책 추천해줘`를 보내 SSE 사건과 카드, 노출 행을 본다. 두 번째 턴, 세션 삭제, 어린이 요청도 본다. 여러 tool 호출에서 추론 항목 재전송과 `maxLength` 스키마를 확인한다. 실제 호출은 승인받고, 쓴 모델과 토큰 수를 알린다
- [x] 8.2 어린이 검사 호출과 개인정보 가리기를 일부러 빼서 테스트가 실패하는지 확인하고 되돌린다
- [x] 8.3 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `alembic check`가 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 테스트 docstring이나 평가 시나리오에 연결돼 있는지 스크립트로 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-recommendation-evals`로 넘어간다.

## `add-recommendation-evals`로 넘기는 것 (2026-11-10 결정)

- **어린이 지표를 둘로 나눈다.** ① 책 분류(장서가 들어올 때 정해 저장하는 값)와 ② 요청 판단(대화마다 코드가 정하는 값)은 다른 문제다. 지금의 `children_general` 검사는 위반의 원인이 ①인지 ②인지 구분하지 못한다.
  - ①은 장서 쪽에서 잰다: 어린이로 분류한 책의 정밀도와 놓친 비율. 파일 근거는 `evals/holdings_import`가 이미 잰다. 분류 원문 근거는 출처를 바꿀 때 같은 방식으로 잰다.
  - ②는 대화 시나리오로 잰다: 어린이 요청을 맞게 판단한 비율, 어른 요청을 어린이로 좁힌 오판 비율. 책 분류는 정답으로 고정해 ①의 오차가 섞이지 않게 한다.
- **6.3 평가의 기대 불일치 2건** (`evals/librarian/data/runs/20261110-160534-gpt-6-luna/`). 둘 다 LLM이 `search_children_books`를 불러 ②가 켜진 경우다.
  - `no-description`: 물어본 책이 어린이 도서였다. 답은 맞았다. 시나리오 기대(어린이 요청 아님)를 고친다.
  - `parenting`(`아이 훈육 방법 책`): 문장 규칙은 맞게 판단했지만 tool 사용으로 어린이로 좁혀졌다. 오판 비율 지표로 남긴다. tool 사용으로 판단을 켜는 규칙을 바꾸려면 스펙 변경이다.
- **출처 교체는 ①만 바꾼다.** YES24는 MVP용이고, 승인이 나면 국립중앙도서관·도서관 정보나루로 바꾼다. 그때 `app/features/children/rules.py`의 `CHILDREN_CATEGORIES`를 새 분류 값에 맞추고 평가 표본을 새 출처로 다시 받는다. ②와 AI 사서 코드는 바뀌지 않는다.
