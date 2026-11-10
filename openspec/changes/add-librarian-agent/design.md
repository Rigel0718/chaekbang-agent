# Design

## Context

- `app/agent/`의 실행기가 있고 사용자는 없다. `run()`은 세션을 받고, 답은 검사 뒤에 사건으로 나가며, `DoneEvent`에 실행 id와 상태가 있다.
- `_with_counts`의 `holding_count`와 `held=True`는 분실·훼손 사본도 세므로 추천 조건으로 쓸 수 없다.
- `list_library_books(within=...)`는 기능이 기관 도서 조건을 넘기는 방식이고 `/children/books`가 쓴다. 공통은 그 뜻을 모른다.
- 표시 값은 `LibraryBook.shown`이고 공식 값이 먼저다. 부제와 시리즈는 공식 서지에만 있다.
- `kdc`는 파일 값만 있고 공식 서지 채움이 넣지 않아서 분야 검색의 근거가 약하다.
- 개발 DB의 데이터는 가짜 서지다. 가상 서지는 검색이 실제보다 잘 맞아 보이므로 평가는 YES24 표본을 쓴다.
- 테스트의 `session` 하나가 `get_session`을 대체한다.

## Goals / Non-Goals

**Goals:**
- `공룡 책 추천해줘`에 소장 도서로 답한다.
- 소장, 어린이, 개인정보 규칙을 코드로 지키고, 어린이 기능을 빼도 공통이 동작한다.
- 대화가 공용 PC에 남지 않는다.

**Non-Goals:**
- 토큰 단위 스트리밍. 실행기 결정을 따른다.
- 문장 속 서명의 코드 검사. 평가의 규칙 검사로 본다.
- 이름 가리기. 코드로 안정적으로 찾을 수 없다.
- 기관별 프롬프트 설정.

## Decisions

### 1. 패키지 배치

```
app/library/
├── recommendation/
│   ├── search.py   # 후보 검색, 추천 가능 조건
│   ├── checks.py   # 소장 검사
│   ├── cards.py    # 카드 만들기
│   └── events.py   # 노출 기록
├── models/chat.py  # ChatSession, ChatMessage, RecommendationEvent
├── services/chat.py
├── privacy.py      # 개인정보 가리기
├── tools.py        # search_collection, get_book_detail
├── librarian.py    # 프로필 만들기, 답 구조, 정리 규칙
└── api/librarian.py
app/features/children/
├── tools.py        # search_children_books
├── checks.py       # 어린이 검사
└── rules.py        # 어린이 요청 판단 추가
```

`recommendation_events`는 `run_id`로 `agent_runs`를 가리키므로 `library → agent` 의존이고 허용된 방향이다.

### 2. 프로필 조립

`build_librarian_profiles(extensions)`는 운영 방식별 프로필 두 개를 돌려준다. `LibrarianExtension`은 `tools`, `final_checks`, `prompt_note`만 가진 값이고, 어린이 기능이 `children_extension()`으로 내놓는다. `app/main.py`가 잇고 `app.state`에 둔다. 라우터는 기관의 `loan_mode`로 프로필을 고른다. 평가도 같은 함수를 부른다.

- **대안: 훅에 tool 등록** → 훅은 사건을 알리는 전역 목록이다. 프로필은 값으로 조립해야 프로필별로 다르게 끼울 수 있고 테스트가 전역 상태를 바꾸지 않는다.
- 프로필은 실행 중 바뀌지 않아서 프롬프트 캐시의 앞부분이 고정된다. 기관 이름 같은 값은 프롬프트에 넣지 않는다.

### 3. 후보 검색

SQL 한 번으로 찾는다. 표시 값은 `coalesce(Book.x, LibraryBook.x)`다.

