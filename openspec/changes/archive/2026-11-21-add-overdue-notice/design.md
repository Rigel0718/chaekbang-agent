## Context

- **지금 상태**
  - 공통 승인 틀(`app/library/approval.py`)에 확정하는 종류의 전이 표 `CONFIRMING`(실행 상태 `confirmed`, 내리기 없음)이 있지만 쓰는 곳이 없다. 큐레이션은 `PUBLISHING`을 쓴다(`services/curations.py`).
  - 연체는 저장하지 않고 조회할 때 계산한다(`services/loans.py`의 `LoanFilter.OVERDUE`, `is_overdue`, 기준일 `clock.today()`). `GET /loans?status=overdue`가 등록번호·제목·회원번호·날짜를 돌려준다.
  - 회원은 회원번호와 이름만 있다(`models/circulation.py`의 `Member`, `schemas/circulation.py`). 회원 API는 관리자 토큰만 받는다. 미반납 대출이 있는 회원은 지울 수 없다.
  - 운영 에이전트(`admin_agent.py`, v2)는 운영 방식별 프로필을 만들고, 외부 대출 기관에서는 대출 tool을 뺀다(`analytics_tools(axes, loans=...)`). 실행 기록에는 tool마다 `record_fields`로 고른 맨 위 입력만 남는다(`curation_tools.py`).
  - 관리자 대화의 문장은 `mask_personal`(`privacy.py`)로 전화번호·이메일·주민번호·그 기관 회원번호를 가린 뒤 LLM에 간다. 이름은 가리지 않는다.
- **제약**: MVP 출시가 우선이다. 각 결정은 동작하는 가장 단순한 안으로 정하고 품질 개선은 roadmap에 적는다. 실제 발송은 범위 밖이다.

## Goals / Non-Goals

**Goals:**

- `CONFIRMING`을 처음 쓰는 종류를 승인 틀 README의 "새 종류 더하기" 순서대로만 더한다. 승인 틀 코드는 바꾸지 않는다.
- 회원 값(이름, 회원번호, 전화번호)이 LLM 요청, 실행·대화 기록, 틀 행에 들어가지 않는 것을 tool 결과의 필드와 코드 채우기로 보장한다.
- 담당자는 틀을 한 번 승인하면 이후 승인 없이 오늘의 연락 목록을 받는다.

**Non-Goals:**

- 안내 이력, 연락함 표시, 회원별 묶음, CSV, 발송, 수신 동의, 관리자 화면.
- 휴관일을 뺀 연체 일수, 날짜 표기 바꾸기.

## Decisions

### 1. 승인은 틀에만, 목록은 계산

`overdue_notice_templates`(기관별, `ApprovalMixin`, `CONFIRMING`) 하나만 만든다. 승인하면 같은 트랜잭션에서 `mark_executed`로 `confirmed`와 `executed_at`을 둔다. 확정 자체가 "실행"이다. 쓰는 틀은 `status = confirmed` 가운데 `executed_at`이 가장 늦은 행(같으면 id가 큰 것)이다. 이전 확정 틀의 상태는 바꾸지 않는다. 응답의 "지금 쓰는 틀인지"는 조회할 때 계산한다.

- **고른 이유**: 회원에게 나갈 위험한 부분은 LLM 문장뿐이고, 연체 대출과 회원 값은 코드가 정확히 뽑는다. 매번 승인하면 담당자가 쓰지 않는다(탐색 때 사용자 지적). 이전 틀을 `archived`로 바꾸는 안은 `CONFIRMING`에 내리기가 없어 승인 틀을 고쳐야 한다.
- **버린 안**: 안내 한 번마다 초안 → 승인 → 승인 시점 스냅숏(항목 테이블). 이력이 남지만 테이블이 하나 더 생기고, 채운 문안이나 회원 값을 저장하게 된다.
- `docs/design.md` 승인 흐름의 연체 안내 문장을 "연체 안내 틀 확정은 승인 후, 그 틀로 코드가 만든 목록은 승인 없이"로 고친다.

### 2. 자리표시와 채우기

자리표시는 상수 표 하나(`{이름}`, `{서명}`, `{반납예정일}`, `{연체일수}`, `{도서관}`)로 두고 `{서명}`, `{반납예정일}`을 필수로 한다. 검사는 `\{[^{}]*\}`로 찾은 자리표시가 모두 표에 있는지, 필수가 모두 있는지, 300자 이내인지 본다. 채우기는 표의 다섯 개를 `str.replace`로 바꾼다. `str.format`은 쓰지 않는다. 틀 문장 안의 다른 중괄호나 속성 접근이 코드로 해석되지 않게 하기 위해서다.

