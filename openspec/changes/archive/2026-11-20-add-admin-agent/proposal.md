## Why

관리자 화면의 운영 에이전트가 아직 없다. 사서 없는 기관의 담당자(주민센터 직원, 자원봉사자)는 "이번 달 대출이 많았던 분야", "아동 과학책이 몇 권인지"를 SQL 없이 알고 싶고, 이 답이 뒤의 보충 구매 요청서 초안(`add-approval-flow`)의 근거가 된다.

처음 설계(`docs/design.md`)는 자연어 SQL(`run_analytics_query`)이었지만, 탐색에서 **정해진 분석 tool**로 바꿨다. 담당자가 실제로 물을 질문 14개가 축 몇 개의 조합으로 모두 풀리고, 숫자를 service가 결정적으로 계산하면 pytest로 정답을 대조할 수 있다(설계 원칙 7). LLM은 어떤 분석인지, 기간, 축만 enum으로 고른다. SQL 생성의 안전장치(읽기 전용 role, view 화이트리스트, sqlglot, 실행 시간 제한)는 이번에 만들지 않는다. 못 하는 질문의 종류를 실행 기록에 남겨, 자연어 SQL을 열지는 그 기록으로 나중에 정한다.

## What Changes

- **분석 service 네 가지와 운영 에이전트 tool**(겉 4개, 속은 필터·묶기 빌더 하나)
  - `get_collection_status`: 장서 사본 수·서명 수. 묶기 없음·분야·입수 구분·상태(+ 기능이 더한 축). 제적 사본은 빼고 따로 센다.
  - `list_holdings_by_status`: 분실·훼손·대출 중 사본 목록(서명, 저자, 등록번호, 청구기호, 마지막 수정 시각).
  - `get_loan_stats`: 기간 대출 건수. 묶기 없음·분야·책(+ 기능이 더한 축). 분야로 묶으면 권수와 권당 대출을 함께 낸다. 항상 지금 대출 중·연체 중 건수를 낸다. 자체 대출 기관 프로필에만 있다.
  - `list_unborrowed_books`: 기간 안에 한 번도 대출되지 않은 서명. 자체 대출 기관 프로필에만 있다.
  - 공통 필터: 분야(KDC 주류 10개 + 분류 없음, 여러 개), 기능이 더한 축의 값.
- **분야는 코드가 정한다**: 공식 서지 KDC → 기관 도서 KDC → 사본 청구기호 앞 세 자리 → 분류 없음. 분류 없음도 결과에 늘 넣어 그룹 합이 전체와 같다.
- **기간은 코드가 계산한다**: 프리셋 7개(이번 달, 지난달, 최근 30일, 최근 90일, 올해, 작년, 최근 365일) 또는 월 숫자(1~12, 미래면 작년). 결과에 계산한 기간을 돌려준다. LLM은 날짜를 쓰지 않는다.
- **출력 한도**: 순위 10권 기본·20권 상한, 목록 20건 기본·50건 상한. 목록과 순위는 전체 수와 잘림 여부를 낸다. 같은 수는 건수 → 서명 가나다순 → id 순으로 고정한다.
- **개인정보**: 분석 결과에 회원 이름·회원번호·회원 id·기증자가 없다. tool마다 출력 필드를 허용 목록으로 고정한다. 이용자 개인에 대한 질문은 못 하는 분석으로 안내하고, 연체한 회원은 기존 연체 목록(`GET /loans?status=overdue`)으로 안내한다.
- **분석 축 훅**: 공통 분석은 "분석 축"(이름, 값, 기본값, 배정 조건)만 알고, 어린이 기능이 어린이·일반 축을 등록한다. 어린이로 배정되지 않은 책은 일반이다. 기능 없이 조립하면 tool 스키마에 그 축이 없다.
- **운영 에이전트 프로필과 대화**: 공통 실행기에 운영 에이전트 프로필(프롬프트, 분석 tool, 최종 답)을 운영 방식별로 조립한다. 관리자만 쓰는 대화 경로(`POST /admin-agent/messages`, SSE)를 둔다. 대화 세션 저장과 가리기는 AI 사서와 같은 구조를 쓰되 세션 종류를 나눈다.
- **못 하는 분석의 기록**: 최종 답에 못 하는 분석의 종류(`unsupported`, enum)를 두고, 실행기가 최종 답에서 기록해도 되는 필드만 실행 행에 남긴다. 질문 문장은 새로 저장하지 않는다.
- **분석 질문 평가**: `evals/admin_agent/`. 손으로 만든 가상 자체 대출 기관과 고정 날짜에서 시나리오 약 20개를 실제 LLM으로 돌린다. 라벨은 기대 tool 호출이고, 지표는 tool 선택, 지어낸 숫자 없음, 못 하는 분석 분류다. LLM 채점은 없다.
- **범위 밖**: 자연어 SQL과 안전장치, 분석 REST API(화면은 `add-web-ui`), 장서 등록 tool(REST로 이미 됨), `draft_*` tool과 승인 흐름·연체 목록 tool·연체 안내문(`add-approval-flow`), 회원 연락처, 임의 날짜 범위·"작년 9월"·KDC 강목, 최근 들어온 책(입수일 없음), 외부 대출 기관의 세부 안내.

