# Design

## Context

- 에이전트 코드는 아직 없고 LLM 의존성도 없다. `.env`에 LLM 키가 없다.
- `app/central/enrichment.py`는 외부 호출 전에 트랜잭션을 끝내고, 접점(`EnrichmentTargets`)을 실행하는 쪽이 넘겨준다. 실행기도 같은 방식을 따른다.
- 테스트 세션은 연결 단위 트랜잭션 안의 savepoint이고 `get_session`을 바꿔 끼운다. 실행기가 세션을 직접 만들면 이 구조를 벗어난다.
- 기관 데이터 테이블은 NOT NULL `library_id`와 복합 외래 키로 기관을 넘는 참조를 막는다. `tests/platform/test_database_schema.py`가 테이블 목록을 고정해서 함께 고친다.
- 기본 모델 `gpt-6-luna`는 추론 모델이다. tool 호출 사이에 추론 항목을 함께 돌려줘야 하고, 추론과 출력을 합쳐 `max_output_tokens`를 넘으면 답이 나오기 전에 끊길 수 있다.
- `gpt-5-mini`는 2026-12-11에 제거되므로 쓰지 않는다. `gpt-6-luna`는 제거 예정이 없고 Responses API와 tool 호출을 지원한다 (2026-11-07 확인).

## Goals / Non-Goals

**Goals:**
- AI 사서와 운영 에이전트가 프로필만 바꿔 같은 실행기를 쓴다.
- 기관 범위, 입력 검증, 최종 검사, 한도를 LLM이 아니라 코드가 지킨다.
- LLM 없이 가짜 접점으로 모든 시나리오를 테스트한다.

**Non-Goals:**
- 승인 대기와 재개. 상태 값과 단계 기록이 나중에 늘어날 수 있으면 충분하고, 이번에 자리를 미리 만들지 않는다.
- 토큰 단위 스트리밍. 최종 답은 검사 뒤에 한 번에 나간다.
- 대화 저장. 이전 대화는 부르는 쪽이 넘긴다.
- 여러 제공자 구현. 접점만 두고 어댑터는 OpenAI 하나다.

## Decisions

### 1. 패키지 구성

```
app/agent/
├── tools.py       # Tool, ToolContext
├── profile.py     # Profile, FinalCheck, Violation
├── llm.py         # LlmClient 접점, 중립 메시지와 응답 형식
├── openai_client.py  # OpenAI 어댑터
├── runner.py      # 호출 루프, 사건
├── records.py     # 기록 쓰기, 기관 범위 조회
├── models.py      # AgentRun, AgentStep
└── README.md
```

`core`만 import한다. `central`, `library`, `features`는 `Tool`을 쓰려고 `app.agent`를 import할 수 있다. 의존 방향은 `features → library → central → agent → core`가 아니라, `agent`가 `core` 바로 위에 있고 세 층이 각각 아래를 보는 모양이다.

- **대안: `Tool` 타입을 `app/core`에 두고 세 층이 `agent`를 모르게 하기** → 대화 API 라우터가 어차피 실행기를 불러야 해서 `library → agent`가 필요하다. 타입만 `core`로 옮기면 경계만 복잡해진다.
- `agent_runs.library_id`는 문자열 `ForeignKey("libraries.id")`로 잇는다. `app.library`를 import하지 않고, 어린이 기능의 모델과 같은 방식이다.

### 2. tool 입력은 Pydantic 모델

`Tool`은 `name`, `description`, `input_model`, `handler`, `status_label`, `record_fields`를 갖는다. JSON Schema는 `input_model.model_json_schema()`로 만들고, `input_model`은 `extra="forbid"`다.

- 검증과 스키마가 한 정의에서 나와 어긋나지 않고 새 의존성이 없다. `library_id`를 입력에 넣으면 정의되지 않은 값으로 거부된다.
- MCP 어댑터가 필요해지면 이름, 설명, JSON Schema를 그대로 내보낸다.
- **대안: 손으로 쓴 JSON Schema + `jsonschema`** → 의존성이 늘고 handler의 타입이 사라진다.

`handler(ctx: ToolContext, input) -> str | dict`이고 `ToolContext`에 `library_id`, `session`이 있다.

### 3. 최종 답은 tool로 받는다

프로필의 `answer_tool`이 최종 답이다. 입력 모델이 곧 답의 구조이고, 검사와 사건이 이 값을 쓴다.

- 글로 끝나면 코드가 볼 구조가 없어서 검사할 수 없다.
- 어댑터는 `tool_choice: "required"`로 tool 호출을 요구한다. 강제가 안 되는 제공자도 있으므로 호출 여부는 실행기도 확인한다. 글로 끝나면 한 번 다시 요청하고, 그다음은 고정 답이다.
- **대안: 구조화 출력** → tool과 섞는 방식이 제공자마다 다르다. tool 호출은 어느 제공자에나 있고 가짜 접점도 단순하다.

