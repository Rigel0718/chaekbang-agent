## Context

- **이긴 설정**(proposal Why, `docs/reports/search-recommendation-strategy.md` 1절)
  - 비슷한 책: `sim-rrf`. `SimilarSettings()` 기본값(같은 시리즈·같은 저자·같은 KDC 세목(`section`, 서명 순)·벡터 이웃, RRF k 60 1:1, 시리즈 묶기·MMR 끔, 5권)
  - 최근 기록: `hist-mean`. `HistorySettings()` 기본값(기록 책 벡터 평균, 기록 신호는 벡터만, 모자라면 인기로 채움)
  - 둘 다 **저장된 벡터만** 쓴다. 질의를 인코딩하지 않으므로 서비스 중에 임베딩 서버가 필요 없다. 걸린 시간은 기준 책당 약 37ms, 기록당 약 27ms다(실험 장서 525권).
  - 주제로 찾기 `hybrid-k60`은 요청마다 질의를 인코딩한다. 이 change에서 다루지 않는다(Non-Goals).
- **지금 제품 경로**
  - 찾기: `GET /catalog/search`, `GET /catalog/suggest`, `find_book` tool, 대화의 찾은 책 카드(`found` 사건, 최대 3권)
  - AI 사서 tool: `search_collection`, `find_book`, `get_book_detail`, `get_library_guide`. 어린이 기능이 `search_children_books`를 끼운다(`search_tool`에 `within`).
  - `related.py`의 `find_similar`, `find_from_history`는 테스트와 실험에서만 불린다.
  - `ToolContext`는 `library_id`와 DB 세션만 가진다. tool은 대화 세션을 모른다.
  - `chat_messages`에는 책 표시 글(`note`, `[고른 책: #12 데미안]`)과 답 글(`[추천한 책: #id 서명]`)만 있고 책 id 칸이 없다.
- **대출 신호**: `LoanSignals`는 실험에서만 파일로 공급한다. 제품 테이블이 없다(사용자 결정, 아래 결정 1).
- **미룬 일**: `add-loan-signals`의 D.1~D.4. 정보나루가 2026-11-17에 `upstream_unavailable`로 막혀 남은 11회를 받지 못했다. 그때까지의 결론은 기본값 그대로다(`sim-rrf`, `hist-mean`). 남겨 둔 분야 세트(주제 8, 기준 책 8, 최근 기록 4)와 실행 전 라벨 304건은 이미 있다. 막힌 지 하루가 안 됐고 언제 풀릴지 모른다(결정 2).

## Goals / Non-Goals

**Goals:**

- 실험이 잰 코드(`find_similar`, `find_from_history`)를 제품 경로가 **그대로** 부른다. 제품 경로에서 설정을 따로 고르지 않는다. 기본값이 바뀌면 제품도 함께 바뀐다.
- 결과마다 "왜 이 책인지"를 데이터로 보여 준다. 문구는 코드가 신호에서 만들고 LLM이 만들지 않는다.
- 어린이 범위, 기관 범위는 코드로 강제한다. 다른 기관의 책은 기준 책으로도 결과로도 쓸 수 없다.
- change의 끝이 외부 API가 풀리는 때에 묶이지 않는다. 정보나루가 필요한 일은 이 change에 두지 않는다.

**Non-Goals:**

- 주제로 찾기를 AI 사서에 잇기, `search_collection`을 바꾸기(다음 change `add-topic-search-tool`)
- 함께 대출·정보나루 인기의 운영자 층 테이블과 갱신 실행(정보나루 약관 확인 뒤)
- 미룬 일 D.1(정보나루 11회, 인기 기간)과 D.2(`s10` 다시 재기). 대출 테이블 change(가칭 `add-loan-signal-store`)로 다시 옮긴다(결정 2)
- 대화 추천 품질 평가(어울림 라벨, Hit Rate)와 LLM 채점(`add-recommendation-evals`)
- 비슷한 책 API의 노출 기록(Open Questions 1)
- 시리즈 다음 권 순서(권차 정규화와 함께, Open Questions 2)
- 화면(`add-web-ui`)

## Decisions

### 1. 범위 나누기 (2026-11-17 사용자 결정)

| 후보 | 이번 | 이유 |
| --- | --- | --- |
| 미룬 일 D.1·D.2 | 뺌 → `add-loan-signal-store` | 정보나루가 필요하고, 결과가 함께 대출 변형에만 닿는다(결정 2) |
| 미룬 일 D.3·D.4 | 넣음, 맨 앞 | 정보나루가 필요 없다 |
| 찾은 책 카드 아래 비슷한 책 | 넣음(REST) | 결정 4 |
| AI 사서 tool | 비슷한 책·최근 기록만 | 주제로 찾기는 임베딩 서버를 상시로 띄워야 하고, `search_collection`을 바꾸면 AI 사서 행동이 바뀌어 LLM 평가 전후 비교가 필요하다 |
| REST | 비슷한 책만 | 최근 기록은 대화 세션의 책을 쓰므로 tool로만 쓴다(결정 8) |
| 빈 기록 "아무거나" | 우리 도서관 인기만 | 정보나루 인기는 테이블이 없어 공급이 없다 |
| 대출 테이블과 갱신 | 뺌 | 정보나루 약관(저장·재배포·출처 표기)을 확인하기 전이다. 함께 대출은 실험에서 채택되지 않았다 |
| Open Questions | 결정 10 | |

