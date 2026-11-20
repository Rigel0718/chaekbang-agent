## Context

- **지금 상태**
  - 승인과 관련된 코드, 테이블, 스펙은 없다. `docs/design.md`에는 테이블 `approvals`와 "승인되면 에이전트 실행을 이어서 진행한다"는 문장이 있다.
  - 공통 실행기(`app/agent/runner.py`)는 한 번 돌고 끝나는 루프다. 실행 상태는 `running/completed/repaired/fallback/failed/refused/cancelled`이고 멈췄다가 이어 가는 상태가 없다. 실행 기록에는 이용자 문장, 모델이 쓴 글, tool 결과 원문을 남기지 않는다.
  - 운영 에이전트(`app/library/admin_agent.py`, v1)는 분석 tool 넷과 `submit_answer`만 있고 쓰기 tool이 없다. 운영 대화(`services/admin_chat.py`)는 질의 인코더를 넘기지 않는다.
  - AI 사서(`app/library/librarian.py`, v6)의 소장 도서 검색 tool은 `search_tool(...)`로 만들고 인코더를 `ctx.values`로 받는다. 추천 가능 조건은 `recommendation/search.py`의 `RECOMMENDABLE_STATUSES`, 카드는 `recommendation/cards.py`의 `build_cards`·`build_summaries`다.
  - 직원 역할은 `admin`·`kiosk` 둘이다.
- **제약**: MVP 출시가 우선이다. 각 결정은 동작하는 가장 단순한 안으로 정하고, 품질을 높이는 안은 `docs/roadmap.md`의 개선 사항으로 적는다.

## Goals / Non-Goals

**Goals:**

- 상태와 전이 규칙을 한 곳에 두어 다음 change(연체 안내, 구매 요청서)가 테이블만 더하면 되게 한다.
- 승인 대기는 DB 행만으로 이어진다. 프로세스, 실행, 세션 어디에도 승인에 필요한 상태를 두지 않는다.
- LLM은 책 고르기와 문장만 맡고, 소장·권수·길이·기관 범위는 코드가 막는다.

**Non-Goals:**

- 승인 이력 표, 승인 뒤 에이전트 실행 재개, 승인자 분리, 역할 세분화, 게시 기간.
- 관리자 승인 화면과 이용자 화면의 큐레이션 줄(`add-web-ui`).
- 대화로 초안 고치기, 대출 순위로 큐레이션 만들기, 어린이 큐레이션 표시.

## Decisions

### 1. 종류별 테이블에 `status` 칸, 공통은 상태 값과 전이 함수

`app/library/approval.py`에 `ApprovalStatus`(StrEnum), 전이 표, 전이 함수를 둔다. 전이 함수는 ORM 모델과 목표 상태를 받아 `UPDATE ... WHERE id = :id AND library_id = :lib AND status = :from RETURNING`으로 바꾸고, 바뀐 행이 없으면 상태 충돌(409) 또는 없음(404)을 올린다. 승인자·시각 칸(`approved_by`, `approved_at`, `executed_at`, `rejected_reason`)은 종류별 테이블이 같은 이름으로 가진다(공통 mixin).

- **고른 이유**: 대상이 셋뿐이고, 행마다 외래 키와 `library_id` 하나로 기관 분리가 끝난다. 상태 하나를 조회할 때 조인이 없다.
- **버린 안**: 공통 `approvals` 표(대상 종류 + 대상 id). 대상 id에 외래 키를 걸 수 없고, 기관 분리를 두 번 확인해야 하며, 대상과 승인 행의 상태가 어긋날 수 있다. 이력이 필요해지면 이력 표를 따로 더한다(개선 사항).

### 2. 승인 뒤 실행을 이어 가지 않는다

에이전트 실행은 초안을 저장하면 끝난다. 승인은 REST 요청 하나에서 전이와 실행(큐레이션은 게시)을 한 트랜잭션으로 한다. 실행은 결정적인 코드라 LLM을 다시 부르지 않는다.

