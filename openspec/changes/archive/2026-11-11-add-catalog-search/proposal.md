# Proposal

## Why

도서관 이용자는 대부분 제목이나 저자를 알고 와서 "이 책 있어요?"를 묻는다. 지금은 이 질문도 AI 사서 대화로만 처리한다. LLM 호출이 두 번 들어 느리고, 기관별 일일 실행 상한을 단순 조회가 먼저 쓴다. 게다가 검색은 공백만 무시하는 부분 문자열 비교라서 `데미얀`처럼 한 글자만 틀려도, 입력 중인 `데미ㅇ`에서도 찾지 못한다.

아는 책을 정확히 찾는 것은 추천보다 먼저 갖춰야 할 기본이다. 그래서 검색과 추천을 나눈다. 검색은 웹 검색처럼 코드가 처리하고, 결과는 대화 안에서 자연스럽게 이어지게 한다. 그 위에 다음 change에서 "찾은 책과 비슷한 책" 추천을 얹는다.

## What Changes

- **서명·저자 찾기**: 그 기관의 소장 도서를 서명과 저자로 찾는다. 공백, 대소문자, 한 글자 안팎의 오타를 허용하고, 정확히 맞는 책을 먼저 둔다. LLM을 쓰지 않는다.
- **자동완성**: 입력 중인 글자(조합 중인 자모 포함)로 서명·저자 후보를 돌려준다. 키오스크 입력창 아래에 띄우는 용도다.
- **검색 API**: `GET /catalog/search`, `GET /catalog/suggest`. 키오스크와 관리자가 쓴다. 결과는 카드와 같은 서지·대출 상태이고 추천 이유는 없다.
- **대화와 잇기**
  - 대화 요청에 **고른 책**(`selected_library_book_id`)을 보낼 수 있다. 자동완성에서 책을 고르면 문장 없이 보낸다. 이때는 LLM을 부르지 않고 그 책의 카드만 보낸다. 다음 턴부터 그 책이 대화 문맥에 남는다.
  - 문장을 보내면 코드가 먼저 서명 찾기를 하고, 거의 정확히 맞는 책이 있으면 **찾은 책 카드**(`found` 사건)를 LLM 답보다 먼저 보낸다. 같은 책을 LLM이 답에 다시 넣으면 답 카드에서 뺀다.
  - 고른 책·찾은 책 표시는 이용자 문장과 따로 저장하고(`chat_messages.note`), LLM에게는 코드의 안내 메시지로 보낸다. 서명의 "아이" 같은 낱말이 어린이 요청 판단을 켜지 않게 하기 위해서다.
  - AI 사서에 같은 찾기를 쓰는 `find_book` tool을 더한다. 주제 검색 `search_collection`은 그대로다.
- **한글 비교 규칙**: 자모 분해 규칙을 `app/core/text.py`에 더하고, 같은 규칙의 SQL 함수를 마이그레이션으로 만든다. 오타 유사도 방식(`pg_trgm` 자모·음절, `fuzzystrmatch` 자모 편집 거리)은 구현 첫 단계에서 표본으로 비교해 고른다. 둘 다 PostgreSQL 기본 확장이라 DB 이미지는 그대로다.
- **검색 평가**: YES24 표본 87권에서 정확히, 공백 없이, 일부만, 오타, 저자로, 조합 중 자모로 입력한 질의를 코드로 만들어 1위 적중률, 5위 안 적중률, MRR을 잰다. 지금 키워드 검색이 기준선이다. LLM을 부르지 않는다.
- **MVP 순서 변경**: 8 `add-catalog-search` → 9 `add-library-guide`(운영 시간·휴관일·대표 연락처·시설 위치·이용 규칙 안내, 반납 예정일 계산) → 10 `add-related-books`(찾은 책의 같은 저자·분류·소개 임베딩 추천, 하이브리드 점수) → 11 `add-recommendation-evals`(대화 추천 평가). LLM은 찾기에서 빠지고, 자연어로 책을 찾는 대화와 도서관 안내를 맡는다. CLAUDE.md와 `docs/design.md`를 고친다.
- **기존 테스트 수정**: archive 이후 평가 추적 테스트가 사라진 change 경로를 읽어 실패한다. 현재 스펙과 진행 중인 change를 읽게 고친다.

**범위 밖 (이번 change에서 하지 않음)**

- 비슷한 책 추천, 임베딩, pgvector, 저자 구조화 → `add-related-books`
- 대화 추천 평가(어린이 판단 지표, 모델 비교, LLM이 오타를 고치는지) → `add-recommendation-evals`
- 화면(자동완성이 달린 채팅 입력창) → `add-web-ui`. 이번에는 API 계약까지만 만든다
- 담은 책 신호, 대출 기록 기반 추천. 담은 책은 고른 책과 같은 통로로 `add-related-books` 이후에 검토하고, 대출 기록 기반 추천은 2단계다
- ISBN·청구기호·초성 검색. 필요해지면 따로 다룬다

## Capabilities

### New Capabilities

- `catalog/book-lookup`: 서명·저자 찾기(오타 허용), 자동완성, 검색 API, 그 기관 범위

### Modified Capabilities

- `agent/librarian`: 대화 요청에 고른 책을 받고, 사건에 찾은 책 카드(`found`)를 더한다. 조회 tool에 `find_book`을 더한다
- `agent/chat-sessions`: 고른 책만 보낸 턴의 저장 내용과 상한 적용
- `platform/database-schema`: `pg_trgm` 확장과 자모 분해 SQL 함수

## Impact

- **코드**: `app/core/text.py`(자모 규칙), `app/library/recommendation/lookup.py`(새로), `app/library/api/catalog.py`(새로), `app/library/schemas/`, `app/library/models/chat.py`(`note`), `app/library/models/catalog.py`·`app/central/models.py`(찾기 키 생성 열), `app/library/services/chat.py`, `app/library/tools.py`, `app/library/librarian.py`(프롬프트), `app/agent/runner.py`(`history`가 안내 메시지를 받음), `app/main.py`, `migrations/`, `evals/catalog_search/`(새로), 테스트
- **API**: `GET /catalog/search`, `GET /catalog/suggest` 추가. `POST /librarian/messages`에 `selected_library_book_id`(선택)를 더하고 `message`는 고른 책이 있을 때 비워도 된다. SSE에 `found` 사건이 더해지고, 고른 책만 보낸 턴의 `done`은 실행 id가 null이다. 기존 클라이언트는 그대로 동작한다
- **DB**: 새 테이블은 없다. 유사도 확장, 자모 분해 함수, `books`·`library_books`의 찾기 키 생성 열(DB가 계산), `chat_messages.note` 열이 더해진다. 개발 DB를 백업하고 마이그레이션한다
- **외부 호출**: 없다. 검색 평가는 LLM과 YES24를 부르지 않는다
- **문서**: CLAUDE.md(현재 단계, MVP 순서), `docs/design.md`(이용자 화면, 일정), `README.md`, `app/library/README.md`