분량은 약 4.5일이다(아래 표). 다음 change `add-topic-search-tool`(가칭)은 `add-related-books`와 `add-recommendation-evals` 사이에 둔다. 대출 테이블 change `add-loan-signal-store`(가칭)는 정보나루 약관을 확인한 뒤로, 순서는 정하지 않고 MVP 순서 끝의 "약관 확인 뒤" 항목으로 적는다. `CLAUDE.md`의 MVP 순서를 고친다.

| 묶음 | 일 |
| --- | --- |
| 미룬 일(남겨 둔 분야 실행, 문서) | 0.75 |
| 제품 service, 근거 문구, 범위 훅, REST | 1 |
| 실행 값, 세션의 책(마이그레이션), tool, 어린이 tool·검사, 프롬프트 | 1.5 |
| 문턱 진단 | 0.5 |
| 평가 시나리오, 문서, 마지막 점검 | 0.5 |

### 2. 미룬 일: 정보나루가 필요 없는 것만 (2026-11-17 사용자 요청으로 고침)

처음 안은 D.1~D.4를 모두 맨 앞에 두고, 정보나루가 풀릴 때까지 하루 한 번 다시 시도하는 것이었다. 막힌 지 하루가 안 됐고 언제 풀릴지 몰라서, change의 끝이 외부 API에 묶인다. 그래서 정보나루가 필요한 일은 이 change에서 뺀다.

| 일 | 정보나루 | 이번 | 이유 |
| --- | --- | --- | --- |
| D.1 남은 11회 받기, 인기 기간 | 필요 | 뺌 → `add-loan-signal-store` | 인기 기간은 정보나루 인기에만 쓰는데, 그 공급(테이블)이 그 change에 있다 |
| D.2 `s10` 넣어 단계 6·최근 기록 다시 재기 | 필요(D.1 결과) | 뺌 → `add-loan-signal-store` | 다시 재는 것은 함께 대출 변형(`sim-best-co`, `hist-mean-co`·`-all`)뿐이다. 함께 대출은 테이블이 있어야 제품에 쓸 수 있으니, 채택 여부도 그 change에서 정하는 것이 맞다 |
| D.3 남겨 둔 분야 실행 | 필요 없음 | 넣음, 맨 앞 | 정해 둔 변형의 `sim-best`·`hist-best`는 지금 기본값(`sim-rrf`, `hist-mean`)이다. 함께 대출 변형이 없어 `s10`의 빈 신호와 상관없다 |
| D.4 결과 문서·마지막 점검 | 필요 없음 | 넣음(8절과 함께) | D.1·D.2를 다시 옮겼다고 적는다 |

- **D.2를 빼도 기본값은 그대로다.** D.2가 바꿀 수 있는 것은 함께 대출 변형의 수치뿐이다. KDC 단계(단계 5)와 기록의 규칙 신호(`hist-mean-rules`)는 함께 대출 값을 읽지 않아 `s10`과 상관없이 이미 끝났다(`add-loan-signals` 결과: 기본값 그대로).
- **제품 코드는 기본 설정 객체만 읽는다.** service는 `SimilarSettings()`, `HistorySettings()`를 그대로 쓰고 값을 다시 적지 않는다. 나중에 `add-loan-signal-store`에서 함께 대출이 채택되면 기본값 한 곳, 스펙, 대출 신호 공급만 바꾸면 제품이 따라간다.
- **옮기는 곳**
  - `add-loan-signal-store`(가칭, 정보나루 약관 확인 뒤): 운영자 층 `book_loan_signals`·`national_popular_loans`와 갱신 실행(`add-loan-signals` 결정 5), D.1·D.2, 함께 대출과 정보나루 인기의 제품 공급
  - 그 change의 tasks 맨 앞에 D.1·D.2를 둔다. 호출 수(11회, 하루 500건의 2.2%)와 대상 ISBN(`9791199489509`, `9791199491717` = `s10`, `9791199509009`)을 이 design, CLAUDE.md 현재 단계, 보고서 9절에 적어 둔다. archive된 `add-loan-signals` tasks는 고치지 않는다.
  - 이 change에서는 정보나루를 한 건도 부르지 않는다.
- **순서**(tasks): D.3 → 제품 일(결정 3~9) → 문턱 진단(결정 10) → D.4·문서·마지막 점검
- 안: (a) 처음 안대로 기다린다 — 끝이 외부에 묶인다. (b) D.1~D.4를 모두 뺀다 — D.3은 정보나루 없이 할 수 있고 세트와 실행 전 라벨 304건이 이미 있어 미룰 이유가 없다. **(c) 정보나루가 필요한 D.1·D.2만 대출 테이블 change로 옮긴다 (선택)**.

### 3. 제품 service

- 위치는 `app/library/services/related.py`다. REST와 tool이 이 함수만 부른다(설계 원칙 1).
  - `similar_for_book(session, library_id, library_book_id, *, within=None) -> list[RelatedItem]`
  - `related_for_session(session, library_id, session_book_ids, *, within=None) -> list[RelatedItem]`