- 값: `{이름}` 회원 이름, `{서명}` 대출 목록과 같은 표시 서명(공식 서지 먼저), `{반납예정일}` `YYYY-MM-DD`, `{연체일수}` `(clock.today() - due_on).days`, `{도서관}` `libraries.name`.
- **버린 안**: 영문 자리표시(`{member_name}`). 관리자가 REST로 직접 고치는 문장이라 한국어가 읽기 쉽다.

### 3. 틀의 개인정보 검사

틀을 저장하기 전에(REST와 tool 같은 service) `mask_personal(session, library_id, text) != text`이면 422(tool은 오류 결과)로 거부한다. 메시지에는 찾은 값을 넣지 않는다. 몰래 가리고 저장하지 않는 이유는 틀이 잘못 쓰였다는 걸 만든 쪽(관리자나 LLM)이 알게 하기 위해서다.

- 이름은 검사하지 않는다(`privacy.py`의 기존 방침). 두세 글자 이름이 일반 낱말과 겹쳐 잘못 거부할 수 있다. 대신 평가 시나리오(`overdue-notice-name`)로 LLM이 `{이름}`을 쓰는지 본다. 이름 맞춰 보기는 개선 사항이다.

### 4. 연체 줄 service 하나, 출구 둘

`overdue_rows(session, library_id, today)`가 연체 대출을 회원·사본·기관 도서·공식 서지와 조인해 회원번호 → 반납 예정일 → 대출 id 순으로 돌려준다. 연체 판정은 `services/loans.py`의 `OVERDUE` 조건을 그대로 쓴다.

- `GET /overdue-notices/today`: 쓰는 틀이 없으면 409, 있으면 줄마다 회원 값과 채운 문안을 붙여 전부 돌려준다. 저장하지 않는다.
- `list_overdue_loans` tool: 줄에서 허용 목록 필드(`title`, `accession_number`, `due_on`, `overdue_days`)만 골라 20줄까지, `total`·`shown`·`truncated`·`has_template`과 함께 준다. 허용 목록은 상수로 두고 pytest로 고정한다(분석 tool과 같은 방식).
- **버린 안**: tool과 REST를 따로 조회. 연체 기준이나 순서가 어긋날 수 있다.

### 5. 안내문 틀 초안 tool

`draft_overdue_notice`는 `template` 하나를 받아 `create_template(..., submit=True)`(큐레이션과 같은 모양)를 부른다. 결과는 `template_id`, `status`, `overdue_count`, 승인 안내 `note`다. 채운 미리보기는 주지 않는다. 회원 값을 LLM에 보내지 않기 위해서다. `record_fields=()`로 입력을 실행 기록에 남기지 않는다. 틀 문장은 틀 행에만 있다.

### 6. 외부 대출 기관 차단은 service 한 곳

틀 service와 연체 줄 service의 맨 앞에서 기관의 `loan_mode`를 보고 `external`이면 대출 차단과 같은 계열의 `ConflictError`(409, "대출은 기존 프로그램에서 관리합니다" 안내)를 올린다. REST와 tool이 같은 검사를 지난다. 프로필에서는 `loans=mode == INTERNAL`일 때만 두 tool을 넣는다.

### 7. 회원 전화번호

`members.phone`은 `String(11)`이고 비어 있을 수 있다. 스키마 검증기가 하이픈·공백·점을 지운 뒤 `^0\d{8,10}$`를 검사하고, 빈 문자열은 None으로 둔다. `MemberRead`에 `phone`을 더한다(관리자 API만 이 스키마를 쓴다). 회원 검색 `q`는 바꾸지 않는다. 연체 안내 목록은 조회할 때 회원 행에서 읽는다.

### 8. 프롬프트 v3

`BASE_PROMPT`에 "연체 안내" 절을 더한다. 연체를 물으면 `list_overdue_loans`를 쓰고, 안내문을 부탁하면 자리표시 다섯 개로 틀을 써서 `draft_overdue_notice`를 부르게 한다. 회원 이름이나 번호를 들어도 틀에 쓰지 말고 `{이름}`을 쓰며, 결과의 `overdue_count`만 말하게 한다. `patron_info` 안내를 "연체 안내 목록"으로 바꾸고, 승인 안내에 확정을 더한다. 외부 대출 문구에 "연체 안내문"을 더한다. `PROFILE_VERSION = "v3"`.

