# Proposal

## Why

공통 실행기는 준비됐지만 이용자가 쓸 수 있는 에이전트가 없다. 이 프로젝트의 핵심 성과 지표는 추천 품질이고, 측정하려면 먼저 소장 도서로 답하는 AI 사서가 있어야 한다. 어린이 요청과 개인정보처럼 틀리면 안 되는 규칙은 공용 PC에 올리기 전에 코드로 지키게 한다.

## What Changes

- **후보 검색**: 소장 도서를 키워드로 찾는다. 대출 가능이나 대출 중 사본이 있는 책만 나온다.
- **AI 사서 프로필**: 조회 tool `search_collection`, `get_book_detail`과 최종 답 `submit_answer`. 운영 방식별로 안내가 다르다.
- **어린이 기능의 확장**: `search_children_books` tool, 어린이 요청 판단 규칙, 어린이 최종 검사. 기능을 빼면 함께 빠진다.
- **소장 최종 검사**: 답의 추천은 이 기관의 추천 가능한 책이어야 한다.
- **대화 API**: `POST /librarian/messages`는 SSE로 진행 상태를 보내고, 검사 뒤에 답과 추천 카드를 보낸다. 카드는 코드가 DB 값으로 만든다.
- **대화 세션**: 무입력 시간이 지나면 서버가 끝내고 메시지를 지운다. 턴 수와 동시 요청을 제한한다.
- **개인정보 가리기**: 전화번호, 이메일, 주민번호, 회원번호를 LLM 호출과 저장 전에 가린다.
- **비용 상한**: 입력 길이, 턴 수, 기관별 일일 실행 수.
- **추천 노출 기록**: 이용자에게 보인 추천을 `recommendation_events`에 남긴다.
- **평가**: `evals/librarian/`에 시나리오와 규칙 검사를 둔다. 서지는 YES24에서 받은 표본 약 100권을 쓴다. 표본은 로컬 JSON이고 저장소에 넣지 않는다. 에이전트 동작 시나리오는 여기서 확인한다.

**범위 밖 (이번 change에서 하지 않음)**

- 대출·반납·희망도서 tool, 운영 방식에 따른 tool 끄기 → `add-librarian-actions`. v1은 없는 책에 희망도서 안내만 한다
- `get_curations`, `get_popular_loans`, `search_external_books`
- 임베딩 검색, LLM 채점, 30~50개 평가 세트 → `add-recommendation-evals`
- 대출 전환율 계산, 화면 → `add-recommendation-evals`, `add-web-ui`
- 시드 데이터 변경. 평가는 자기 가상 서지를 쓴다

## Capabilities

### New Capabilities

- `catalog/collection-search`: 소장 도서 후보 검색과 추천 가능 조건
- `agent/librarian`: AI 사서의 tool, 최종 답, 소장 검사, 카드, 대화 API, 답의 원칙
- `agent/chat-sessions`: 대화 세션, 만료와 삭제, 개인정보 가리기, 사용 상한
- `agent/recommendation-events`: 추천 노출 기록

### Modified Capabilities

- `features/children`: 어린이 도서 검색 tool, 어린이 요청 판단, 어린이 최종 검사를 추가
- `library/staff-auth`: 키오스크가 AI 사서와 대화할 수 있음
- `platform/database-schema`: 테이블 15개, 대화와 노출 기록의 기관 간 참조 금지
- `platform/package-layers`: 어린이 기능 없이 AI 사서가 동작

## Impact

- **코드**: `app/library/recommendation/`, `app/library/tools.py`, `app/library/librarian.py`, `app/library/services/chat.py`, `app/library/privacy.py`, `app/library/api/librarian.py`, `app/library/models/chat.py`, `app/library/schemas/librarian.py`, `app/features/children/{tools,checks,rules}.py`, `app/core/errors.py`, `app/main.py`, `app/central/external/yes24/`(상품 검색), `evals/librarian/`, 테스트
- **API**: `POST /librarian/messages`, `DELETE /librarian/sessions/{id}` 추가. 기존 API는 바뀌지 않는다
- **DB**: `chat_sessions`, `chat_messages`, `recommendation_events` 추가
- **설정**: `LIBRARIAN_SESSION_IDLE_MINUTES`, `LIBRARIAN_MAX_TURNS`, `LIBRARIAN_DAILY_RUN_LIMIT`
- **외부 호출**: 이용자 문장과 도서 소개가 LLM 제공자에게 간다. 평가와 최종 점검은 실제 호출 비용이 든다. 표본을 받을 때 YES24를 10회 호출한다