### 4. 최종 검사와 훅의 차이

`FinalCheck`는 `name`과 `check(ctx: CheckContext, answer) -> list[Violation]`을 갖는다. `Violation`은 `message`와 `items`다. `CheckContext`는 `library_id`, `session`, 이번 실행까지의 `user_texts`, 호출한 `tool_names`다.

| | 훅 | 최종 검사 |
| --- | --- | --- |
| 역할 | 사건을 알림 | 판정해서 막음 |
| 반환 | 없음 | 위반 목록 |
| 범위 | 앱 전체 service | 그 프로필의 실행 |
| 등록 | `register_hook` | 프로필 조립 |

재시도 한도를 넘으면 `Profile.repair(answer, violations)`로 위반 항목을 빼고 다시 검사한다. 통과하지 못하면 `fallback_answer`다. 실패 쪽을 늘 "덜 내보내는" 방향으로 둔다. 실행기는 답의 안쪽 구조를 모르므로 항목을 빼는 일은 프로필이 맡는다.

### 5. 진행 사건은 비동기 생성기

`run(...)`은 `AsyncIterator[RunEvent]`다. 사건은 `status`, `answer`, `done`이다. SSE 변환은 `add-librarian-agent`의 라우터가 한다.

- 소비자가 멈추면 생성기가 닫히거나 태스크가 취소된다. `finally`에서 상태를 `cancelled`로 저장하고, 취소 중에도 저장되게 `asyncio.shield`로 감싼다.
- 답은 검사 뒤에 나간다. 토큰을 먼저 흘리면 검사 전의 답이 보이기 때문이다.

### 6. 세션은 부르는 쪽이 넘긴다

`run`은 `AsyncSession`을 받는다. 라우터는 `get_session`의 세션을, evals는 자기 세션을 넘긴다.

- 단계를 기록할 때마다 커밋해서 LLM 호출 전에 트랜잭션을 끝낸다. 중간에 죽어도 기록이 남고 연결을 잡고 있지 않는다.
- tool과 검사는 이 세션 하나로 순서대로 실행한다. `AsyncSession`은 동시에 쓸 수 없고, 조회 위주라 병렬 실행의 이득이 작다.
- tool에서 예외가 나면 롤백한 뒤 기록한다.

### 7. LLM 접점과 OpenAI 어댑터

```python
class LlmClient(Protocol):
    model: str

    async def complete(self, *, system, tools, messages) -> LlmTurn: ...
```

`LlmTurn`은 `tool_calls`, `text`, `stop`(`end`, `tool_use`, `refused`, `truncated`), `usage`, `raw`다. `raw`는 어댑터만 아는 응답 항목이고 실행기는 다음 호출에 그대로 넣는다.

어댑터의 호출 방식:
- `AsyncOpenAI`의 Responses API를 쓴다. 답을 검사 뒤에 내보내므로 스트리밍하지 않는다.
- `store=False`로 부른다. 이용자 대화를 제공자 쪽 응답 저장소에 남기지 않기 위해서다. 그래서 `previous_response_id`를 쓰지 않고, 응답의 `output` 항목(추론, tool 호출)과 tool 결과를 다음 `input`에 그대로 이어 보낸다.
- `tool_choice`는 `required`, tool에 `strict: true`다. strict는 모든 필드를 `required`로 요구하므로 tool 입력 모델은 기본값 없이 쓰고, 값이 없어도 되는 필드는 `T | None`으로 둔다.
- `reasoning.effort`는 `LLM_EFFORT`(기본 `low`). 모델 기본값은 `medium`이지만 긴 추론보다 응답 시간이 중요한 대화다. `temperature`는 보내지 않는다.
- `max_output_tokens`는 `LLM_MAX_TOKENS`(기본 25000)다. 문서가 추론과 출력에 최소 2만 5천 토큰을 남기라고 권한다.
- 프롬프트 캐시는 앞부분이 같아야 맞으므로 시스템 프롬프트와 tool 정의를 프로필에서 고정한다. 이 모델은 캐시 쓰기가 입력 가격의 1.25배라, 켜는 방식과 실제 이득은 구현 때 사용량으로 확인한다.
- `status`가 `incomplete`이고 이유가 `max_output_tokens`면 `truncated`, `content_filter`면 `refused`다. 응답의 거절 항목도 `refused`로 바꾼다. 거절 항목의 모양은 문서에 없어서 SDK 타입으로 확인한다.
- SDK 재시도를 쓰고 실행기에서 다시 재시도하지 않는다. 타입별 오류는 `LlmError`로 바꿔 올린다.
- **대안: Chat Completions** → 공식 문서의 tool 호출과 추론 항목 전달 안내가 Responses API 기준이다.