- **고른 이유**: 실행을 이어 가려면 LLM 대화(이용자 문장, tool 결과)를 저장해야 하는데 실행 기록 원칙과 부딪힌다. 큐레이션·연체 안내·구매 요청서 모두 승인 뒤 할 일에 판단이 필요 없다.
- **버린 안**: 실행 상태 `waiting_approval`과 이어 가기. 실행기 스펙의 상태·기록·사건이 모두 바뀌고 이번 분량을 넘는다.
- `docs/design.md`의 승인 흐름 문장과 테이블 목록(`approvals`)을 이 결정에 맞게 고친다.

### 3. 상태와 전이

```
          create             submit              approve (한 트랜잭션)
  (없음) ---------> [draft] ---------> [pending_approval] -------> [approved] --> [published]
                     ^  |                    |                                        |
                     |  | delete             | reject(사유)                           | unpublish
                     |  v                    |                                        v
                     | (삭제)                |                                    [archived]
                     +-----------------------+
```

- `approved`는 확정 종류(`confirmed`)와 같은 모양을 쓰려고 남긴다. 큐레이션은 같은 트랜잭션에서 `published`까지 가므로 바깥에서 `approved`가 보이지 않는다.
- `archived`는 원칙 3에 없던 값이다. 게시본을 이용자 쪽에서 뺄 방법이 있어야 해서 더하고 `CLAUDE.md` 원칙 3을 고친다.
- `rejected` 상태는 두지 않는다. 반려는 사유를 남기고 `draft`로 돌아가 고칠 수 있게 한다.
- DB에는 enum `approval_status`(여섯 값)를 쓴다. 종류마다 쓰지 않는 값(큐레이션의 `confirmed`)은 코드의 전이 표가 막는다.

### 4. 큐레이션 테이블

- `curations`: `id`, `library_id`, `title`(40), `intro`(200, null 가능), `status`, `created_by`(직원), `approved_by`, `approved_at`, `executed_at`(게시 시각), `rejected_reason`, `created_at`, `updated_at`. 인덱스 `(library_id, status, executed_at)`.
- `curation_items`: `curation_id`, `position`, `library_book_id`, `reason`(60). 기관 도서는 같은 기관이어야 한다(service가 확인, `library_book_id`는 외래 키). 기관 도서가 지워지면 항목도 지운다(`ON DELETE CASCADE`).
- 고칠 때(PATCH)는 항목을 통째로 바꾼다. 부분 수정 API는 두지 않는다.

### 5. 추천 가능 검사는 쓸 때와 읽을 때 두 번

- 쓸 때(만들기, 고치기, tool): 모든 책이 그 기관의 추천 가능한 책인지 `recommendable_ids`로 한 번에 확인한다. 다른 기관이나 없는 책은 404, 추천 불가는 409이고 걸린 id를 메시지에 담는다. tool에서는 같은 도메인 오류가 LLM에 돌아간다.
- 읽을 때(게시본 읽기, `get_curations`): 지금 추천 가능한 책만 남기고 0권이면 뺀다. 게시 뒤 장서가 바뀌는 것(제적, 분실)을 따로 이벤트로 처리하지 않기 위해서다.
- 승인 때는 다시 확인하지 않는다. 읽을 때 거르므로 승인 대기 중에 빠진 책이 이용자에게 나가지 않는다.

### 6. 운영 에이전트 v2

- tool: 분석 넷(자체 대출만 대출 둘) + `search_collection`(AI 사서와 같은 `search_tool`) + `draft_curation` + `submit_answer`.
- `draft_curation` 입력: `title`, `intro`, `library_book_ids`, `reasons`(같은 순서, 같은 길이). 실행기의 `record_fields`는 맨 위 필드만 고르므로 책 id와 이유를 나눠 받아 `record_fields=("library_book_ids",)`로 둔다(실행기는 바꾸지 않는다, 구현 중 2026-11-21 정함). 이유와 제목이 실행 기록에 남지 않게 하는 테스트를 둔다. 길이가 다르거나 내용 규칙을 어기면 도메인 오류(LLM이 받음)다. tool 안에서 만들기와 제출을 한 트랜잭션으로 한다.
- 운영 대화가 질의 인코더를 넘기도록 `api/admin_agent.py`에서 AI 사서와 같은 의존성(`get_query_encoder`)을 쓴다.
- 프롬프트에 더하는 것: 큐레이션은 검색 결과의 책만, 3~10권, 이유는 결과의 서명·분류·소개 근거로 한 줄, 답에 "승인 대기로 올렸어요, 승인해야 게시돼요", 승인·게시 요청에는 하지 않고 관리 화면(지금은 API)을 안내하며 `unsupported=other`.
- 최종 답 구조는 그대로다(문장, `unsupported`).