- 두 함수가 하는 일
  - 기준 책은 그 기관의 **찾을 수 있는 책**(`get_findable`)이어야 한다. 다른 기관이나 추천할 수 없는 책은 찾을 수 없음 오류(404)다.
  - 모델 이름은 설정의 임베딩 모델(`embedding_model`)이다. 인코더를 만들지 않는다.
  - 대출 신호 공급은 `None`이다. 함께 대출 신호는 비고, 인기 채우기는 우리 도서관 인기에서 끝난다.
  - 기관 개별 범위(결정 6)와 부르는 쪽 범위(`within`)를 함께 건다(AND).
  - 결과(`Ranked`)를 카드 요약(`build_summaries`와 같은 값)과 근거(결정 5)로 바꾼다.
- `RelatedItem`은 `BookSummary`에 `basis`(근거 코드 목록)와 `basis_text`(문구 목록)를 더한 스키마다. 노출 기록이나 질의를 저장하지 않는다.

### 4. 찾은 책 카드 아래 비슷한 책: REST

- `GET /catalog/books/{library_book_id}/similar` → `list[RelatedBook]`(최대 5권). 직원 토큰이고 키오스크 계정도 쓴다. 기관은 토큰으로 정한다.
- **SSE에 넣지 않는다.**
  - `found` 사건은 LLM 전에 나가는 찾기 결과다. 거기에 책마다 5권을 붙이면 사건이 3 × 5권으로 커지고, 이용자가 고르지 않은 책까지 계산한다.
  - 화면이 카드를 펼칠 때 부르면 한 권만 계산한다. 찾기 결과 화면(`/catalog/search`)과 고른 책 카드도 같은 API를 쓴다.
  - SSE 사건의 순서·내용을 바꾸지 않아서 기존 스펙과 테스트가 그대로다.
- 안: (a) `found` 사건에 비슷한 책을 붙인다 — 위 이유로 버림. (b) 새 `similar` 사건 — 사건 순서 스펙이 바뀌고 한 턴에 계산이 몰린다. **(c) REST (선택)**.
- 찾은 책은 추천이 아니지만, 그 아래 비슷한 책은 추천이다. 그래서 어린이 범위 훅(결정 6)을 건다. 노출 기록은 이번에 남기지 않는다(Open Questions 1).

### 5. 근거 코드와 문구

- 근거 코드는 결과가 오른 신호 이름이다: `series`, `author`, `kdc`, `vector`, `popular`(최근 기록·빈 기록), `national_popular`(공급이 없어 이번에는 나오지 않음).
- 문구는 코드가 만든다. LLM은 이 문구와 소개를 근거로만 이유를 쓴다(설계 원칙 6).

| 코드 | 비슷한 책 | 최근 기록 |
| --- | --- | --- |
| `series` | `같은 시리즈` | (기록 신호에 없음) |
| `author` | `같은 지은이` | `최근 본 책과 같은 지은이` |
| `kdc` | `같은 분류 {세목}`(예: `같은 분류 813.7`) | `최근 본 책과 같은 분류` |
| `vector` | `내용이 비슷한 책` | `최근 본 책과 내용이 비슷한 책` |
| `popular` | — | `우리 도서관에서 많이 빌린 책` |

- 순서는 시리즈 → 지은이 → 분류 → 내용이고 두 개까지 보여 준다. 코드 목록(`basis`)은 모두 준다.
- 세목은 그 결과 책의 표시 KDC 세목이다(`kdc_section`). 세목 신호이므로 기준 책과 같다.
- 지은이 이름은 문구에 넣지 않는다. 카드에 저자가 이미 있다.
- 안: 신호별 순위를 그대로 보여 준다(`벡터 3위`) — 이용자에게 뜻이 없다.

### 6. 기관 개별 기능의 범위 훅

- `hooks.py`에 사건이 아니라 **범위 제공자**를 하나 더한다: `related_scope(session, library_id, base_ids) -> Select | None`. 등록된 제공자의 조건을 모두 AND로 건다. 없으면 범위를 더하지 않는다.
- **어린이 기능의 제공자**: 기준 책이 **모두** 그 기관의 어린이 도서이면 어린이 도서로 좁힌다. 아니면 좁히지 않는다.
  - 비슷한 책은 기준 책이 하나라 "그 책이 어린이 도서인가"다. 그림책에서 비슷한 책을 보면 그림책이 나온다.
  - 최근 기록에서 어린이 도서와 일반 도서가 섞이면 좁히지 않는다. 섞인 기록의 어린이 판단은 `add-recommendation-evals`의 Open Question(요청 판단)이다.
  - 대화에서 어린이 요청이면 이 훅과 상관없이 어린이 tool(결정 7)과 최종 검사가 지킨다.
- 공통 코드는 조건의 뜻을 모른다(기존 `within`과 같다). 훅 등록은 `app/main.py`에서 하고, 평가 진입점도 같은 등록을 쓴다.
- 안: 비슷한 책 API에 `audience` 파라미터 — 공통 API에 기관 개별 값이 들어간다(코딩 규칙 위반).

### 7. AI 사서 tool