## Capabilities

### New Capabilities

- `library/collection-analytics`: 장서·대출 분석 service와 그 tool의 계약. 분야 결정, 기간 계산, 제적 처리, 출력 한도, 분석 축, 출력 허용 목록, 기관 분리
- `agent/admin`: 운영 에이전트. 관리자 대화 요청, 운영 방식별 프로필, 최종 답과 못 하는 분석, 분석 질문에 답하는 에이전트 동작(평가)
- `platform/admin-agent-evals`: 분석 질문 평가의 데이터, 시나리오 라벨, 지표, 실행 방식

### Modified Capabilities

- `agent/runner`: 최종 답 tool이 기록해도 되는 필드를 골라 실행 기록에 남김
- `agent/chat-sessions`: 세션 종류(AI 사서·운영 에이전트) 분리, 종류별 만료 시간과 일일 실행 상한
- `features/children`: 어린이·일반 분석 축 등록과 운영 에이전트 프롬프트 문구

## Impact

- 코드: 새 `app/library/analytics/`(필터·묶기 빌더, 분야 결정, 기간, 축 등록), 새 `app/library/services/analytics.py`, 새 `app/library/admin_agent.py`(프로필, 프롬프트, 최종 답), `app/library/tools.py` 또는 새 `app/library/analytics_tools.py`(분석 tool 4개), 새 `app/library/api/admin_agent.py`, `app/library/services/chat.py`(세션 종류, 답 모양 일반화), `app/agent/tools.py`·`app/agent/runner.py`·`app/agent/records.py`(최종 답 기록 필드), `app/features/children/`(축 등록, 운영 에이전트 확장), `app/main.py`(조립), `app/core/config.py`(운영 에이전트 세션 만료·일일 상한)
- DB: 마이그레이션 하나. `chat_sessions`에 세션 종류, `agent_runs`에 최종 답 기록(JSONB). 분석 쿼리를 위한 인덱스는 측정 뒤 필요할 때만.
- API: 새 `POST /admin-agent/messages`, `DELETE /admin-agent/sessions/{id}`(관리자만). 기존 AI 사서 경로는 그대로이고, 종류가 다른 세션 id는 404다.
- 외부 호출: 없음. 임베딩 서버도 쓰지 않는다.
- LLM: 평가 실행만. 호출 수와 비용을 알리고 승인을 받은 뒤 한다.
- 문서: `docs/design.md`(운영 에이전트 tool 표, 자연어 SQL 보류), `docs/roadmap.md`(20번 줄, 미룬 일), `docs/glossary.md`(분야, 분석 축), `app/library/README.md`, `app/features/README.md`, `evals/admin_agent/README.md`, `CLAUDE.md`(현재 단계, 명령)