### 7. AI 사서 `get_curations`

- 입력 없는 tool. 결과는 `{"curations": [{"title", "intro", "books": [검색 결과와 같은 값 + "reason"]}], "note"}`.
- 이유는 큐레이션 담당자가 쓴 문장이라 LLM이 그대로 옮겨도 된다. 답의 추천 이유는 여전히 LLM이 쓰고 최종 검사를 거친다.
- 프롬프트: "이달의 추천, 도서관 추천 목록, 큐레이션" 질문에 부른다. 없으면 없다고 하고 다른 추천을 권한다.
- 프로필 v6 → v7. `get_curations`는 기관 공통 tool이라 두 운영 방식 모두 가진다.

### 8. API

- 관리자: `app/library/api/curations.py`, 접두사 `/curations`. 전이는 `POST /curations/{id}/{submit|approve|reject|unpublish}`. 반려 본문 `{reason}`(200자 이내, 필수).
- 게시본: `GET /librarian/curations`. 기존 `librarian` 라우터에 더한다. 키오스크·관리자 둘 다.
- 응답 스키마는 `app/library/schemas/curation.py`. 책은 `build_summaries`로 만든 카드에 `reason`을 더한다. 회원·기증자 필드는 카드에 없다.

### 9. 테스트와 평가

- pytest(`tests/library/test_approval.py`, `test_curations.py`, `test_curations_api.py`, `test_curation_tools.py`): 스펙 시나리오마다 하나 이상, 이름에 요구사항을 적는다.
- **재시작 뒤 이어짐**: 이 테스트만 트랜잭션 되돌림을 쓰지 않는다. 엔진 A로 기관·책·승인 대기 큐레이션을 만들고 커밋한 뒤 `engine.dispose()`. 새 엔진 B로 `get_session` 의존성을 바꾼 앱에서 HTTP로 승인하고 게시본을 읽는다. 끝나면 만든 기관을 지운다. 앱의 `app.state`에 승인 관련 값이 없음을 함께 확인한다.
- 평가: `evals/admin_agent`에 큐레이션 기관(자체 대출 약 12권, 외부 대출 약 8권, 주제 `공룡`·`우주` 각 3권 이상)과 시나리오 4개(공룡 만들기, 우주 이달의 추천, 승인 요청, 외부 대출 기관 만들기), 지표 "초안 충실도". `evals/librarian`에 시나리오 2개(게시본 있음, 없음). 게시본은 시나리오 준비에서 service로 만든다.
- 회귀: 프롬프트가 바뀌므로 `evals.admin_agent` 전체와 `evals.librarian` 전체를 한 번씩 돌린다. 문턱은 지난 결과보다 나빠지지 않음이다.

## Risks / Trade-offs

- [에이전트가 검색하지 않은 책 id를 넣음] → 소장 검사가 다른 기관·추천 불가를 막고, 검색 결과 안의 책인지는 평가의 초안 충실도로 본다. 문제가 되면 tool에서 이번 실행의 검색 결과 id만 받게 한다(개선 사항).
- [이유 문장을 지어냄] → 담당자가 승인 전에 읽는다. 사실성 채점은 개선 사항.
- [승인 대기 중 책이 빠짐] → 읽을 때 거르므로 이용자에게 나가지 않는다. 관리자 상세에는 그대로 보여 승인 전에 알 수 있게 카드의 대출 상태를 함께 준다.
- [`approved`가 큐레이션에서 바깥에 안 보임] → 상태 표는 다음 종류와 같이 쓰려고 둔다. 테스트는 승인 시각이 남는지로 본다.
- [회귀 평가 비용] → 약 200회 호출. 실행 전에 수를 알리고 승인을 받는다.

