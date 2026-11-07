# Tasks

## 1. 설정과 뼈대

- [x] 1.1 `uv add openai`을 실행하고 `uv run pytest`가 그대로 통과하는지 확인한다
- [x] 1.2 `app/core/config.py`에 LLM 설정과 모델 가격표를 추가하고 `.env.example`을 고친다. [agent/runner] 키 없이 서버 시작, 모델 가격표 시나리오를 통과시킨다
- [x] 1.3 `tests/agent/`에 가짜 LLM(`FakeLlm`: 정해 둔 응답을 차례로 돌려주고 받은 요청을 남긴다)과 가짜 tool을 만든다

## 2. 기록

- [x] 2.1 `app/agent/models.py`와 리비전을 작성하고 `app/models.py`의 `TENANT_TABLES`에 넣는다. 개발 DB를 백업한 뒤 `&&`로 이어 `upgrade` → `downgrade -1` → `upgrade`와 `alembic check`가 통과하는지 확인한다
- [x] 2.2 `tests/platform/test_database_schema.py`를 12개 테이블로 고치고 [platform/database-schema] 시나리오 전부를 통과시킨다
- [x] 2.3 `app/agent/records.py`를 작성하고 [agent/runner] 기록의 기관 범위를 통과시킨다

## 3. 실행기

- [x] 3.1 `tools.py`, `profile.py`, `llm.py`를 작성하고 [agent/runner] tool 정의, 프로필의 tool만 실행, 입력 검증, 기관 범위 주입 시나리오를 통과시킨다
- [x] 3.2 `runner.py`의 루프를 작성하고 호출 루프, 최종 답 tool, 실행 한도, 진행 사건, 실행 안 대화 유지 시나리오를 통과시킨다
- [x] 3.3 최종 검사와 재시도 초과를 작성하고 최종 검사, 검사 재시도 초과 시나리오를 통과시킨다
- [x] 3.4 오류와 중단을 작성하고 tool 오류 처리, LLM 오류 처리, 중단 시나리오를 통과시킨다
- [x] 3.5 기록을 잇고 실행 기록, 기록의 개인정보, 외부 호출 중 트랜잭션 없음 시나리오를 통과시킨다. 진행 중 기록은 savepoint 세션 대신 실제 커밋이 되는 세션으로 확인하고 테스트 행을 지운다

## 4. OpenAI 어댑터

- [x] 4.1 `app/agent/openai_client.py`를 작성한다. 네트워크 없이 가짜 SDK 클라이언트로 요청 값(`store=False`, `tool_choice`, `strict`, `reasoning.effort`, `max_output_tokens`), 응답 변환, 거절·잘림·오류 변환을 테스트하고 [agent/runner] 키 없이 실행, 모델 설정 적용, 제공자 저장 없음을 통과시킨다
- [x] 4.2 키가 `.env`에 들어온 뒤 사람이 승인하면 가짜 tool 하나로 실제 호출을 한 번 돌려 왕복을 확인한다. 쓴 모델과 토큰 수를 알린다. 키가 없으면 이 태스크를 남기고 알린다

## 5. 경계

- [x] 5.1 `tests/platform/test_package_layers.py`에 [platform/package-layers] 거꾸로 된 import 금지, 실행기의 import 제한, 실행기만 불러오기, 가짜 tool로 실행을 작성해 통과시킨다
- [x] 5.2 `app/agent/`에 `app.library` import를 일부러 넣고 5.1이 실패하는지 확인한 뒤 되돌린다. 최종 검사 호출을 일부러 빼고 3.3의 시나리오가 실패하는지도 확인한 뒤 되돌린다

## 6. 문서

- [x] 6.1 `app/agent/README.md`에 역할, 구성, 규칙, 새 tool·프로필 추가 방법을 쓰고 `README.md`의 현재 단계와 설정을 고친다. 적은 명령이 실행되는지 확인한다

## 7. 최종 점검

- [x] 7.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `alembic check`가 모두 통과하는지 확인하고, 이번 change의 모든 delta 시나리오가 최소 한 테스트의 docstring에 연결돼 있는지 스크립트로 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive한다.
- 다음 change `add-librarian-agent`로 넘어간다. 앞서 정한 내용은 `docs/design.md`의 AI 사서 절을 따른다.
