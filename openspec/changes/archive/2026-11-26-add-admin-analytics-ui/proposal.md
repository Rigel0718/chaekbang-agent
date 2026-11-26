## Why

관리자 화면의 운영 대화는 답 문장만 보인다. 분야별 장서·대출, 많이 빌린 책, 분실 사본 같은 분석 결과를 글로만 읽어야 하고, 운영 에이전트가 만든 초안은 [승인 목록] 탭에서 다시 찾아야 한다. 공통 실행기가 진행 문구·답·끝 사건만 내보내고 tool 결과와 초안 id는 LLM에게만 가기 때문이다. 24b를 둘로 나눈 뒤쪽이다(앞쪽 24f `add-admin-import-ui`는 2026-11-25에 끝남, 탐색 2026-11-26).

## What Changes

- 공통 실행기: tool이 화면용 변환 함수(`present`)를 고를 수 있다. 실행기는 성공한 tool의 변환 값을 모았다가, 검사를 통과한 답이나 정리한 답으로 끝날 때만 답 바로 앞에 호출 순서대로 결과 사건으로 낸다. 고정 답·실패·중단이면 내지 않고, 실행 기록에 남기지 않는다. 실행기는 tool 이름과 값의 뜻을 모른다.
- 운영 에이전트 SSE에 `result` 사건을 더한다(`session` → `status`… → `result`… → `answer` → `done`). 결과 모양은 새로 만드는 화면용 모델 둘이다: 표(`TableResult`)와 초안 링크(`DraftLink`).
- 결과를 내는 tool: 장서 현황·대출 통계(묶었을 때만 표, 그룹 표는 막대 열), 상태별 사본, 안 빌린 책, 큐레이션·연체 안내문 틀·구매 요청서 초안(종류와 id). 지금 있는 분석 결과 모델은 바꾸지 않는다.
- 관리자 화면 운영 대화: 답 말풍선 아래에 표와 막대를 보이고, 초안에는 [초안 보기] 버튼을 둔다. 누르면 [승인 목록] 탭에서 그 초안이 펼쳐진다.
- 운영 평가 36개 전체 회귀(`add-purchase-request`에서 미룬 일). 프롬프트는 v4 그대로다.

하지 않는 것: 분석 REST, 연체 목록·구매 후보·검색 결과 표, 표 정렬·접기·CSV, 원형·선 차트, 주소에 초안 id를 넣는 링크, 프롬프트 다듬기(v5), 대화 기록에 표 남기기, Playwright, 장서 관리·회원 탭(`add-admin-collection-ui`).

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `agent/runner`: 진행 사건 요구사항에 결과 사건을 더하고(tool이 고른 화면용 값만, 통과한 답과 함께만), tool의 화면용 변환 요구사항을 더한다.
- `agent/admin`: SSE 사건 순서에 `result`를 더하고, 결과 사건의 모양과 tool별 결과, 결과 사건의 개인정보·기관 분리 요구사항을 더한다.
- `platform/web-ui`: 운영 대화 화면이 답 아래 표·막대를 보이고, [초안 보기]로 승인 목록의 초안을 펼친다.

## Impact

- 실행기: `app/agent/tools.py`(`present` 칸), `app/agent/runner.py`(`ResultEvent`, 모으기), `app/agent/README.md`
- 운영 에이전트: `app/library/schemas/admin_results.py`(새 모듈: `TableResult`, `DraftLink`), `analytics_tools.py`·`curation_tools.py`·`overdue_tools.py`·`purchase_tools.py`(변환 함수), `services/admin_chat.py`(`result` 사건), `app/library/README.md`
- 화면: `app/web/public/admin/chat.js`, `approvals.js`, `main.js`, `admin.css`, `app/web/README.md`
- 테스트: `tests/agent/test_runner.py`, `tests/library/`(변환 함수, 개인정보, 대화 사건), `tests/platform/test_web_ui.py`
- 평가: `evals/admin_agent` 실행만(코드 변경은 새 사건을 받아도 깨지지 않는지 확인 정도). LLM 약 80~110회
- DB 스키마, 의존성, 외부 API 변경 없음