## Migration Plan

- 마이그레이션 하나: enum `approval_status`, `curations`, `curation_items`. 기존 행을 바꾸지 않는다. 되돌리기는 두 테이블과 enum을 지운다.
- 적용 전에 개발 DB를 백업하고 명령은 `&&`로 잇는다.

## Open Questions

- 게시본 읽기 상한 5개가 이용자 화면에 맞는지는 `add-web-ui`에서 화면을 정할 때 본다. 스펙의 숫자만 바뀐다.

## 결과

- **시작 전 기준**(2026-11-21, 0.1): pytest 1721 통과, 7 건너뜀, 실패 2. 실패 둘(`test_admin_agent_eval.py::test_scenarios_trace_admin_eval_requirements`, `test_librarian_eval.py::test_scenarios_cover_eval_requirements`)은 이 change의 delta 스펙에 새로 생긴 평가 시나리오를 아직 평가가 추적하지 않아서다(6.1·6.2에서 해결). ruff 통과.
- **평가 실행**(2026-11-21, 6.4, `gpt-6-luna`, 운영 admin v2, AI 사서 v7, 사용자 승인 뒤)
  - 새 시나리오만: 운영 4/4(지표 넷 모두), 사서 2/2(기대 맞음, 규칙 위반 0). 입력 토큰 약 4.8만.
  - 운영 전체 27개: tool 선택 26/27, 숫자 충실도 26/27, 못 하는 분석 27/27, 초안 충실도 27/27, 모두 맞음 26/27(v1 기준 23/23). 틀린 하나는 `science-word`("과학책은 몇 권 있어?")로, 자연과학 하나 대신 자연과학+기술과학으로 불러 14권이라 답했다. 답에 기준(KDC 400·500번대)을 밝혔다. 같은 시나리오만 두 번 더 돌려도 같았다(v2에서 일관된 동작). 입력 토큰 약 20.3만.
  - 사서 전체 34개(37턴): 규칙 위반 0, 기대 불일치 1(`no-description`), 고정 답 0%. 답은 "소개 정보와 목차가 제공되지 않아 내용을 확인해 드리기 어렵습니다"로 맞는 답인데, 판정 정규식에 "제공되지 않"이 없어 틀림으로 나왔다. 지난 기준(2026-11-17)은 기대 불일치 0~1(`related-anything`). 질의 인코딩 실패 4번(임베딩 서버를 막 띄운 직후, 키워드로 내려감). 입력 토큰 약 24.3만.
  - 판정 넓힘(사용자 결정, 2026-11-21): `science-word` 라벨이 자연과학만 또는 자연과학+기술과학(8 또는 14권)을 받게 하고, 사서 `no-description` 정규식에 "제공되지 않"을 더했다. 다시 돌린 결과 `no-description`은 맞음. `science-word`는 이번에는 "과학책처럼 주제로 세는 분석은 아직 못 해요"(`unsupported`)로 답해 다시 틀렸다. 네 번 중 세 번은 둘을 합쳐 답했고 한 번은 못 한다고 답했다. 판정 문제가 아니라 v2에서 "과학책" 질문의 분야 고르기가 흔들리는 것이다(v1에서는 두 번 모두 맞음).
  - 결정(사용자, 2026-11-21): `science-word`는 개선 사항으로 `docs/roadmap.md`에 기록하고 운영 평가 결과를 26/27로 둔다. 프롬프트 수정과 전체 재평가는 MVP 뒤.
- **라벨 확인**(6.3, 2026-11-21): 새 라벨 6개(운영 4, 사서 2)를 사용자가 보고 고칠 곳 없이 실행을 승인했다.
- **마무리**(7.1, 2026-11-21): pytest 1796 통과, 실패 0, 건너뜀 0(임베딩 서버가 떠 있어 실서버 테스트 7개도 돌았다. 0.1은 1721 통과·7 건너뜀·실패 2). ruff check·format 통과, `openspec validate --strict` 통과.