- **tool 하나, 입력 하나**: `find_related_books(library_book_id: int | None)`
  - 값이 있으면 비슷한 책(`similar_for_book`)이다.
  - 비우면 지금 대화 세션의 책으로 최근 기록(`related_for_session`)이다. 세션에 책이 없으면 우리 도서관 인기다.
  - 비슷한 책과 "아무거나"를 tool 둘로 나누면 LLM이 고를 것이 늘어난다. 둘 다 "책에서 출발하는 추천"이고 입력의 있고 없음으로 갈린다.
- 결과는 `search_result`와 같은 꼴에 `basis_text`를 더한다. 빈 결과면 `note`(`비슷한 소장 도서를 찾지 못했다. search_collection으로 다시 찾거나 희망도서를 안내한다`)를 준다.
- `record_fields`에 `library_book_id`를 둔다. 책 id는 개인정보가 아니고, 어느 책에서 출발했는지는 실행 기록에서 볼 값이다.
- **어린이 tool**: 어린이 기능이 `find_related_children_books`를 끼운다. 같은 factory(`related_tool`)로 범위만 어린이 도서다(`search_tool`과 같은 모양).
  - 어린이 요청 판단의 tool 이름을 집합으로 바꾼다(`search_children_books`, `find_related_children_books`).
  - 프롬프트 문구: 어린이 요청에서 "비슷한 거"는 이 tool을 쓴다.
- **프롬프트**(BASE_PROMPT에 더함)
  - `비슷한 거`, `이런 책 또`, 고른 책·찾은 책을 가리키는 요청은 `find_related_books`에 그 책 id를 넣는다.
  - `아무거나`, `추천해 줘`처럼 조건이 없으면 `find_related_books`를 비워서 부른다.
  - 이유는 결과의 `basis_text`와 소개에만 근거한다.
- 프로필 버전을 올린다. tool이 늘어 실행 기록의 프로필이 달라지기 때문이다.
- `search_collection`은 그대로 둔다. 주제·분위기 요청은 지금처럼 키워드 검색이다.

### 8. 대화 세션의 책

- **칸**: `chat_messages.library_book_ids integer[] NOT NULL DEFAULT '{}'`. 코드가 쓴다.
  - 이용자 행: 고른 책이나 찾은 책의 id(`note`와 같은 책)
  - 답 행: 카드가 된 추천 책의 id(`[추천한 책: …]`과 같은 책)
  - 기존 행은 빈 목록이다.
- **고르는 법**: 세션의 메시지를 최신 순으로 보며 서로 다른 id를 **3권까지** 모은다. 실험의 기록이 2~3권이었다. 이번 턴의 고른 책·찾은 책도 들어간다(이용자 행을 실행 전에 저장한다).
  - 지금은 그 기관에 없거나 추천할 수 없게 된 책은 `find_from_history`가 건너뛴다.
- **개인정보**: 세션은 회원과 잇지 않고 마지막 입력 5분 뒤 끝나며 메시지와 함께 지워진다. id 칸도 같이 지워진다. `note`에 이미 있는 값과 같은 정보라 새로 남기는 개인정보가 없다.
- 안: (a) `note`와 답 글에서 `#id`를 정규식으로 읽는다 — 서명에 `#3`이 있으면 틀린다. (b) LLM이 tool에 id 목록을 넘긴다 — 사용자 결정으로 버림(세션의 책은 코드가 정한다). **(c) id 칸 (선택)**.

### 9. 실행 값 주입

- tool은 대화 세션을 모른다. 세션의 책을 tool 입력으로 받으면 LLM이 정하는 값이 된다.
- `ToolContext`에 `values: Mapping[str, Any]`(읽기 전용, 기본 빈 값)를 더한다. `run(..., tool_values=...)`으로 부르는 쪽이 넘기고 실행기는 뜻을 모른 채 그대로 전한다.
- 대화(`services/chat.py`)는 `{"session_book_ids": (…)}`을 넘긴다. 이름은 `app/library`의 상수다. 실행기는 이 이름을 모른다.
- LLM 입력과 섞이지 않는다. 입력 모델은 그대로 `extra="forbid"`이고, 실행 값은 실행 기록에 남기지 않는다.
- 안: `ToolContext`에 `session_book_ids` 칸 — 공통 실행기가 AI 사서의 개념을 알게 된다.

### 10. Open Questions 정리

