순서: 1~3은 LLM 없이 전화번호, 안내문 틀, 연체 안내 목록을 끝까지 만들고, 4는 운영 에이전트에 잇고, 5는 평가, 6은 문서와 마무리다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 저장 (design 결정 1·7, Migration Plan)

- [x] 1.1 `Member.phone`(`String(11)`, nullable)과 새 `app/library/models/overdue_notice.py`(`overdue_notice_templates`: `library_id`, 문장, `created_by`, `ApprovalMixin`, 문장 비어 있지 않음 CHECK)를 만들고 `app/models.py`의 `TENANT_TABLES`에 넣는다. 마이그레이션을 만들고 개발 DB를 백업한 뒤 `&&`로 업그레이드한다(확인: 스펙 database-schema "빈 DB에 upgrade"(25개), "회원 전화번호 칸", "안내문 틀의 저장 계층 규칙"의 테스트, `alembic downgrade -1 && alembic upgrade head`가 됨)

## 2. 회원 전화번호 (design 결정 7)

- [x] 2.1 `MemberCreate`·`MemberUpdate`·`MemberRead`에 `phone`(지우기·검증, 빈 값 null)을 더하고 회원 service가 저장·수정한다. 검색 `q`는 그대로 둔다(확인: 스펙 members "정상 등록", "전화번호와 함께 등록", "전화번호 형식 오류", "전화번호로는 찾지 않음", "전화번호 지우기"의 테스트, 기존 회원 테스트 통과)

## 3. 안내문 틀과 연체 안내 목록 (design 결정 1~4·6)

- [x] 3.1 `app/library/schemas/overdue_notice.py`와 `app/library/services/overdue_notices.py`의 틀 만들기·고치기·지우기를 만든다: 자리표시 표·필수·300자 검사, `mask_personal` 비교로 개인정보 거부, 외부 대출 기관 409(확인: 스펙 overdue-notices "안내문 틀 내용" 넷, "틀의 개인정보 거부" 둘, "외부 대출 기관의 틀 만들기"의 테스트)
- [x] 3.2 제출·승인(`CONFIRMING`, 같은 트랜잭션에서 `mark_executed`)·반려, 목록(상태 거르기, 최신순)·상세, 쓰는 틀 고르기(`executed_at`이 가장 늦은 확정 틀, 같으면 id 큰 것)를 만든다(확인: 스펙 overdue-notices "승인 기록", "확정된 틀 고치기", "새로 확정한 틀", "승인 대기 틀"의 테스트)
- [x] 3.3 연체 줄 service(`overdue_rows`: 연체 판정은 `services/loans.py`와 같은 조건, 표시 서명, 연체 일수, 회원번호 → 반납 예정일 → 대출 id 순)와 채우기(`str.replace`로 다섯 자리표시)를 만든다(확인: 스펙 overdue-notices "채운 문안", "반납했거나 아직 기한 안", "전화번호 없는 회원", "같은 회원의 두 권"의 테스트)
- [x] 3.4 `app/library/api/overdue_notices.py`(틀 경로 8개와 `GET /overdue-notices/today`, `require_admin`)를 만들고 `app/main.py`에 등록한다(확인: 스펙 overdue-notices "상태로 거르기", "반려 뒤 고쳐 제출", "틀 없음", "저장 없음", "연체 안내 권한" 둘, "연체 안내의 기관 분리" 셋, "외부 대출 기관의 목록"의 테스트)
- [x] 3.5 `app/library/README.md`의 승인 흐름 절에 연체 안내(틀만 승인, 목록은 계산, 자리표시, 개인정보 검사)를 적는다(확인: README에 연체 안내 절이 있음)

## 4. 운영 에이전트 v3 (design 결정 4·5·8)

- [x] 4.1 새 `app/library/overdue_tools.py`에 `list_overdue_loans`(허용 목록 필드, 20줄, `total`·`shown`·`truncated`·`has_template`)와 `draft_overdue_notice`(`submit=True`, `record_fields=()`, 결과에 채운 문안 없음)를 만든다(확인: 스펙 admin "연체 목록 tool" 셋, "안내문 틀 초안 tool" 셋의 테스트, 가짜 LLM)
- [x] 4.2 `build_admin_profiles`의 자체 대출 기관 프로필에 두 tool을 넣고, 프롬프트(연체 안내 절, `patron_info` 안내, 확정 승인 안내, 외부 대출 문구)를 고치며 v3로 올린다(확인: 스펙 admin "운영 방식별 tool" 셋의 테스트, 기존 운영 에이전트 테스트 통과)
- [x] 4.3 카나리아 테스트: 카나리아 회원이 연체한 기관에서 가짜 LLM이 두 tool을 부른 운영 대화 한 번 뒤, 가짜 LLM이 받은 모든 요청과 `agent_runs`·`agent_steps`·대화 기록·틀 행을 검사한다(확인: 스펙 admin "카나리아 회원"의 테스트)

## 5. 평가 (스펙 admin-agent-evals)

- [x] 5.1 `evals/admin_agent`에 시나리오 4개(`overdue-list`, `overdue-notice`, `overdue-notice-name`, `overdue-notice-external`)와 라벨(틀 기대, 승인 대기 낱말), 초안 충실도의 틀 판정을 더하고, `who-overdue`의 추적을 고치며 README를 고친다(확인: 스펙 admin-agent-evals "되돌림", "스펙 추적", "기대하지 않은 초안", "회원 이름이 든 틀"의 테스트, 가짜 LLM)
- [x] 5.2 사람 확인: 새 라벨 4개를 사용자가 본다(확인: 사용자 확인 기록. 2026-11-21 고칠 곳 없이 실행 승인)
- [x] 5.3 실제 LLM 실행: 호출 수를 알리고 승인을 받은 뒤 새 시나리오 4개, 그다음 `evals.admin_agent` 전체를 한 번 돌려 design "결과"에 적는다(확인: 새 시나리오 모두 맞음, 전체가 지난 결과(26/27)보다 나빠지지 않음. 전체 27/31, 외부 대출 프롬프트 수정과 `overdue-count` 라벨 넓힘 뒤 틀린 시나리오 재실행 모두 맞음, design 결과)

## 6. 문서와 마무리

- [x] 6.1 `docs/design.md`(tool 표의 두 tool, 승인 흐름의 연체 안내 문장, 테이블 목록), `docs/glossary.md`(회원 전화번호), `docs/roadmap.md`의 "`add-overdue-notice`에서 미룸"(안내 이력, 연락함 표시, 회원별 묶음, CSV, 자동 발송과 수신 동의, 이름 맞춰 보기, 휴관일 뺀 연체 일수, 날짜 표기, 자리표시 추가, 외부 대출 기관 연체 파일, 전화번호 표시 형식)을 고친다(확인: 문서에 각 항목이 있음)
- [x] 6.2 전체 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`를 돌린다(확인: 모두 통과, 0.1보다 테스트 수가 늘어남. 1844 통과·7 건너뜀, 0.1은 1787)

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive하고 `docs/roadmap.md`의 22b 상태와 확정된 기본값을 고친다.
- `CLAUDE.md` "현재 단계"를 다음 change로 바꾼다.
