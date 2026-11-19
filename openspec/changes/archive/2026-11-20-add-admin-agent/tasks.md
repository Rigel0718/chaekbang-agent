순서: 1~3은 LLM 없이 숫자를 맞추고, 4~6은 운영 에이전트를 잇고, 7~8은 평가다. 분량이 넘치면 7~8을 다음 change로 나눈다(design 결정 13).

## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 분석 빌더 (design 결정 2·3·4·5, LLM 없음)

- [x] 1.1 `app/library/analytics/`에 분야 결정(공식 KDC → 기관 KDC → 제적 아닌 가장 작은 id 사본의 청구기호 → 분류 없음)과 분야 enum(`KDC_MAIN_CLASSES` + 분류 없음)을 만든다(확인: 스펙 collection-analytics "분야 결정" 넷의 테스트)
- [x] 1.2 기간 입력 모델(프리셋 7개 또는 월, 정확히 하나)과 계산(`clock.today()`, 양 끝 포함, `label`·`in_progress`)을 만든다(확인: "기간" 넷의 테스트, 고정 시계 2026-11-19)
- [x] 1.3 분석 축(`AnalysisAxis`: 이름, 값, 기본값, 표시 이름, 배정)과 등록, 필터·묶기 빌더(축 LEFT JOIN + COALESCE, 분야 필터 여러 개)를 만든다(확인: "공통 필터" 셋, "분석 축" 둘의 테스트를 테스트용 축으로)

## 2. 분석 service 네 개 (design 결정 6·7·8)

- [x] 2.1 `app/library/services/analytics.py`의 장서 현황(사본·서명·제적 따로, 묶기 다섯)과 결과 스키마를 만든다(확인: "장서 현황" 넷, "분석의 기관 범위"의 장서 쪽, 표시 값 테스트)
- [x] 2.2 상태별 사본 목록(분실·훼손·대출 중, 마지막 수정 시각, 외부 대출 기관의 갱신 시각, `total`·`shown`·`truncated`)을 만든다(확인: "상태별 사본 목록" 둘, "표시 값", "목록 한도와 잘림"의 목록 쪽 테스트)
- [x] 2.3 대출 통계(기간 대출 수, 묶기 넷, 지금 대출 중·연체 중, 분야면 사본 수와 권당 대출, 책 순위의 정렬·`in_collection`)를 만든다(확인: "대출 통계" 셋, "분야별 권당 대출" 둘, "책 순위" 셋의 테스트)
- [x] 2.4 안 빌린 책(기간 시작 전 등록, 제적 아닌 사본 있음, 한 사본이라도 빌리면 빠짐, 가나다순)을 만든다(확인: "안 빌린 책" 셋, "목록 한도와 잘림"의 잘린 목록 테스트)
- [x] 2.5 네 service의 기관 분리 테스트(B 기관에 같은 ISBN 사본·대출·어린이 배정)와 심은 값 테스트(회원 이름·번호·기증자)를 쓴다(확인: "분석의 기관 범위" 다른 기관의 같은 책, "분석 결과의 개인정보" 심은 값)
- [x] 2.6 대량 삽입 테스트를 쓴 뒤 테스트 DB를 `VACUUM ANALYZE`한다(확인: 전체 pytest 통과)

## 3. 어린이 축 (features)

- [x] 3.1 `app/features/children/`에 `audience` 축(배정은 `children_book_ids`, 기본 `general`, 표시 "어린이로 분류되지 않음")을 만든다(확인: 스펙 children "어린이 분석 축" 셋의 테스트, package-layers 테스트 통과)

## 4. 실행기의 답 기록 (design 결정 9)

- [x] 4.1 `AnswerTool.record_fields`, `agent_runs.answer_record`(JSONB)와 마이그레이션(개발 DB 백업 뒤 `&&`로 업그레이드), 실행기가 `completed`·`repaired`에서만 쓰기를 만든다(확인: 스펙 runner "최종 답의 기록 필드" 셋의 테스트, 기존 실행기 테스트 통과, `alembic downgrade -1 && upgrade head`가 됨)

## 5. 운영 에이전트 tool과 프로필 (design 결정 4·11)

- [x] 5.1 분석 tool 네 개를 조립 함수로 만든다. 등록된 축으로 입력 모델을 만들고, 입력은 모두 `record_fields`, 결과는 service 스키마다(확인: 축 있음·없음 두 조립의 strict 스키마 변환, "분석 축" 축 없는 조립, "분석 결과의 개인정보" 결과 필드 목록·입력 기록, "분석의 기관 범위" 입력의 기관 값 테스트)
- [x] 5.2 `app/library/admin_agent.py`에 최종 답(`message` 600자, `unsupported` enum, 기록 필드 `unsupported`), 고정 답, 프롬프트, `AdminExtension`, `build_admin_profiles`(자체 대출 tool 넷, 외부 대출 둘)를 만든다(확인: 스펙 admin "운영 방식별 tool" 둘, "운영 에이전트 최종 답" 길이 초과의 테스트)
- [x] 5.3 어린이 기능의 `admin_extension()`(축 + 프롬프트 문구)을 만들고 `app/main.py`가 `app.state.admin_profiles`를 조립한다(확인: 스펙 children "운영 에이전트 어린이 문구"의 테스트, 앱 시작 테스트)