- 추천 가능 조건은 `recommendable_ids(library_id)` 하나로 두고 검색과 소장 검사가 함께 쓴다.
- 비교는 양쪽 공백을 지운 `ILIKE`이고 `%`, `_`는 이스케이프한다. 한국어는 조사가 붙어 부분 문자열이 맞고, 띄어쓰기는 표기가 자주 달라서다.
- 가중치는 서명 4, 부제·시리즈·저자 3, 소개 1이고 키워드별로 더한다. 값은 평가에서 조정한다.
- 인덱스는 두지 않는다. 작은도서관 규모에서는 순차 탐색으로 충분하다고 보고, 느리면 `pg_trgm`을 검토한다.
- tool 결과의 소개는 200자로 자른다. 전체는 `get_book_detail`이 준다.
- 임베딩 비교를 위해 호출부는 `search_collection` 함수 하나만 본다.

### 4. 답 구조

```python
class Recommendation(ToolInput):
    library_book_id: int
    reason: str = Field(max_length=120)


class LibrarianAnswer(ToolInput):
    message: str = Field(max_length=300)
    recommendations: list[Recommendation] = Field(max_length=5)
    suggest_book_request: bool
```

`repair`는 위반한 id를 빼고 문장을 고정 문구로 바꾼다. LLM의 문장이 뺀 책을 말하고 있을 수 있어서다. 남는 책이 없으면 `None`이고 실행기가 고정 답을 낸다.

### 5. 어린이 요청 판단

`rules.py`의 `is_children_request(user_texts)`가 문장을 순서대로 본다.

| 문장 | 상태 |
| --- | --- |
| 14세 이상 나이, 부모가 읽을 표현 | 어린이 근거로 보지 않음 |
| 어린이 표현, 13세 이하 나이 | 어린이 요청으로 |
| 어른 표현만 있음 | 어린이 요청 해제 |
| 그 밖 | 앞 상태 유지 |

어린이 표현은 정규식으로 쓰고 `아이디어`, `아이돌`, `딸기`, `아들러` 같은 낱말은 뒤 글자로 뺀다. 검사는 이 판단 또는 `tool_names`의 `search_children_books`로 켜진다.

애매하면 어린이 쪽으로 간다. 일반 도서가 어린이에게 가는 쪽이 더 큰 실수이기 때문이다. 대가는 어른 요청이 어린이 도서로 좁혀지는 오판이고, 평가에서 비율을 본다.

- **대안: LLM이 답에 `for_children`을 표시** → 규칙을 LLM 판단에 맡기게 된다. LLM의 신호는 어린이 tool 사용으로만 더하고, 끄는 쪽으로는 쓰지 않는다.

### 6. 대화 흐름

`services/chat.py`의 `stream_turn`이 순서를 맡는다.

1. 기관의 끝난 세션을 지운다. 일일 상한, 세션, 턴 상한을 확인한다.
2. `busy_until`을 원자적으로 잡는다. 이미 잡혀 있고 시간이 안 지났으면 409다.
3. 문장을 가리고 저장한다. 이전 메시지를 `history`로 만든다.
4. `run()`을 돌린다. `StatusEvent`는 그대로 보내고 `AnswerEvent`는 들고 있다.
5. `DoneEvent`에서 카드를 만들고 답 메시지와 노출을 저장한 뒤 `answer`, `done`을 보낸다.
6. `finally`에서 `busy_until`을 푼다. 중단돼도 풀리게 `asyncio.shield`로 감싼다.

확인(1~3)은 응답을 시작하기 전에 끝내서 404, 409, 429를 일반 HTTP 응답으로 돌려준다. 그 뒤로는 SSE다. SSE 도중 예외는 실행기가 고정 답으로 끝내므로 `error` 사건을 따로 두지 않는다.

- 답 메시지에는 코드가 `[추천한 책: #12 공룡 백과]`를 덧붙인다. 다음 턴의 "두 번째 책 알려 줘"에 필요하고, tool 결과를 저장하지 않아도 된다.
- 응답은 `StreamingResponse(media_type="text/event-stream")`이다. 새 의존성을 넣지 않는다.
- 세션 id는 UUID다. 공용 화면에서 번호를 바꿔 넘겨 볼 수 없게 한다.

### 7. 세션 삭제

`purge_expired(session, library_id=None)`가 끝난 세션을 지운다. 메시지는 `CASCADE`다. 서버 `lifespan`의 작업이 1분마다 전체 기관을 지우고, 요청은 그 기관을 먼저 지운다. 여러 프로세스가 돌아도 같은 결과다.

