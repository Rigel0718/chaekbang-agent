# Proposal

## Why

AI 사서와 운영 에이전트는 tool 호출 루프, 기관 범위 주입, 최종 답 검사, 실행 기록이 같다. 에이전트마다 만들면 규칙을 지키는 코드가 흩어진다. 공통 실행기를 먼저 만들어 AI 사서는 프롬프트와 tool 묶음만 끼우게 한다. AI 사서까지 한 change로 하면 1주를 넘어서 실행기를 먼저 나눈다.

## What Changes

- **공통 실행기 `app/agent/`**: tool 호출 루프를 돌리고 진행 사건을 내보낸다. 어떤 tool이 있는지 모르고 `core`만 의존한다.
- **tool 계약**: 이름, 설명, 입력 스키마, 실행 함수로 정의하고 같은 프로세스에서 실행한다. 입력은 검증하고, 기관은 실행기가 주입한다.
- **프로필**: 프롬프트, tool 묶음, 최종 답 tool, 최종 검사, 한도를 묶는다.
- **최종 검사 자리**: 최종 답을 내보내기 전에 프로필의 검사를 모두 돌린다. 위반이면 LLM에 돌려주고, 횟수를 넘으면 위반 항목을 뺀 답이나 고정 답을 낸다.
- **LLM 접점**: 실행기는 접점만 알고 OpenAI 어댑터가 이를 구현한다. 기본 모델은 `gpt-6-luna`이고, 키와 모델은 `.env`에서 읽는다.
- **모델 가격표**: 모델별 토큰 가격을 설정에 두어 나중에 비용을 비교할 때 참고한다.
- **실행 기록**: `agent_runs`, `agent_steps`. 이용자 문장, 모델 응답, tool 결과 원문은 저장하지 않는다.
- **의존 방향**: `app/agent`를 층 검사에 넣고 import뿐 아니라 동작으로도 확인한다.

**범위 밖 (이번 change에서 하지 않음)**

- AI 사서 프로필, 실제 tool, 어린이 검사, 대화 API와 SSE, 대화 기록, 추천 노출 기록 → `add-librarian-agent`
- 승인 대기와 재개 → `add-approval-flow`
- 쓰기 tool과 기관 운영 방식에 따른 tool 끄기 → `add-librarian-actions`
- MCP 어댑터, Langfuse 연동
- 실행 기록 조회 API

## Capabilities

### New Capabilities

- `agent/runner`: tool 계약, 프로필, 호출 루프, 최종 검사, 한도와 오류 처리, 진행 사건, 실행 기록, LLM 접점

### Modified Capabilities

- `platform/package-layers`: 의존 방향에 `app/agent`를 추가
- `platform/database-schema`: 테이블 12개로 늘고, 실행 단계는 같은 기관의 실행만 가리킴

## Impact

- **코드**: `app/agent/` 새 패키지, `app/models.py`, `app/core/config.py`, `tests/agent/`, `tests/platform/`
- **DB**: `agent_runs`, `agent_steps` 추가. 기존 테이블은 바뀌지 않는다
- **의존성**: `openai`
- **설정**: `.env`와 `.env.example`에 `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_EFFORT`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`
- **API**: 바뀌지 않는다. 이번 change에는 HTTP 진입점이 없다
