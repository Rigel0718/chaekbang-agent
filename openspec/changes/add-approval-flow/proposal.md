## Why

운영 에이전트는 지금 분석만 하고 아무것도 확정하지 못한다. 설계 원칙 3은 큐레이션 게시·연체 안내·구매 요청서 확정이 `draft → pending_approval → approved → (published | confirmed)`를 거치고 승인 대기가 DB에 남기를 요구하는데, 그 틀이 아직 없다. 이용자 쪽 AI 사서도 "이달의 추천"을 보여 줄 근거(`get_curations`)가 없어 v1에서 미뤄 두었다.

MVP 출시가 우선이므로 이번 change는 **공통 승인 틀과 큐레이션 하나를 끝까지**(초안 → 승인 → 게시 → 이용자 쪽에서 읽기) 만든다. 큐레이션은 지금 있는 데이터(소장 도서, 주제로 찾기)만으로 되고 게시가 하는 일이 분명해서, 완료 기준인 "서버를 재시작해도 승인이 이어짐"을 끝까지 확인할 수 있다. 연체 안내(회원 연락처 결정 필요)와 구매 요청서(희망도서 근거와 가격 필요)는 같은 틀 위에 따로 얹는다.

## What Changes

- **공통 승인 틀**: 상태 값(`ApprovalStatus`: `draft`, `pending_approval`, `approved`, `published`, `confirmed`, `archived`)과 전이 규칙을 공통 코드 한 곳에 둔다. 초안 테이블마다 `status` 칸을 두고 같은 전이 함수를 쓴다. 공통 `approvals` 표는 만들지 않는다.
  - 전이: 만들기(`draft`), 제출(→ `pending_approval`), 승인(→ `approved` → 종류별 실행), 반려(→ `draft`, 사유), 내리기(`published` → `archived`), 삭제(`draft`만). 허용되지 않은 전이는 409. 승인은 조건부 갱신이라 두 번 누르면 두 번째가 409다.
  - 승인·반려·내리기는 관리자(`admin`)만. 승인자와 시각을 남긴다. 만든 사람이 승인해도 된다.
  - 승인 뒤 에이전트 실행을 이어 가지 않는다. 에이전트 실행은 초안을 저장하고 끝나며, 승인과 실행은 REST에서 코드가 한다. 상태가 DB에만 있으므로 재시작 뒤에도 이어진다(`docs/design.md`의 "승인되면 에이전트 실행을 이어서 진행"을 바꾼다).
- **큐레이션**: 제목, 소개, 책 3~10권(책마다 이유 한 줄). 책은 그 기관의 추천 가능한 책만. 승인하면 바로 게시한다(`approved` → `published` 한 트랜잭션).
  - 관리자 REST: 목록·상세·만들기·고치기(`draft`만)·삭제(`draft`만)·제출·승인·반려·내리기.
  - 게시본 읽기 `GET /librarian/curations`(키오스크·관리자): 최신 5개, 읽을 때 지금 추천 가능한 책만 다시 거르고 0권이면 뺀다.
- **운영 에이전트 v2**: 소장 도서 검색 tool(AI 사서와 같은 tool)과 `draft_curation` tool을 더한다. tool로 만든 초안은 바로 승인 대기로 올린다. 운영 방식 두 가지 모두에 넣는다. 운영 대화도 질의 인코더를 넘긴다(없으면 키워드).
- **AI 사서**: 게시된 큐레이션을 돌려주는 `get_curations` tool. 답의 책은 기존 최종 검사(소장, 어린이)를 그대로 거친다. 프로필 버전을 올린다.
- **평가**: `evals/admin_agent`에 큐레이션 시나리오 4개와 지표 "초안 충실도", `evals/librarian`에 게시본 시나리오 2개.
- **범위 밖**: 연체 목록·안내문·회원 연락처(`add-overdue-notice`), 구매 요청서(`add-purchase-request`, `add-librarian-actions` 뒤), 관리자 승인 화면과 이용자 화면의 "이달의 추천" 줄(`add-web-ui`), 승인 이력 표, 대화로 초안 고치기, 어린이 큐레이션 표시, 게시 기간, 실제 발송.

## Capabilities

### New Capabilities

- `library/approval-flow`: 확정 작업의 공통 승인 상태, 전이 규칙, 권한, 동시 승인, 기관 분리, 재시작 뒤 이어짐
- `library/curations`: 큐레이션의 내용 규칙, 관리자 REST, 게시본 읽기와 읽을 때 거르기

### Modified Capabilities

- `agent/admin`: 운영 방식별 tool에 검색과 큐레이션 초안 tool을 더하고 "쓰기 tool은 없다"를 고침. 큐레이션 초안 tool 계약과 초안 요청에 답하는 에이전트 동작(평가)
- `agent/librarian`: 조회 tool에 게시된 큐레이션 tool을 더함. 큐레이션 질문에 답하는 에이전트 동작(평가)
- `platform/admin-agent-evals`: 큐레이션 시나리오의 라벨(기대 초안)과 지표 "초안 충실도"
- `platform/database-schema`: 마이그레이션이 만드는 테이블이 22개에서 24개(`curations`, `curation_items`)로, 포함 도서의 같은 기관 참조(구현 중 2026-11-21 더함)

## Impact

- 코드: 새 `app/library/approval.py`(상태 값, 전이), 새 `app/library/models/curation.py`, 새 `app/library/services/curations.py`, 새 `app/library/schemas/curation.py`, 새 `app/library/api/curations.py`, `app/library/admin_agent.py`(v2, tool, 프롬프트), `app/library/tools.py` 또는 새 `app/library/curation_tools.py`(`draft_curation`, `get_curations`), `app/library/librarian.py`(tool, 버전), `app/library/api/admin_agent.py`·`services/admin_chat.py`(질의 인코더), `app/main.py`, `app/models.py`
- DB: 마이그레이션 하나. `curations`, `curation_items`, enum `approval_status`
- API: 새 `/curations` 관리자 경로들, 새 `GET /librarian/curations`
- 외부 호출: 없음
- LLM: 평가 실행만. 호출 수를 알리고 승인을 받은 뒤 한다
- 문서: `docs/design.md`(승인 흐름 문장, 테이블 목록), `docs/roadmap.md`(22번, 22b·23b, 개선 사항), `CLAUDE.md`(원칙 3에 `archived`, 현재 단계), `app/library/README.md`, `evals/admin_agent/README.md`