- **대안: 요청 때만 삭제** → 도서관이 문을 닫으면 마지막 대화가 다음 날까지 남는다.
- `agent_runs`는 세션을 가리키지 않아서 세션을 지워도 남고, 남은 기록에 문장이 없다.

### 8. 개인정보 가리기

`mask_personal(session, library_id, text)`이다. 값은 `[개인정보]`로 바꾼다.

- 전화번호, 이메일, 주민번호는 정규식이다. 하이픈 없는 13자리는 ISBN 체크 디지트가 맞으면 두고, 그 외에 주민번호 형태면 가린다.
- 회원번호는 형식이 기관마다 달라서 정규식으로 찾을 수 없다. 문장의 낱말을 그 기관의 `members.member_number`와 맞춰 보고, `회원번호 7788` 같은 표현도 가린다.
- **대안: LLM으로 찾기** → 가리기 전의 값이 LLM에 가게 되어 목적에 어긋난다.

### 9. 테이블

**chat_sessions**: `id`(UUID), `library_id`, `last_active_at`, `busy_until`, `created_at`. `(library_id, id)` 유일.

**chat_messages**: `id`, `library_id`, `session_id`, `role`(`user`, `assistant`), `content`, `created_at`. `(library_id, session_id)` 복합 FK, `CASCADE`.

**recommendation_events**: `id`, `library_id`, `library_book_id`, `run_id`, `position`, `was_available`, `shown_at`. 기관 도서는 복합 FK `CASCADE`, 실행은 복합 FK `RESTRICT`. `(run_id, position)` 유일.

어린이 값을 두지 않는다. 어린이 검사 결과는 `agent_steps`에 있어서 실행 id로 잇는다.

### 10. 상한

`LIBRARIAN_SESSION_IDLE_MINUTES`(5), `LIBRARIAN_MAX_TURNS`(20), `LIBRARIAN_DAILY_RUN_LIMIT`(500). 입력 500자는 스키마, 턴당 호출은 프로필의 `max_llm_calls`다. 일일 수는 `agent_runs`를 프로필 이름과 기관 시간대의 오늘로 센다. 상한 오류는 `core`에 `LimitExceededError`를 더하고 `main.py`가 429로 바꾼다.

### 11. 평가

`evals/librarian/`은 `evals/holdings_import/`와 같은 구조다.

- `fetch_sample.py`: YES24 상품 검색으로 키워드 10개에 10권씩 받아 `evals/librarian/data/yes24_sample.json`에 저장한다. 판매가, 판매 상태, 평점은 저장하지 않는다.
- `catalog.py`: 표본을 테스트 DB의 가상 기관에 넣는다. 공식 서지 연결, 어린이 구분은 실제 분류 값으로 정하고, ISBN 없는 책, 소개 없는 책, 분실만 있는 책, 대출 중인 책은 고정한 규칙으로 상태를 바꿔 만든다.
- `scenarios.py`: 시나리오 12개 안팎. 각 항목에 스펙의 요구사항과 시나리오 이름을 적어 추적한다.
- `__main__.py`: 테스트 DB 트랜잭션 안에서 돌리고 되돌린다. 규칙 검사 표를 내고 위반이 있으면 실패한다.

규칙 검사는 미소장 추천, 어린이 요청의 일반 도서, 이름·연락처를 묻는 문장, 문장 속 미소장 서명, 고정 답 비율이다. 실제 LLM을 쓰므로 돌리기 전에 알린다. 서지는 실제 값이지만 기관과 사본 상태는 가상이므로 수치를 실제 서비스 성능으로 쓰지 않는다. 테스트는 두 층이다.

| 층 | 자료 | LLM | 표본 파일이 없으면 |
| --- | --- | --- | --- |
| 시나리오 테스트 | 테스트 안에서 넣는 작은 자료 | 가짜 | 그대로 돈다 |
| 표본 테스트 (`tests/samples/`, `sample` 표시) | YES24 표본을 테스트 DB에 적재 | 가짜 | 건너뛴다 |