## 6. 대화 경로와 세션 종류 (design 결정 10)

- [x] 6.1 `chat_sessions.kind`(`SessionKind`)를 4.1과 같은 마이그레이션에 넣고(아직 적용 전이면) 세션 조회를 기관 + 종류로 건다. 설정 `admin_session_idle_minutes`(30), `admin_daily_run_limit`(200)을 `app/core/config.py`와 `.env.example`에 더한다(확인: 스펙 chat-sessions "세션 종류"의 AI 사서 쪽, "세션 만료" 종류별, "일일 실행 상한" 다른 종류의 테스트, 기존 대화·세션 테스트 통과)
- [x] 6.2 `services/chat.py`에서 세션·가리기·상한·저장을 종류를 받는 공통 함수로 나누고, 운영 에이전트 턴(`session`, `status`, `answer`(`message`, `unsupported`), `done`)을 만든다. AI 사서 사건과 저장 내용은 바꾸지 않는다(확인: 기존 AI 사서 대화 테스트가 고치지 않고 통과, "운영 에이전트 문장 가리기" 테스트)
- [x] 6.3 `app/library/api/admin_agent.py`에 `POST /admin-agent/messages`, `DELETE /admin-agent/sessions/{id}`(`require_admin`)를 만든다(확인: 스펙 admin "운영 에이전트 대화 요청" 넷, "운영 에이전트 세션 끝내기", "운영 에이전트 최종 답"의 기록 둘, chat-sessions "세션 종류"의 나머지 셋의 테스트, 가짜 LLM)

## 7. 평가 틀 (design 결정 12, LLM 없음)

- [x] 7.1 `evals/admin_agent/fixture.py`에 평가 기관(약 40개 서명, 고정일 2026-11-19)을 만든다(확인: 스펙 admin-agent-evals "평가 기관" 둘의 테스트)
- [x] 7.2 시나리오 23개와 라벨(기대 호출, 있어야 할 숫자, 기대 종류, 추적)을 Claude가 쓰고 사람에게 전부 보여 확인받는다(확인: "시나리오 라벨" 스펙 추적 테스트, 사람 확인을 design "결과"에 적음)
- [x] 7.3 채점(부분 일치 tool 선택, 숫자 추출과 충실도, 종류 일치)과 결과 폴더·`summary.md`·종료 코드를 만든다(확인: "시나리오 라벨" 부분 일치, "평가 지표" 셋, "평가 실행과 결과" 요약 파일의 테스트, 가짜 LLM)
- [x] 7.4 `evals/admin_agent/README.md`에 실행 명령과 지표를 적는다(확인: 적힌 명령이 가짜 LLM으로 그대로 돈다)

## 8. 평가 실행 (실제 LLM, 승인 뒤)

- [x] 8.1 시나리오 수, 예상 호출 수·토큰·비용을 세어 알리고 승인을 받는다. 승인이 없으면 8.2를 하지 않는다(확인: 승인 기록을 design "결과"에 적음)
- [x] 8.2 `uv run python -m evals.admin_agent`를 두 번 돌려 지표 세 개와 틀린 시나리오를 design "결과"에 적는다. 프롬프트를 고치면 버전을 올리고 다시 두 번 돈다(확인: run 이름 둘, 지표별 맞은 수, 실제 사용량)

## 9. 마지막 점검과 문서

- [x] 9.1 모든 스펙 delta 시나리오가 테스트(docstring에 `[capability] 요구사항 / 시나리오`) 또는 평가 시나리오(`traces`)에 있는지 표로 확인한다(확인: design "결과"의 시나리오 표)
- [x] 9.2 `docs/design.md`(운영 에이전트 tool 표, 자연어 SQL 보류), `docs/glossary.md`(분야, 분석 축), `app/library/README.md`, `app/features/README.md`, `CLAUDE.md`(현재 단계, 평가 명령)를 고친다(확인: tool 표가 코드와 같음, `run_analytics_query`가 "보류"로 표시됨)
- [x] 9.3 `uv run pytest`(테스트 DB `VACUUM ANALYZE` 뒤), `uv run ruff check . && uv run ruff format --check .`(확인: 모두 통과, 통과 수를 결과에 적음)

## Workflow follow-up

- archive 전에 `docs/roadmap.md` 20번 줄(내용·완료 기준·상태)과 미룬 일(자연어 SQL, `list_overdue_loans`·안내문 초안, 회원 연락처, 임의 기간·강목, 최근 들어온 책)을 고친다.
- 사람이 확인한 뒤 `/opsx:archive`로 `openspec/specs/`에 반영한다.