## Risks / Trade-offs

- [안내 이력이 없어 같은 사람에게 몇 번 연락했는지 모름] → MVP는 발송이 없어 담당자가 판단한다. 안내 이력·연락함 표시는 개선 사항.
- [LLM이 대화 속 회원 이름을 틀에 그대로 씀] → 프롬프트 규칙과 평가 시나리오. 틀이 채워지면 이름이 두 번 나오는 정도이고 다른 회원에게는 잘못된 이름이 간다 → 승인 단계에서 사람이 본다. 이름 맞춰 보기 검사는 개선 사항.
- [승인한 틀의 문장이 연체가 없는 날에도 그대로] → 목록이 비면 빈 줄을 돌려줄 뿐이다.
- [연체 일수에 휴관일이 들어감] → 판정 기준(`due_on < today`)과 같게 두고, 휴관일 빼기는 개선 사항.
- [전화번호를 LLM에 보내는 경로가 새로 생길 수 있음] → tool 출력 허용 목록과 카나리아 pytest가 회귀를 막는다.

## Migration Plan

- 마이그레이션 하나: `members.phone` 추가(nullable, 기존 행 null), `overdue_notice_templates` 생성(`approval_status` CHECK는 기존 공통 정의 사용). 되돌리면 둘 다 지운다.
- `app/models.py`의 `TENANT_TABLES`에 새 테이블을 넣는다.

## Open Questions

없음.

## 결과

- **기준(0.1, 2026-11-21)**: pytest 1787 통과·7 건너뜀·2 실패, ruff 통과. 실패 둘(`test_scenarios_trace_admin_eval_requirements`, `test_scenarios_cover_eval_requirements`)은 새 스펙 delta의 `연체 안내 요청에 답함` 시나리오 4개를 평가 시나리오가 아직 추적하지 않아서이고, 5.1에서 풀린다(변경 전 저장소에서는 모두 통과).
- **스펙 delta 고침(3.1 점검, 4구간)**: `library/overdue-notices` "틀의 개인정보 거부"에 회원번호는 4자 이상만 맞춰 본다고 적었다. 대화 문장 가리기(`privacy.py`의 `MIN_MEMBER_NUMBER_LENGTH`)와 같은 기준이고, 짧은 번호는 `7일` 같은 문장 속 숫자와 구분할 수 없다. 테스트 `test_short_member_number_is_not_matched`로 고정했다.
- **평가(5.3, 2026-11-21, `gpt-6-luna`, admin v3)**
  - 새 시나리오 4개: 4/4(지표 넷 모두). 입력 토큰 약 2.9만. LLM이 쓴 틀은 둘 다 자리표시만 썼다(`{이름}님, 대출하신 「{서명}」의 반납 예정일은 {반납예정일}이며 현재 {연체일수}일 연체 중입니다…`). 이름을 말한 요청에도 `{이름}`을 썼다.
  - 운영 전체 31개: 27/31(tool 선택 29, 숫자 충실도 29, 못 하는 분석 29, 초안 충실도 30). 입력 토큰 약 25.7만. 틀린 넷:
    - `overdue-notice-external`: 종류 `other`, "관리 화면에서 안내문을 확인하고 승인해 주세요"라고 안내. 공통 프롬프트의 연체 안내 목록·승인 안내가 외부 대출 기관에도 섞인 것이라 외부 대출 문구에 "연체 안내문 틀도 연체 안내 목록도 없다, no_data, 관리 화면·승인·목록을 안내하지 않는다"를 더했다(v3 그대로, 외부 프롬프트 pytest 추가). 고친 뒤 3번 모두 맞음.
    - `overdue-count`: 새 `list_overdue_loans`로 맞는 건수(2)를 답했다. 라벨을 `get_loan_stats` 또는 `list_overdue_loans`로 넓혔다(사용자 승인).
    - `busy-fields`(권당 대출이 높은 역사 대신 자연과학을 말함), `curation-space`(3권을 찾고도 모자란다고 판단): 맞는 tool을 불렀고 이번 change와 관계없는 흔들림으로 본다. 다시 2번씩 돌려 모두 맞음. roadmap 개선 사항에 적는다.
  - 고친 뒤 재실행은 외부 3번, 나머지 둘 2번씩만 했다(약 20회 호출). 전체 31개는 다시 돌리지 않았다(수정이 외부 대출 문구와 라벨 하나에만 걸림).