- 스펙 시나리오는 시나리오 테스트가 맡는다. 표본 파일은 저장소에 없어서 깨끗한 checkout에서도 시나리오가 확인돼야 하기 때문이다.
- 표본 테스트는 실제 서지로 검색, 어린이 분류, 카드, 대화 흐름이 맞는지 본다. 예: 키워드 `공룡`이 제목에 공룡이 든 책을 찾는지, 실제 저자 표기의 일부로 찾는지, 실제 분류 값으로 어린이 도서가 정해지는지, 실제 소개가 tool 결과에서 잘리는지.
- 표본 적재는 평가와 같은 `evals/librarian/catalog.py`를 쓴다.
- 표본 테스트의 기대값은 책 하나하나가 아니라 조건으로 쓴다. 표본을 다시 받으면 책이 바뀌기 때문이다.

**표본의 위치**

소장 도서의 ISBN만 조회한다는 규칙의 예외다. 사람이 평가용으로 정한 일회성 표본 100권이고, 다음을 지킨다.

- `.gitignore`에 넣어 저장소에 올리지 않는다. 재배포 금지 조건 때문이다.
- 개발 DB에 넣지 않는다. 평가는 테스트 DB 트랜잭션 안에서 쓰고 되돌린다.
- 서비스 경로에서 쓰지 않는다. 상품 검색 함수는 표본 스크립트만 부른다.
- 표본을 늘리거나 주기적으로 받지 않는다.
- 재현을 위해 키워드와 스크립트는 저장소에 둔다. 다시 받으면 내용이 달라질 수 있다.

- **대안: 베스트셀러 API** → 인기 도서로 쏠리고 CLAUDE.md가 금지한 방식이다. 상품 검색은 평가 주제에 맞게 고를 수 있다.

## Risks / Trade-offs

- [이번 change가 크다] → 순서를 나눠 단계마다 테스트를 통과시킨다. 1주를 넘길 것 같으면 범위를 임의로 줄이지 않고 알린다.
- [어린이 규칙의 오판] → 어른 요청이 어린이로 좁혀질 수 있다. 평가에 오판 시나리오를 넣고 낱말을 고친다.
- [문장 속 서명은 코드가 막지 못한다] → 문장을 300자로 제한하고 프롬프트에서 금지하며, 평가에서 본다.
- [이름은 가릴 수 없다] → LLM 제공자에게 간다. 세션 종료 때 지우고, 화면 주의 문구는 `add-web-ui`에서 넣는다.
- [YES24 소개가 LLM 제공자에게 간다] → 이용 조건을 서비스 전에 확인한다. 기록에는 tool 결과를 남기지 않는다.
- [표본 저장이 이용 조건의 '축적'에 걸릴 수 있다] → 100권으로 제한하고 저장소 밖에 둔다. YES24 확인 항목에 함께 넣는다.
- [다시 받으면 표본이 달라져 점수를 비교할 수 없다] → 받은 날을 파일에 적고, 버전 비교는 같은 파일로 한다.
- [키워드 검색은 기분·상황 요청에 약하다] → 알고 있는 한계다. `add-recommendation-evals`에서 임베딩과 비교한다.
- [`gpt-6-luna`의 추천 품질을 모른다] → 평가에서 `gpt-5.6-terra`와 비교한다.
- [strict 스키마가 `maxLength`, `maxItems`를 받는지 모른다] → 실제 호출 태스크에서 확인한다. 안 되면 스키마에서 빼고 Pydantic 검증만 남긴다.
- [추론 항목 재전송이 아직 실제로 돌지 않았다] → 최종 점검의 여러 tool 대화에서 확인한다.
- [`was_available`은 가져오기 기관에서 마지막 파일 기준이다] → 시각이 카드에 함께 나간다.

## Migration Plan

새 테이블 세 개만 추가한다. 개발 DB를 백업한 뒤 `upgrade` → `downgrade -1` → `upgrade`를 `&&`로 잇는다. 되돌릴 때는 `downgrade -1`이다.
