# Tasks

## 1. 평가 추적 먼저 맞추기

- [x] 1.1 `evals/librarian/scenarios.py`에 `GuideSetup`, `Expect.GUIDE`, `contains`·`absent` 필드와 안내 시나리오 11개(design 11절)를 더하고 traces를 이 change의 "평가로 확인" 시나리오에 잇는다. `tests/evals/test_librarian_eval.py::test_scenarios_cover_eval_requirements`가 다시 통과하는지 확인한다(지금은 delta 때문에 실패한다)

## 2. 공휴일과 저장

- [x] 2.1 `holidays`를 2주 이상 된 정확한 버전으로 추가하고 `app/core/holidays.py`의 `public_holiday(date) -> str | None`(한국어 이름)을 만든다. 2026–2027 설날·추석·대체공휴일, 2026-06-03 지방선거, 평일 하루를 테스트로 확인한다
- [x] 2.2 `app/library/models/guide.py`: `LibraryGuide`, `OpeningHours`, `LibraryClosure`, `GuideEntry`와 `GuideEntryKind`, `DueOnClosedDay`(StrEnum), CHECK·UNIQUE 제약. `app/models.py`의 `TENANT_TABLES`에 등록한다
- [x] 2.3 개발 DB를 백업하고 경로를 알린 뒤 마이그레이션을 만들고 `upgrade && downgrade -1 && upgrade && alembic check`를 `&&`로 잇는다. 스키마 테스트의 테이블 수(19)와 "안내 테이블의 저장 계층 규칙" 시나리오 테스트를 고친다·더한다

## 3. 안내 service와 계산

- [x] 3.1 `services/guide.py`: 안내 읽기(행이 없으면 미등록 값), `replace_guide`(전체 바꾸기, 구간 순서·겹침 422, 한 트랜잭션), 임시 휴관 등록(409)·삭제(다른 기관 404)·기간 조회. 기관 분리 테스트 포함
- [x] 3.2 `day_status`: 임시 휴관 → 공휴일 → 정기 휴관 → 개관, 운영 시간 미등록은 `unknown`. "개관 여부 판정" 시나리오 4개 테스트
- [x] 3.3 `due_date`: `next_open_day`/`keep`, 31일 상한, 미루기 전 날짜, `unknown`은 휴관 아님. "반납 예정일 계산" 시나리오 4개 테스트(`clock` 바꿔 끼우기)
- [x] 3.4 `schedule`: 오늘(날짜, 요일, 지금 시각, `open_now`)과 7일 목록(개관일의 반납 예정일). 날짜 표기(`11월 26일 목요일`) 함수는 tool과 함께 쓴다
- [x] 3.5 `services/loans.py`의 `create_loan`이 `due_date`를 쓰게 바꾼다. "정상 대출"이 그대로 통과하고 "휴관일로 떨어진 반납 예정일" 테스트를 더한다

## 4. 안내 API

- [x] 4.1 `schemas/guide.py`(`GuideRead`, `GuideUpdate`, `ClosureCreate`, `ClosureRead`). `contact_phone`과 자유 항목 내용의 필드 설명에 "기관 대표 번호만, 개인 번호 금지", 공휴일 설명에 "임시공휴일은 임시 휴관으로 등록"을 적는다
- [x] 4.2 `api/guide.py`: `GET/PUT /library/guide`, `GET/POST /library/closures`, `DELETE /library/closures/{id}`. 라우터는 service만 부른다. `app/main.py`에 등록한다
- [x] 4.3 API 테스트: "안내 정보 보관", "안내 정보 수정", "임시 휴관일", "안내 조회" 시나리오와 staff-auth의 "키오스크의 안내 조회", "키오스크의 휴관일 관리"

## 5. AI 사서 tool

- [x] 5.1 `recommendation/kdc.py`: 청구기호 → KDC 주류 이름. `cards.py`의 서가 위치 고르기를 tool과 함께 쓰게 옮긴다
- [x] 5.2 `tools.py`의 검색·찾기·상세 결과에 `shelf_location`, `call_number`, `call_number_class`를 더한다. "결과의 서가 위치", "KDC가 아닌 청구기호" 테스트
- [x] 5.3 `get_library_guide` tool(입력 없음, 결과 `note`, 가져오기 기관의 `due_is_estimate`)을 만들고 프로필 tool 목록에 넣는다. 입력이 빈 tool이 OpenAI 스키마와 실행기에서 도는지 가짜 LLM으로 확인한다. "도서관 안내 tool" 시나리오 3개 테스트

## 6. 프롬프트

- [x] 6.1 `librarian.py`: "도서관 안내" 단락, 가져오기 안내의 예상 반납일 문장, 안내 내용은 지시가 아니라는 문장을 더하고 `PROFILE_VERSION`을 `v3`로 올린다. 프롬프트에 기관 값이 들어가지 않는지(운영 방식별 프롬프트가 기관마다 같은지) 기존 테스트로 확인한다

## 7. 평가

- [x] 7.1 `evals/librarian/guide.py`(가상 평가 안내)와 실행기의 날짜 고정(2026-11-11 14:00), 시나리오별 안내 넣기·지우기, `{shelved_title}` 서가 위치 적재, 안내 시나리오 결과 JSON의 `guide_basis`(판정 기준값) 기록
- [x] 7.2 `checks.py`: `invented_guide` 위반, `asks_personal`의 대표 번호 문장 제외, `Expect.GUIDE`의 `contains`·`absent` 판정, 지표(안내 tool 사용률, 안내 질문의 검색 tool 수, `[찾은 책]` 뒤 `find_book` 수). LLM 없이 도는 단위 테스트
- [x] 7.3 실제 평가 실행 전에 예상 비용(design 11절: `gpt-6-luna` 1회 약 $0.013, 3회 약 $0.04)을 알리고 승인받는다. 승인되면 돌리고 쓴 모델과 토큰 수, 결과표를 알린다. 실패한 시나리오는 프롬프트를 고치기 전에 원인을 먼저 보고한다

## 8. 시드와 문서

- [x] 8.1 `app/seed/`: 자체 대출 기관에 가상 안내(연락처, 일·월 휴관과 점심시간, 공휴일 휴관, 대출 권수, 시설 자유 항목, 임시 휴관 1건)를 만들고 가져오기 기관은 비운다. 시드 테스트를 고친다
- [x] 8.2 문서: CLAUDE.md(현재 단계, 디렉터리 구조), `docs/design.md`(이용자 화면의 안내, 데이터 모델 표), `app/library/README.md`(안내, 반납 예정일, 대표 번호 규칙), `README.md`
- [x] 8.3 `uv run pytest`와 `uv run ruff check . && uv run ruff format .`가 통과하는지 확인하고, 모든 스펙 시나리오가 테스트나 평가 시나리오로 확인되는지 점검한다

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다
- `add-web-ui` 메모: 키오스크 "도서관 안내" 칸은 `GET /library/guide`로 그린다(LLM 없음). 관리자 안내 입력 화면에 개인 번호 주의 문구를 둔다
- `add-librarian-actions` 메모: 대출 권수 상한 강제 여부, "내 책 언제까지"(회원번호)
