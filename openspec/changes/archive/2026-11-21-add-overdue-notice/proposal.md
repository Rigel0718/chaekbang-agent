## Why

자체 대출 기관의 담당자는 연체를 알아도 누구에게 무슨 말로 연락할지 매번 손으로 정리해야 한다. 운영 에이전트는 연체 건수(`get_loan_stats`의 `current.overdue`)만 알려 주고, 연체 안내는 설계 원칙 3의 확정 작업인데 아직 없다. `add-approval-flow`가 만든 공통 승인 틀의 확정하는 종류(`CONFIRMING`)를 쓰는 첫 기능이다.

담당자가 매번 승인을 누르지 않게, 승인은 회원에게 나갈 **문장(안내문 틀)에 한 번만** 받고, 연체 안내 목록은 그 틀과 지금의 연체 대출로 코드가 그때그때 만든다. LLM은 자리표시가 있는 틀만 쓰고 회원 값은 보지 않는다. 실제 문자·메일 발송은 하지 않는다. 담당자가 목록을 보고 직접 연락할 수 있게 회원에 전화번호(선택)를 둔다.

## What Changes

- **회원 전화번호**: 회원에 선택 입력 전화번호를 더한다. 숫자만 저장하고(하이픈·공백 제거, `0`으로 시작하는 9~11자리), 관리자 회원 API와 연체 안내 목록에서만 쓴다. 회원 검색어로는 찾지 않는다. 회원을 지우면 함께 사라지고 다른 곳에 복사하지 않는다. 회원 스펙의 "회원번호와 이름만"을 바꾼다.
- **안내문 틀**: 기관별 연체 안내문 틀(문장 하나, 300자 이내). 자리표시는 `{이름}`, `{서명}`, `{반납예정일}`, `{연체일수}`, `{도서관}`의 다섯 개이고 `{서명}`과 `{반납예정일}`은 반드시 들어간다. 모르는 자리표시나 전화번호·이메일·주민등록번호·그 기관 회원번호 형태가 든 틀은 저장하지 않는다.
  - 승인 틀의 `CONFIRMING`을 따른다: 만들기·고치기·삭제(`draft`만), 제출, 승인(→ `confirmed`), 반려. 내리기는 없다. 확정된 틀 중 가장 최근에 확정된 것이 그 기관이 쓰는 틀이다.
  - 관리자 REST: 목록·상세·만들기·고치기·삭제·제출·승인·반려.
- **연체 안내 목록**: `GET /overdue-notices/today`(관리자). 지금의 연체 대출마다 한 줄로 회원번호, 이름, 전화번호, 서명, 등록번호, 반납 예정일, 연체 일수, 쓰는 틀을 채운 문안을 돌려준다. 승인 없이 요청할 때마다 계산하고 저장하지 않는다. 확정된 틀이 없으면 409.
- **운영 에이전트 v3**: `list_overdue_loans`(연체 대출의 서명, 등록번호, 반납 예정일, 연체 일수와 전체 수. 회원 값 없음)와 `draft_overdue_notice`(틀을 만들어 바로 승인 대기로 올림. 실행 기록에 입력을 남기지 않음)를 자체 대출 기관 프로필에 더한다. "누가 연체했어?"는 계속 `patron_info`이고 연체 안내 목록을 안내한다.
- **외부 대출 기관**: 두 tool을 넣지 않고, 안내문 틀과 연체 안내 목록 REST는 모두 409와 안내 메시지다.
- **평가**: `evals/admin_agent`에 연체 시나리오 4개(목록, 틀 초안, 이름을 말한 틀 초안, 외부 대출 기관)와 초안 충실도의 연체 안내 판정.
- **범위 밖**: 실제 발송과 수신 동의, 안내 이력·연락함 표시, 회원별로 묶은 문안, CSV 내려받기, 관리자 화면(`add-web-ui`), 외부 대출 기관의 연체 파일 가져오기, 휴관일을 뺀 연체 일수.

## Capabilities

### New Capabilities

- `library/overdue-notices`: 안내문 틀의 내용 규칙과 승인(확정), 쓰는 틀, 연체 안내 목록의 값과 순서, 기관 분리, 외부 대출 기관 차단

### Modified Capabilities

- `circulation/members`: 회원 최소 정보에 선택 전화번호를 더하고 형식·쓰는 곳을 정함
- `agent/admin`: 자체 대출 기관 프로필의 tool에 연체 목록과 안내문 틀 초안을 더함, 두 tool의 계약(회원 값 없음, 기록 없음), 연체 안내 요청에 답하는 동작과 "누가 연체했어?"의 안내(평가)
- `platform/admin-agent-evals`: 연체 안내 시나리오의 라벨과 초안 충실도 판정
- `platform/database-schema`: 테이블 24개에서 25개(`overdue_notice_templates`)로

## Impact

- 코드: `app/library/models/circulation.py`(회원 전화번호), `schemas`·`services/members.py`, 새 `app/library/models/overdue_notice.py`, 새 `services/overdue_notices.py`, 새 `schemas/overdue_notice.py`, 새 `api/overdue_notices.py`, 새 `app/library/overdue_tools.py`, `app/library/admin_agent.py`(v3, 프롬프트), `app/main.py`, `app/models.py`(`TENANT_TABLES`)
- DB: 마이그레이션 하나. `members.phone`, `overdue_notice_templates`
- API: 회원 요청·응답에 `phone`, 새 `/overdue-notice-templates` 경로들, 새 `GET /overdue-notices/today`
- 외부 호출: 없음
- LLM: 평가 실행만(운영 평가 전체 회귀 약 110~130회). 호출 수를 알리고 승인을 받은 뒤 한다
- 문서: `docs/design.md`(tool 표, 승인 흐름의 연체 안내 문장, 테이블 목록), `docs/roadmap.md`(22b 상태, 미룬 일), `CLAUDE.md`(현재 단계), `app/library/README.md`, `evals/admin_agent/README.md`, `docs/glossary.md`(회원 전화번호)