- **시리즈 상한 1: 켜지 않는다.** `sim-series1`은 겹침만 줄이고(0.57 → 0.07) 조정이 -0.014(0·12·2)였다. 비슷한 책에서 같은 시리즈가 나오는 것은 손해가 아니었다. 다시 재지 않는다.
- **시리즈 다음 권(권차): 미룬다.** 같은 시리즈 안 순서는 서명 정렬 순서이고 숫자는 글자 순서다(`10권`이 `2권`보다 앞). 권차 정규화(CLAUDE.md 도메인 용어 "권차")가 먼저 필요하고 범위가 커진다. Open Questions 2.
- **결과를 비울 문턱: 있는 라벨로 진단한다.**
  - 대상은 비슷한 책 결과 중 **근거가 벡터 하나뿐인 책**이다. 규칙 근거(시리즈·지은이·분류)가 있는 책은 문턱으로 빼지 않는다.
  - 데이터: 비슷한 책 세트(조정 14, 확인 6)의 `sim-rrf` 상위 10권, 지금 라벨(0·1·2), 기준 책 벡터와의 코사인. 새 라벨을 달지 않는다.
  - 규칙: 0.30~0.80을 0.01 간격으로 보며, 조정에서 **벡터 근거만 있는 0 라벨을 절반 이상 빼고 2 라벨은 5% 이하만 빼는** 가장 큰 문턱을 고른다. 확인 세트에서도 같은 방향(0을 더 많이 뺌)이어야 한다.
  - 넘는 문턱이 없으면 **문턱 없음**이다. 설정 `min_vector_similarity`는 두되 기본값은 `None`이다.
  - 넘으면 기본값을 그 값으로 하고, nDCG@5가 떨어지지 않는지(같은 명령, 짝 비교) 보고, 스펙 delta를 고친 뒤 알린다.
  - 결과가 5권보다 적어지는 것은 문턱의 뜻이다. 인기로 채우지 않는다(비슷한 책은 인기 채우기를 쓰지 않는다).
  - 최근 기록에는 걸지 않는다. 세트가 조정 7개뿐이다.
- 주제로 찾기의 "소장 도서가 없는 요청" 문턱은 `add-topic-search-tool`로 넘긴다.

### 11. 에이전트 평가 시나리오

- `evals/librarian`에 시나리오를 더한다(설계 규칙: 에이전트 동작은 pytest 대신 평가).
  - 고른 책 뒤 `비슷한 거 있어요?` → `find_related_books`에 그 책 id, 추천은 결과 안의 책
  - `아무거나 추천해 줘`(세션에 책 없음) → `find_related_books`를 비워 부름, 인기가 비면 없다고 답함
  - 어린이 그림책을 고른 뒤 `이거랑 비슷한 그림책` → 어린이 도서만 추천
  - 이유에 결과에 없는 근거(수상, 줄거리)를 쓰지 않음
- **실행은 승인 뒤**: LLM 호출이라 호출 수(시나리오 수 × 반복)와 예상 비용(`LLM_PRICES`)을 알리고 승인을 받는다. 승인이 없으면 시나리오와 채점 코드만 넣고, 가짜 LLM으로 시나리오 틀만 확인한다.

### 12. 테스트

- service(테스트 DB의 작은 장서): 기준 책 기관 분리(404), 추천할 수 없는 기준 책 404, 결과의 기관 분리, 근거 코드와 문구, 문구 두 개 상한과 순서, 대출 신호 공급 없음(함께 대출 비어 있음, 정보나루 인기로 채우지 않음), 결과가 `find_similar` 기본 설정과 같은 순서
- REST: 200·404·키오스크 토큰, 응답 항목, 질의·노출 기록을 남기지 않음
- 범위 훅: 어린이 기준 책 → 어린이 도서만, 일반 기준 책 → 좁히지 않음, 섞인 기록 → 좁히지 않음, 다른 기관의 어린이 구분을 보지 않음
- 실행 값: 값이 handler에 그대로 감, LLM이 같은 이름을 입력에 넣으면 거부, 실행 기록에 없음
- 세션의 책: 이용자 행·답 행의 id, 최신 순 서로 다른 3권, 이번 턴 포함, 다른 세션·다른 기관의 행을 읽지 않음, 세션 삭제와 함께 지워짐
- tool: id 있음 / 비움 / 세션에 책 없음 / 빈 결과의 note, 어린이 tool의 범위, 어린이 요청 판단(tool 이름 집합)
- 마이그레이션: upgrade·downgrade·autogenerate 차이 없음
- 기존 동작: `find_similar`·`find_from_history` 기본 설정의 결과가 시작 전 기준 실행과 같음, `evals.catalog_search` 기준과 같음
- 대량 삽입·롤백 뒤 테스트 DB `VACUUM ANALYZE`

### 13. 함께 고칠 문서

| 문서 | 고칠 곳 |
| --- | --- |
| `CLAUDE.md` | 현재 단계(남겨 둔 분야 결과, 제품에 나간 것, D.1·D.2를 `add-loan-signal-store`로 옮김), MVP 순서에 `add-topic-search-tool`과 약관 확인 뒤 `add-loan-signal-store`, 디렉터리 구조(`services/related.py`), 명령 |
| `docs/design.md` | 추천 결과 한 줄, 주차 표 |
| `app/library/README.md` | 비슷한 책 API, `find_related_books`, 세션의 책, 범위 훅, "REST와 tool에는 아직 잇지 않았다" 문장 고치기 |
| `app/features/README.md` | 어린이 관련 책 tool, 범위 제공자 |
| `app/agent/README.md` | 실행 값 |
| `evals/recommendation/README.md` | 남겨 둔 분야 결과 표, 문턱 진단 |
| `docs/reports/search-recommendation-strategy.md` | 1절 "제품 연결", 9절 남은 일 |

## Risks / Trade-offs

