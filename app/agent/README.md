# agent

공통 실행기다. AI 사서와 운영 에이전트가 같은 실행기를 쓰고, 프로필만 바꿔 끼운다.

## 맡는 일

- tool 호출 루프와 입력 검증
- 기관 범위 주입. LLM은 기관을 정할 수 없다
- 최종 답 검사와 재시도, 위반 항목 정리, 고정 답
- 한도와 오류 처리, 진행 사건
- 실행 기록(`agent_runs`, `agent_steps`)

## 구성

| 파일 | 내용 |
| --- | --- |
| `tools.py` | `Tool`, `AnswerTool`, `ToolInput`, `ToolContext` |
| `profile.py` | `Profile`, `FinalCheck`, `Violation`, `CheckContext` |
| `llm.py` | LLM 접점과 중립 메시지 형식 |
| `openai_client.py` | OpenAI Responses API 어댑터 |
| `runner.py` | `run()`: 호출 루프, 사건 |
| `records.py` | 기록 쓰기, 기관 범위 조회 |
| `models.py` | `AgentRun`, `AgentStep`, 상태 값 |

## 규칙

- `app/core`만 import한다. `central`, `library`, `features`는 이 패키지를 import할 수 있고 반대는 안 된다. `tests/platform/test_package_layers.py`가 막는다.
- 어떤 tool이 있는지 모른다. tool은 패키지별 `tools.py`가 내놓고 프로필은 `app/main.py`에서 조립한다.
- 답은 검사를 통과한 뒤에만 사건으로 나간다. 토큰을 먼저 흘리지 않는다.
- 이용자 문장, 모델이 쓴 글, tool 결과 원문을 기록하지 않는다. tool 입력은 `record_fields`로 고른 값만 남긴다. 회원번호 같은 값은 고르지 않는다.
- LLM 호출 동안 트랜잭션을 잡지 않는다. 단계 기록이 커밋해서 끝낸다.
- 세션은 부르는 쪽이 넘긴다. tool과 검사는 그 세션 하나로 순서대로 돈다.
- `run()`의 `history`에는 이전 이용자 문장과 답 외에 코드의 안내(`Instruction`)를 넣을 수 있다. 안내는 LLM에 developer 메시지로 가고, 검사가 받는 이용자 문장(`user_texts`)에는 들어가지 않는다.
- 실패는 덜 내보내는 쪽으로 간다. 검사가 죽으면 답은 나가지 않고 고정 답이 나간다.

## 새 tool 추가

1. 입력 모델을 `ToolInput`으로 만든다. 필드에 기본값을 쓰지 않고, 없어도 되는 값은 `T | None`으로 둔다. `library_id`를 넣지 않는다.
2. 패키지의 `tools.py`에 `Tool`을 정의하고 `ctx.library_id`, `ctx.session`으로 service를 부른다.
3. service의 도메인 오류는 그대로 올린다. LLM이 메시지를 받는다.
4. 프로필의 `tools`에 넣는다.

## 새 프로필 추가

`Profile`을 만든다. 최종 답은 `AnswerTool`이고, `fallback_answer`는 검사를 거치지 않으므로 책을 넣지 않는다. 검사가 있으면 `final_checks`에, 위반 항목을 뺄 수 있으면 `repair`에 넣는다.

```python
llm = OpenAiClient()
async for event in run(
    session=session, llm=llm, profile=profile, library_id=staff.library_id, user_text=text
):
    ...
```

## 모델

기본 모델은 `LLM_MODEL`(`gpt-6-luna`)이고 키는 `.env`의 `OPENAI_API_KEY`에서만 읽는다. 모델별 토큰 가격은 `app/core/config.py`의 `LLM_PRICES`에 있다. 비용은 저장하지 않고 토큰 수만 기록한다.
