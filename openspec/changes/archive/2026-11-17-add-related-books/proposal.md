## Why

추천 실험 세 change(`add-recommendation-experiments`, `add-related-book-experiments`, `add-loan-signals`)로 비슷한 책은 `sim-rrf`(같은 시리즈·같은 저자·같은 KDC 세목·벡터 이웃을 RRF 1:1로 합침), 최근 기록은 `hist-mean`(기록 책 벡터의 평균)으로 정했다. 세 출처 장서(A)에서 `sim-rrf`는 조정 nDCG@5 0.649 → 0.700(+0.052, 구간 +0.008 ~ +0.107)이고, 대출 신호 실험에서 KDC의 몫(+0.053)도 다시 확인했다. 그런데 제품에는 아직 서명·저자 찾기만 나가 있다. 찾은 책 카드에는 "이 책과 비슷한 책"이 없고, AI 사서는 "비슷한 거", "아무거나"를 키워드 검색(`search_collection`)으로만 처리한다.

`add-loan-signals`에서 정보나루가 막혀 미룬 일(D.1~D.4)도 남아 있다. 정보나루는 막힌 지 하루가 안 됐고 언제 풀릴지 모른다. 그래서 정보나루가 필요 없는 일(남겨 둔 분야 실행, 결과 문서)만 이 change 맨 앞에 두고, 정보나루가 필요한 일(남은 11회 받기, `s10` 다시 재기)은 대출 테이블 change로 다시 옮긴다. 다시 재는 것은 함께 대출 변형뿐이라 지금 기본값은 바뀌지 않는다.

## What Changes

- **미룬 일 중 정보나루가 필요 없는 것 먼저**(D.3·D.4, `add-loan-signals`에서 옮김, 2026-11-17 사용자 요청으로 고침)
  - D.3: 남겨 둔 분야를 정해 둔 변형으로 실행한다. `sim-best`·`hist-best`는 지금 기본값(`sim-rrf`, `hist-mean`)이다. 세트와 실행 전 라벨 304건은 이미 있다.
  - D.4: 결과 문서와 마지막 점검을 이 change의 문서 일과 함께 한다.
  - D.1(남은 11회, 인기 기간)과 D.2(`s10`을 넣어 함께 대출 변형 다시 재기)는 대출 테이블 change(가칭 `add-loan-signal-store`, 정보나루 약관 확인 뒤)로 다시 옮긴다. 함께 대출은 테이블이 있어야 제품에 쓸 수 있으므로 채택 여부도 그 change에서 정한다.
  - 이 change에서는 정보나루를 부르지 않는다.
- **비슷한 책 API**(LLM 없음): `GET /catalog/books/{library_book_id}/similar`.
  - 찾은 책 카드 아래와 찾기 결과 화면이 이 API를 부른다.
  - 기본 설정(`SimilarSettings()`)으로 최대 5권을 낸다. 결과마다 근거 코드와 근거 문구를 붙인다. 문구는 데이터에서 만든다(`같은 시리즈`, `같은 지은이`, `같은 분류 813.7`, `내용이 비슷한 책`).
  - 기관 개별 기능은 기준 책에 따라 범위를 좁힐 수 있다(훅). 어린이 기능은 기준 책이 어린이 도서이면 어린이 도서 안에서만 찾는다.
- **AI 사서 tool `find_related_books`**: 입력은 `library_book_id`이고 비워도 된다.
  - 값이 있으면 그 책과 비슷한 책을 찾는다(위 API와 같은 service).
  - 비우면 지금 대화 세션의 책으로 찾는다. 세션의 책은 고른 책, 찾은 책, 추천한 책이고, 최신 순으로 서로 다른 3권까지 쓴다(`hist-mean`).
  - 세션에 책이 없으면("아무거나") 우리 도서관 인기(180일)로 채운다. 그것도 비면 빈 결과다.
  - 어린이 기능은 범위를 어린이 도서로 좁힌 `find_related_children_books`를 끼운다. 이 tool을 쓴 실행도 어린이 요청이다.
  - 기존 `search_collection`은 그대로 둔다.