- **[`s10`을 다시 재지 않은 채 내보낸다]** 함께 대출 변형의 수치가 한 권만큼 덜 잰 상태다 → 기본값에는 함께 대출이 없어 제품 결과와 상관없다. `add-loan-signal-store`가 테이블과 함께 다시 잰다(결정 2).
- **[미룬 일이 두 번 옮겨진다]** 잊히기 쉽다 → CLAUDE.md 현재 단계, 보고서 9절, 메모에 옮긴 곳(`add-loan-signal-store`)을 함께 적는다.
- **[가져오기 기관은 "아무거나"가 빈다]** 대출 행이 없으면 우리 도서관 인기가 비고, 정보나루 인기 공급도 없다 → 빈 결과의 `note`로 LLM이 `search_collection`이나 희망도서로 넘어간다. 결과 문서와 README에 적는다. 정보나루 인기 테이블이 생기면 풀린다.
- **[벡터가 없는 책]** 적재 전인 책은 벡터 이웃이 비고 규칙 신호만 남는다 → 결과가 적거나 빈다. 증분 적재(`embed_books.py --incremental`)를 README에 적는다. 오류로 보지 않는다.
- **[실험 장서와 실제 장서가 다르다]** 시리즈·저자 신호가 드문 스테디셀러 장서였다 → 실제 기관에서 다시 본다(`add-loan-signals` Open Question 2 그대로).
- **[근거 문구가 이유를 대신한다]** LLM이 `basis_text`를 그대로 이유로 쓰면 이유가 단조롭다 → 품질은 `add-recommendation-evals`에서 본다. 지어낸 근거보다 낫다.
- **[tool이 늘어 LLM이 잘못 고른다]** 주제 요청에 `find_related_books`를 쓸 수 있다 → 결과는 늘 소장 도서라 규칙 위반은 없다. 평가 시나리오로 본다(실행은 승인 뒤).
- **[범위 훅의 판단]** 어린이 기준 책이면 어린이 도서로만 좁힌다. 그림책을 고른 어른에게도 그림책만 나온다 → 의도한 동작이다(그 책과 비슷한 책). 섞인 기록은 좁히지 않는다.
- **[문턱 진단이 라벨에 기댄다]** 라벨은 Claude 초안이고 사람은 표본만 봤다 → 규칙을 엄격하게 두고(0 절반 이상, 2는 5% 이하), 넘지 못하면 문턱 없음이다.

## Migration Plan

1. 시작 전 기준: `uv run pytest`, similar·history 기준 실행(`evals.recommendation similar --split all --variants sim-vec,sim-rrf,sim-best`), `evals.catalog_search`. 수치를 결과에 적는다.
2. 남겨 둔 분야 실행(D.3). 라벨을 바꾸기 전마다 `/home/pollux/chaekbang-backups/labels-<시각>-<단계>/`로 백업하고 경로를 알린다.
3. 마이그레이션: 개발 DB를 먼저 `pg_dump`로 `/home/pollux/chaekbang-backups/chaekbang-<시각>-before-related-books.dump`에 백업한다. 명령은 `&&`로 잇는다. 그다음 `alembic upgrade head`다.
4. 제품 일과 테스트, 문턱 진단
5. 문서, 마지막 점검(pytest, ruff, `evals.catalog_search`, 기준 실행과 같은지)
6. 되돌리기: 코드는 커밋 되돌리기, DB는 `alembic downgrade -1`(칸 하나) 또는 백업 복원, 라벨은 백업 폴더

## Open Questions

1. **비슷한 책 API의 노출 기록**: 지금 노출 기록은 AI 사서 실행(`run_id`)에 묶여 있다. 카드 아래 비슷한 책을 추천 품질 지표에 넣으려면 출처 칸이 필요하다. `add-recommendation-evals`에서 지표를 정할 때 함께 정한다.
2. **시리즈 다음 권**: 권차 정규화(`2권`, `Ⅱ`, `하`)를 만든 뒤 같은 시리즈 신호의 순서를 권차 순으로 바꿀지 본다.
3. **정보나루 인기 테이블**: 약관 확인 뒤 `add-loan-signal-store`가 `national_popular_loans`와 갱신 실행을 만들면 "아무거나"의 두 번째 단계와 어린이 연령 묶음이 제품에서 켜진다. 규칙(스펙 "정보나루 인기로 채우기")은 이미 있다.

## 결과

### 시작 전 기준 (2026-11-17)

- `uv run pytest`: 1496 통과, 7 건너뜀, 실패 2.
  - `tests/evals/test_librarian_eval.py::test_scenarios_cover_eval_requirements`: 이 change의 새 평가 요구사항("관련 책 요청에 답함")에 평가 시나리오가 아직 없어서다. 7.3에서 시나리오를 더하면 통과한다.
  - `tests/library/test_book_lookup_speed.py`: 같은 시각에 추천 실험을 돌려 DB가 바빴다. 따로 돌리면 통과한다.
- `ruff check`: 통과
- 비슷한 책 `runs/20261117-152916`(`sim-vec`·`sim-rrf`·`sim-best`): `sim-rrf` 조정 0.700(+0.052, 6·6·2, +0.008 ~ +0.107), 확인 0.689. `results.json`의 `sim-rrf`가 `143307`과, `sim-vec`가 `143256`과 같다.
- 최근 기록 `runs/20261117-152926`(`hist-mean`·`hist-best`): 조정 0.710, 확인 0.829. `hist-mean`이 `123751`과 같다.
- `evals.catalog_search` `20261117-152944`: 표가 `145626`과 같다.