`LLM_MODEL` 기본값은 `gpt-6-luna`다. 운영 모델은 `add-recommendation-evals`의 점수로 정한다.

키가 없으면 어댑터를 호출할 때 `LlmError`다. 서버는 시작한다.

**가격표**는 `app/core/config.py`의 `LLM_PRICES`다. 모델 이름별로 입력, 캐시 입력, 출력의 1M 토큰당 USD와 확인한 날, 제거 예정일을 둔다. 금액은 `Decimal`이다. 비용을 저장하지 않고 토큰 수만 기록해서, 가격이 바뀌어도 기록이 틀어지지 않는다. 캐시 입력과 캐시 쓰기는 가격이 달라서 토큰 수를 따로 기록한다. 캐시 쓰기는 보관 시간별로 가격이 다르지만 합계만 둔다.

### 8. 턴 사이 대화

`run`의 `history`는 이전 턴의 이용자 문장과 최종 답 글만 담는다. 한 실행 안의 응답 블록은 메모리에만 두고 그대로 재전송한다.

- 턴 사이에 추론 항목을 보내지 않으므로 저장할 내용이 작고 제공자 형식에 묶이지 않는다. tool 결과도 대화 저장소로 가지 않는다.
- **대안: 턴 사이에도 전체 블록 저장** → 소개 문구와 추론 항목이 DB에 쌓이고 제공자 형식에 묶인다.

### 9. 기록 테이블

**agent_runs**

| 열 | 타입 | 설명 |
| --- | --- | --- |
| id | PK | |
| library_id | FK, NOT NULL | |
| profile | String(50) | 프로필 이름 |
| profile_version | String(50) | 프롬프트 비교용 |
| model | String(100) | |
| status | enum | `running`, `completed`, `repaired`, `fallback`, `refused`, `failed`, `cancelled` |
| input_tokens, cached_input_tokens, cache_write_tokens, output_tokens | Integer | 합계. 입력은 캐시 입력을 포함한다 |
| started_at, finished_at | DateTime(tz) | |

**agent_steps**

| 열 | 타입 | 설명 |
| --- | --- | --- |
| library_id, run_id | 복합 FK | 같은 기관의 실행 |
| seq | Integer | PK는 (library_id, run_id, seq) |
| kind | enum | `llm`, `tool`, `check` |
| name | String(100)? | tool 또는 검사 이름 |
| is_error | Boolean | |
| duration_ms | Integer | |
| detail | JSONB? | 고른 입력 값, 위반 항목. 글은 넣지 않는다 |

`Violation.message`는 LLM에만 돌려주고 저장하지 않는다. `detail`에는 `items`만 둔다.

### 10. 의존 방향 검사

`tests/platform/test_package_layers.py`의 `FORBIDDEN`에 `agent`를 넣고 `core`의 금지 목록에 `app.agent`를 더한다. import 검사는 지연 import나 간접 import를 놓칠 수 있으므로, 새 프로세스에서 `app.agent.runner`만 불러 `sys.modules`를 확인한다. `app/agent`의 테스트는 가짜 tool과 가짜 LLM만 쓴다.

## Risks / Trade-offs

- [답을 검사 뒤에 내보내서 첫 글자가 늦다] → 진행 문구를 먼저 보낸다. 대화는 짧고 `LLM_EFFORT`를 낮게 둔다.
- [LLM이 최종 답 tool을 자주 안 쓰면 고정 답이 많아진다] → 한 번 다시 요청하고, 실행 상태로 비율을 볼 수 있다.
- [실행기가 나중의 승인 흐름에 맞지 않을 수 있다] → 실제 소비자는 다음 change의 AI 사서다. 승인은 그때 요구사항으로 넓힌다.
- [AI 사서 없이 만든 접점이 쓰기 불편할 수 있다] → `add-librarian-agent` 제안에서 어긋나면 delta를 먼저 고친다.
- [`gpt-6-luna`는 가장 싼 등급이라 추천 품질이 낮을 수 있다] → 운영 모델은 평가 점수와 비용으로 정한다. 비교용으로 가격표에 `gpt-5.6-terra`, `gpt-5-mini`도 남긴다.
- [기록 저장이 커밋을 늘린다] → 턴당 단계가 10개 안팎이라 무시할 수 있다.

## Migration Plan

새 테이블 두 개만 추가한다. 개발 DB를 백업한 뒤 `upgrade` → `downgrade -1` → `upgrade`를 `&&`로 잇는다. 되돌릴 때는 `downgrade -1`이다.
