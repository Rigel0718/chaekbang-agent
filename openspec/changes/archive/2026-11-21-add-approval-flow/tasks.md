순서: 1~3은 LLM 없이 승인 틀과 큐레이션을 끝까지 만들고, 4~5는 두 에이전트에 잇고, 6은 평가, 7은 문서다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 공통 승인 틀 (design 결정 1·2·3)

- [x] 1.1 `app/library/approval.py`에 `ApprovalStatus`(여섯 값), 종류별 전이 표, 조건부 갱신 전이 함수(바뀐 행 없음 → 없으면 404, 상태가 다르면 409), 승인 칸 mixin(`approved_by`, `approved_at`, `executed_at`, `rejected_reason`)을 만든다(확인: 스펙 approval-flow "상태 전이" 다섯, "동시 승인"의 테스트를 테스트용 전이 표로)

## 2. 큐레이션 저장과 service (design 결정 4·5)

- [x] 2.1 `app/library/models/curation.py`(`curations`, `curation_items`)와 `app/models.py` 등록, 마이그레이션(enum `approval_status` 포함)을 만든다. 개발 DB를 백업한 뒤 `&&`로 업그레이드한다(확인: 스펙 approval-flow "승인 상태"의 테스트, `alembic downgrade -1 && alembic upgrade head`가 됨)
- [x] 2.2 `app/library/schemas/curation.py`와 `app/library/services/curations.py`의 만들기·고치기·지우기(내용 규칙, 같은 책 합치기, 쓸 때 추천 가능 검사)를 만든다(확인: 스펙 curations "큐레이션 내용" 셋, "큐레이션의 책은 추천 가능한 소장 도서" 둘의 테스트)
- [x] 2.3 제출·승인(게시까지 한 트랜잭션)·반려·내리기 service와 목록·상세(카드에 이유)를 만든다(확인: 스펙 approval-flow "승인과 실행", curations "승인하면 게시" 둘의 테스트)
- [x] 2.4 게시본 읽기 service(최신 5개, 읽을 때 다시 거르기, 0권이면 뺌)를 만든다(확인: 스펙 curations "게시본 읽기"의 최신 5개, "읽을 때 다시 거르기" 둘의 테스트)

- [x] 2.5 (구현 중 더함) 스펙 delta `platform/database-schema`(테이블 24개, 포함 도서의 같은 기관)에 맞춰 스키마 테스트를 고친다(확인: `tests/platform/test_database_schema.py`의 테이블 구성·개수, "큐레이션 포함 도서의 기관" 테스트)

## 3. 큐레이션 API (design 결정 8)

- [x] 3.1 `app/library/api/curations.py`(관리자 경로 9개, `require_admin`)와 `GET /librarian/curations`(키오스크·관리자)를 만들고 `app/main.py`에 등록한다(확인: 스펙 curations "큐레이션 관리 API" 셋, "게시본 읽기"의 게시된 것만·다른 기관, approval-flow "승인 권한" 둘, "승인의 기관 분리" 둘, curations "큐레이션의 개인정보"의 테스트)
- [x] 3.2 재시작 테스트를 쓴다: 엔진 A로 커밋하고 dispose, 새 엔진 B로 `get_session`을 바꾼 앱에서 HTTP로 승인과 게시본 읽기, 끝나면 만든 기관을 지운다(확인: 스펙 approval-flow "재시작 뒤 이어짐"의 테스트)
- [x] 3.3 `app/library/README.md`에 승인 틀(상태, 전이, 새 종류를 더하는 법)과 큐레이션 API를 적는다(확인: README에 새 종류 추가 절차가 있음)

## 4. 운영 에이전트 v2 (design 결정 6)

- [x] 4.1 `draft_curation` tool(만들기와 제출 한 트랜잭션, 기록은 `library_book_id`만)을 만든다(확인: 스펙 admin "큐레이션 초안 tool" 셋의 테스트, 가짜 LLM)
- [x] 4.2 `build_admin_profiles`에 `search_collection`과 `draft_curation`을 더하고 프롬프트(큐레이션 규칙, 승인 요청 안내)를 고치며 버전을 v2로 올린다. 운영 대화 경로가 질의 인코더를 넘긴다(확인: 스펙 admin "운영 방식별 tool" 셋, "운영 에이전트의 소장 도서 검색"의 테스트, 기존 운영 에이전트 테스트 통과)

## 5. AI 사서 `get_curations` (design 결정 7)

- [x] 5.1 `get_curations` tool(게시본 읽기 service 재사용, 검색 결과 값 + 이유, 없음 표시)을 만들고 AI 사서 프로필에 더해 v7로 올리며 프롬프트에 큐레이션 질문 규칙을 적는다(확인: 스펙 librarian "큐레이션 tool" 넷의 테스트, 기존 AI 사서 테스트 통과)

## 6. 평가 (design 결정 9)

- [x] 6.1 `evals/admin_agent`에 큐레이션 기관(자체 대출·외부 대출, 주제 `공룡`·`우주` 각 3권 이상), 시나리오 4개와 라벨, 지표 "초안 충실도"를 더하고 README를 고친다(확인: 스펙 admin-agent-evals "평가 기관" 셋, "시나리오 라벨" 스펙 추적, "평가 지표"의 새 둘, "평가 실행과 결과" 요약 파일의 테스트, 가짜 LLM)
- [x] 6.2 `evals/librarian`에 게시본 시나리오 2개(있음, 없음)와 준비 코드를 더한다(확인: `--only`로 두 시나리오를 가짜 LLM 경로로 고를 수 있음, 라벨이 스펙 librarian "큐레이션 질문에 답함" 두 시나리오를 추적)
- [x] 6.3 사람 확인: 새 라벨 6개를 사용자가 본다(확인: 사용자 확인 기록. 2026-11-21 고칠 곳 없이 실행 승인)
- [x] 6.4 실제 LLM 실행: 호출 수를 알리고 승인을 받은 뒤 새 시나리오 6개, 그다음 `evals.admin_agent`·`evals.librarian` 전체를 한 번씩 돌려 design "결과"에 적는다(확인: 새 시나리오 모두 맞음, 전체가 지난 결과보다 나빠지지 않음. 운영 `science-word` 하나는 나빠졌고 사용자 결정으로 개선 사항에 기록, design 결과)

## 7. 마무리

- [x] 7.1 전체 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`를 돌린다(확인: 모두 통과, 0.1보다 테스트 수가 늘어남)

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive하고 `docs/roadmap.md`의 22번 상태와 확정된 기본값을 고친다.
- `CLAUDE.md` "현재 단계"를 다음 change(`add-overdue-notice`)로 바꾼다.