- **대화 세션의 책 id**: `chat_messages`에 코드가 쓰는 기관 도서 id 목록 칸을 더한다(마이그레이션). 세션이 끝나면 메시지와 함께 지워진다. 회원과 잇지 않는다.
- **실행 값 주입**: 실행기가 부르는 쪽이 넘긴 읽기 전용 값(이번에는 세션의 책 id)을 tool에 넘긴다. LLM은 이 값을 바꿀 수 없다.
- **Open Questions 정리**
  - 시리즈 상한 1은 켜지 않는다(실험에서 품질이 조금 낮았다).
  - 결과를 비울 유사도 문턱은 있는 라벨로 진단한다. 벡터 근거만 있는 책에 대해서이고, 정한 규칙을 넘을 때만 넣는다.
  - 시리즈 다음 권 순서(권차)는 권차 정규화와 함께 미룬다.
- **에이전트 평가 시나리오**: "비슷한 거", "아무거나", 어린이 책에서 비슷한 책 시나리오를 `evals/librarian`에 더한다. LLM으로 돌리는 것은 호출 수를 알리고 승인을 받은 뒤에만 한다.
- **범위 밖**(사용자 결정 2026-11-17)
  - 주제로 찾기(`hybrid-k60`)를 AI 사서에 잇는 일은 다음 change로 나눈다(가칭 `add-topic-search-tool`). 요청마다 임베딩 서버가 필요하고, 행동 변화를 LLM 평가로 전후 비교해야 하기 때문이다.
  - 함께 대출·정보나루 인기의 운영자 층 테이블과 갱신 실행, 미룬 일 D.1·D.2는 정보나루 약관을 확인한 뒤 `add-loan-signal-store`에서 한다. 제품의 대출 신호 공급은 없음(`None`)으로 둔다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `catalog/related-recommendation`: 비슷한 책 API, 근거 코드와 문구, 기관 개별 범위 훅, 제품 기본 설정과 대출 신호 공급 없음, (진단 결과에 따라) 벡터 근거만 있는 책의 문턱
- `agent/librarian`: 조회 tool에 관련 책 tool을 더함, 세션의 책으로 찾는 최근 기록, 관련 책 요청에 답하는 에이전트 동작(평가)
- `agent/chat-sessions`: 저장 내용에 책 id 목록 칸
- `agent/runner`: 실행 값 주입
- `features/children`: 어린이 관련 책 tool, 어린이 요청 판단에 그 tool, 비슷한 책 API의 어린이 범위
- `platform/database-schema`: `chat_messages`의 책 id 목록 칸

## Impact

- 코드: `app/library/recommendation/related.py`(근거 문구, 제품 진입 함수), 새 `app/library/services/related.py` 또는 같은 패키지의 service, `app/library/api/catalog.py`, `app/library/tools.py`, `app/library/librarian.py`(프롬프트, 프로필 버전), `app/library/services/chat.py`(세션의 책 id), `app/library/models/chat.py`, `app/library/hooks.py`, `app/agent/tools.py`·`runner.py`(실행 값), `app/features/children/`(tool, 검사, 범위 훅), `app/main.py`(등록)
- DB: 마이그레이션 1개(`chat_messages.library_book_ids`). 적용 전에 개발 DB를 `pg_dump`로 백업한다.
- API: `GET /catalog/books/{library_book_id}/similar` 추가. SSE 사건 순서와 내용은 바뀌지 않는다.
- 외부 호출: 없음. 정보나루는 부르지 않는다. LLM 호출 없음(평가 실행은 별도 승인).
- 임베딩 서버: 제품 경로에는 필요 없다(저장된 벡터만 씀). 남겨 둔 분야 주제 질의 8개를 처음 인코딩할 때만 띄우고 내린다(D.3).
- 문서: `CLAUDE.md`(현재 단계, MVP 순서에 `add-topic-search-tool`과 약관 확인 뒤 `add-loan-signal-store` 추가), `docs/design.md`, `app/library/README.md`, `app/features/README.md`, `evals/recommendation/README.md`, `docs/reports/search-recommendation-strategy.md`(9절)