### 남겨 둔 분야 (D.3, 2026-11-17)

- 정해 둔 변형: `sim-best` = `sim-rrf`, `hist-best` = `hist-mean`(기본값 그대로).
- 한 번 실행: topic `runs/20261117-153545`(질의 8개를 처음 인코딩, 임베딩 서버는 실행 뒤 내림), similar `153057`, history `153059`. 모두 `--split all`(남겨 둔 분야 세트는 모두 확인 항목이다).
- 라벨 백업 `/home/pollux/chaekbang-backups/labels-20261117-153649-before-holdout-supplement/`. 보충 라벨 149건(주제 66, 비슷한 책 55, 최근 기록 28)을 Claude가 달았다. 기존 세 라벨 파일은 바뀌지 않았다.

- **표본 검수 ②**(사용자, 2026-11-17): 주제 8, 비슷한 책 7, 최근 기록 5, 모두 20건 중 2건을 고쳤다(일치율 90%, 멈춤 문턱 6건 아래). 고친 것은 `hs02` 기준 책 『맛집에서 만난 세계지리 수업』의 『지리의 힘』 2 → 1, `hh03`의 『숫자 따라 붙이는 퍼즐 스티커북 3000』 1 → 0이다.
- 최종 두 번: topic `runs/20261117-163837`·`163906`, similar `163844`·`163913`, history `163847`·`163915`. 세 세트 모두 두 실행의 `results.json`이 같다. 규칙 위반 0건.

| 세트 | 기준 | 변형 | nDCG@5 | 차이 | 이김·비김·짐 | 95% 구간 | 읽기 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 주제 8개 | `current` 0.708 | `hybrid-k60` | 0.805 | +0.097 | 4·3·1 | -0.030 ~ +0.222 | 방향이 같음(구간이 0을 걸침) |
| 비슷한 책 8권 | `sim-vec` 0.669 | `sim-rrf` = `sim-best` | 0.666 | -0.004 | 2·5·1 | -0.030 ~ +0.012 | 차이 없음 |
| 최근 기록 4개 | `hist-mean` 0.785 | `hist-best` | 0.785 | 0.000 | 0·4·0 | - | 같은 설정 |

- 주제로 찾기는 조정에 쓰지 않은 분야에서도 키워드 검색보다 높다. 상황 질의(+0.102, 2·2·0)와 주제어 질의(+0.092, 2·1·1)가 비슷하다.
- 비슷한 책에서 `sim-rrf`가 `sim-vec`보다 높지 않다. 남겨 둔 분야 책 45권 중 같은 KDC 세목 신호가 값을 가진 기준 책이 8권 중 1권뿐이다(같은 저자 3권, 같은 시리즈 0권). 조정 세트에서 올라간 몫(+0.052)이 KDC 세목에서 왔다는 것과 맞는 모양이다. 기본값은 바꾸지 않는다(결정 11의 규칙, 근거 표시를 위한 2026-11-16 사용자 결정).
- 실행 전 결과(보충 라벨 전)의 `sim-rrf` +0.022는 라벨 없는 책 23건을 0으로 센 값이라 쓰지 않는다.

### 문턱 진단 (결정 10, 2026-11-17)

- `uv run python -m evals.recommendation.threshold 20261117-152916`(`sim-rrf` 상위 10권, 지금 라벨). 표는 `runs/20261117-152916/threshold.md`.
- 조정: 벡터 근거만 있는 책 87건(0 라벨 40, 1 라벨 30, 2 라벨 17). 코사인은 0 라벨 0.354 ~ 0.499(가운데 0.400), 2 라벨 0.376 ~ 0.494(가운데 0.431)로 거의 겹친다.
- 확인: 20건(0 라벨 10, 2 라벨 2).

| 문턱 | 조정 0 뺌 | 조정 1 뺌 | 조정 2 뺌 | 확인 0 뺌 | 확인 2 뺌 |
| --- | --- | --- | --- | --- | --- |
| 0.40 | 50% | 40% | 18% | 10% | 0% |
| 0.45 | 92% | 93% | 71% | 80% | 50% |
| 0.50 | 100% | 100% | 100% | 90% | 100% |

- **결론: 문턱 없음.** 0 라벨을 절반 이상 빼는 가장 낮은 문턱(0.40)이 2 라벨도 18%를 뺀다(규칙은 5% 이하). `min_vector_similarity` 기본값은 `None` 그대로이고 스펙도 그대로다.
- 이 장서에서 벡터 이웃의 코사인은 0.35 ~ 0.52 좁은 띠에 몰려 있어 절대값으로는 관련 없음을 가를 수 없다. 소장 도서가 없는 요청의 빈 결과는 순위가 아닌 다른 근거(대화 추천 평가의 어울림 라벨)로 다시 본다.

### 시나리오와 테스트 (8.2, 2026-11-17)

이 change의 스펙 delta 시나리오 78개가 모두 테스트(docstring에 `[capability] 요구사항 / 시나리오`) 또는 평가 시나리오(`evals/librarian/scenarios.py`의 `traces`)에 있다.

