# Tasks

## 1. 준비

- [x] 1.1 `tests/evals/test_librarian_eval.py`의 추적 테스트가 `openspec/specs/`와 archive되지 않은 change의 delta를 읽게 고친다. 지금 main에서 실패하는 `test_scenarios_cover_eval_requirements`가 통과하는지 확인한다
- [x] 1.2 테스트 DB에서 유사도 방식을 고른다(일회성 비교 스크립트, 저장소에 남기지 않는다). `pg_trgm`이 호환 자모를 글자로 보는지 먼저 확인하고(아니면 design 7의 라틴 매핑), design 3의 후보 셋을 표본의 모음·받침·자판 오타 질의와 관계없는 질의로 비교한다. 오타 5위 안 적중률과 관계없는 질의의 빈 결과 비율을 표로 알리고, 고른 방식과 이유를 design에 적은 뒤 진행한다

## 2. 자모 규칙과 마이그레이션

- [x] 2.1 `app/core/text.py`에 `jamo`, `jamo_spaced`, `jamo_sql`을 작성하고 `tests/core/`에서 겹받침, 이중 모음, 조합 중 자모, 영문·숫자 규칙을 테스트한다
- [x] 2.2 1.2에서 고른 유사도 확장, `ko_jamo` 함수, `chat_messages.note` 열 리비전을 작성하고 `ChatMessage` 모델에 `note`를 더한다. 개발 DB를 백업한 뒤 `&&`로 이어 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다. [platform/database-schema] 시나리오 전부(자모 분해 규칙 일치 포함)를 통과시킨다

## 3. 찾기와 검색 API

- [x] 3.1 `recommendation/lookup.py`에 `find_books`, `get_findable`을 작성하고 `tests/library/test_book_lookup.py`로 [catalog/book-lookup] 찾을 수 있는 책, 서명·저자 찾기, 찾기 결과 순서 시나리오 전부를 통과시킨다. 기관 분리 시나리오를 빠뜨리지 않는다
- [x] 3.2 `suggest_books`를 작성하고 [catalog/book-lookup] 자동완성 시나리오 전부를 통과시킨다
- [x] 3.3 `schemas/catalog.py`(`BookSummary`, `Suggestion`), 카드 만들기를 요약과 이유로 나누고, `api/catalog.py`와 `app/main.py` 등록을 작성한다. [catalog/book-lookup] 검색 API, 검색 기록을 남기지 않음 시나리오를 통과시키고 기존 카드 테스트가 그대로 통과하는지 확인한다
- [x] 3.4 가짜 기관 도서 5,000권으로 찾기, 자동완성, 문장 속 서명이 각각 200ms 안에 끝나는지 확인하는 테스트를 둔다. 넘으면 인덱스를 검토하기 전에 알린다. (구현 중 추가) 질의마다 계산하면 넘어서, 찾기 키를 `books`·`library_books`의 생성 열로 저장하도록 리비전·모델·`lookup.py`를 고치고 [platform/database-schema] 찾기 키 열의 자동 계산 시나리오를 통과시킨다

## 4. AI 사서 tool

- [x] 4.1 `tools.py`에 `find_book`을 작성하고 프로필과 프롬프트에 넣는다. 가짜 LLM으로 [agent/librarian] 조회 tool 시나리오 전부를 통과시키고, 어린이 기능 없는 프로필에서도 들어가는지 확인한다

## 5. 대화와 잇기

- [x] 5.1 `run()`의 `history`가 `Instruction`을 받게 넓히고 `tests/agent/`에 안내 메시지가 `user_texts`에 들어가지 않는 테스트를 둔다. `MessageRequest`에 고른 책을 더하고, `prepare_turn`·`stream_turn`에 고른 책만 보낸 턴과 `note` 저장, 대화 기록의 안내 메시지 변환을 넣는다. [agent/librarian] 대화 요청 시나리오 전부와 [agent/chat-sessions] 저장 내용, 고른 책 턴의 상한 시나리오 전부를 통과시킨다
- [x] 5.2 `found_in_text`, 문장 턴의 찾은 책 카드, 답 카드와 노출 기록에서 찾은 책 빼기, 프롬프트를 작성하고 [agent/librarian] 찾은 책 카드 시나리오 전부(서명 속 어린이 낱말, 찾은 책을 다시 추천 포함)를 통과시킨다. 기존 [agent/librarian]·[agent/chat-sessions]·[agent/recommendation-events] 테스트가 그대로 통과하는지 확인한다

## 6. 검색 평가

- [x] 6.1 `evals/catalog_search/`에 질의 만들기, 지표(1위·5위 안·MRR·찾음 비율·오탐 비율), 기준선 비교, 실행 진입점을 작성한다. 질의 만들기와 지표는 표본 없는 작은 자료로 테스트하고, 결과 폴더를 `.gitignore`에 넣는다
- [x] 6.2 표본으로 `uv run python -m evals.catalog_search`를 돌려(LLM·YES24 호출 없음) 질의 종류별 표를 기준선과 함께 알린다. 유사도 문턱을 표로 정해 코드와 README에 적고, design 8의 목표에 못 미치는 종류가 있으면 원인과 함께 알리고 멈춘다

## 7. 문서

- [x] 7.1 CLAUDE.md(현재 단계, MVP 순서 8 `add-catalog-search` → 9 `add-library-guide` → 10 `add-related-books` → 11 `add-recommendation-evals`와 그 뒤 번호, LLM의 역할(찾기는 코드, 대화와 도서관 안내는 LLM), 디렉터리 구조), `docs/design.md`(이용자 화면에 검색과 추천의 구분, 자동완성이 달린 대화 입력, 일정 표, v1의 "임베딩은 add-recommendation-evals" 문구), `README.md`(검색 API, 검색 평가), `app/library/README.md`를 고친다. 적은 명령이 실행되는지 확인한다

## 8. 최종 점검

- [x] 8.1 일회용 DB에서 실제 서버로 확인한다: 키오스크 토큰으로 `GET /catalog/suggest?q=데미ㅇ`, `GET /catalog/search?q=데미얀`, 고른 책만 보낸 대화, `데미안 있어요?` 대화의 `found` 사건을 본다. LLM이 필요한 마지막 확인은 승인받고, 쓴 모델과 토큰 수를 알린다
- [x] 8.2 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `alembic check`가 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 테스트 docstring에 연결돼 있는지 스크립트로 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-library-guide`를 제안한다. design 10의 첫 항목이 출발점이다. 그 뒤 `add-related-books`는 design 10의 둘째 항목에서 출발한다.