| capability | 테스트 |
| --- | --- |
| `catalog/related-recommendation` | `tests/library/test_related_books.py`(최소 유사도, 근거 문구, 범위 훅, 제품 경로), `tests/library/test_related_books_api.py`(API), `tests/evals/test_threshold.py`(진단 규칙) |
| `agent/librarian` | `tests/library/test_related_tool.py`(관련 책 tool), `tests/library/test_chat_session_books.py`(대화 세션의 책), `tests/library/test_librarian.py`(프로필의 tool). "관련 책 요청에 답함"은 평가 시나리오 `related-picked`, `related-found`, `related-anything`, `related-children` |
| `agent/chat-sessions` | `tests/library/test_chat_lookup.py`(고른 책만 보낸 턴), `tests/library/test_chat_session_books.py`(답 행·빈 행) |
| `agent/runner` | `tests/agent/test_runner.py`(실행 값 주입 넷) |
| `features/children` | `tests/features/children/test_related_children.py`, 기존 `test_librarian_children.py`·`test_rules.py`(어린이 요청 판단) |
| `platform/database-schema` | `tests/platform/test_database_schema.py`(책 id 칸, 기존 시나리오) |

- 전체 `uv run pytest`: 1566 통과, 7 건너뜀(테스트 DB `VACUUM ANALYZE` 뒤). 찾기 속도 테스트의 안정화는 tasks 8.6.
- 기준 실행 다시 돌림(8.4): similar `20261117-162249`, history `162253`의 `results.json`이 시작 전 `152916`·`152926`과 같다. 요약은 시각·걸린 시간 줄과 설정 줄의 새 칸(`min_vector_similarity: null`)만 다르다. `evals.catalog_search` `20261117-162209`의 표가 `152944`와 같다.

### AI 사서 평가 (7.4, 실제 LLM, 2026-11-17, 사용자 승인)

- `uv run python -m evals.librarian`, 시나리오 27개, `gpt-6-luna`. 결과 `evals/librarian/data/runs/20261117-163945-gpt-6-luna/`.
- 턴 29개, 입력 토큰 159,656, 출력 토큰 3,780(약 $0.018). 고정 답 비율 0%. **규칙 위반 0건**(`invented_basis` 포함).
- 기대 불일치 2건: `parenting`, `guide-mixed`. 둘 다 이용자 문장에 어린이 표현이 없는데 LLM이 `search_children_books`를 불러 어린이 판단이 켜졌다. 2026-11-11 실행(`20261111-094557`)에서는 두 시나리오가 맞았고 `no-description` 하나가 틀렸다(이번에는 맞음).
  - 이번 change가 바꾼 어린이 프롬프트 문구(관련 책 tool 두 줄)가 어린이 tool 쪽으로 기울게 했을 수 있다. 한 번 실행이라 LLM의 흔들림과 가르지 못했다.
  - 코드 검사(어린이 최종 검사)는 켜지는 쪽으로만 작동하므로 일반 요청에 어린이 도서만 나간 것이고, 규칙 위반은 아니다. `guide-mixed`는 어린이 도서 3권을 추천했다.
- **관련 책 시나리오 4개는 기대가 맞았지만 tool 결과가 모두 비었다.** 평가 표본(87권)에는 벡터가 적재돼 있지 않고 같은 시리즈·저자·KDC 신호도 거의 없다. 그래서 "추천이 tool 결과 안에 있음"은 확인되지 않았고, tool 호출 모양(`related-picked`·`related-found`·`related-children`은 고른 책·찾은 책 id, `related-anything`은 null)과 빈 결과 뒤의 행동(없다고 말함, `search_collection`·`search_children_books`로 넘어감)만 확인됐다.
- `related-children`은 어린이 관련 책 tool을 고른 책 id로 불렀고, 결과가 비자 어린이 도서 검색으로 넘어가 어린이 도서 2권을 추천했다.
- **어린이 문구 고친 뒤 다시**(사용자 요청, 2026-11-17): 어린이 프롬프트 문구에 "어린이 요청"의 뜻(이용자가 영유아·초등학생이 읽을 책이나 아이와 함께 읽을 책을 찾을 때, 이때만 어린이 tool), 아이·나이를 말하지 않은 주제 요청(예: 공룡)과 부모가 읽을 육아·훈육 책은 어린이 요청이 아니라는 줄을 더했다. 어린이 tool 두 설명에 "어린이 요청에만 쓴다"를 더했다. 코드의 어린이 요청 판단 규칙과 같은 기준이다. 프로필 버전 v5.
  - 어린이 문구에 닿는 7개만 다시 돌렸다(`--only`): `parenting`, `guide-mixed`, `related-children`, `child-dinosaur`, `grandchild-picture-book`, `elementary-science`, `children-follow-up`. 결과 `evals/librarian/data/runs/20261117-164808-gpt-6-luna/`.
  - 턴 8개, 입력 토큰 50,730, 출력 토큰 1,526(약 $0.006). **규칙 위반 0건, 기대 불일치 0건.** `parenting`·`guide-mixed`가 일반 요청으로 돌아왔고, 어린이 시나리오 다섯은 그대로 어린이 판단이다.
  - 나머지 20개는 다시 돌리지 않았다(어린이 문구만 바뀌었다). 한 번 실행이라 흔들림은 여전히 가르지 못한다.
