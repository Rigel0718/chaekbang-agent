순서: 1~3은 LLM 없이 정가 조회, 요청서, 승인·확정, 후보를 끝까지 만들고, 4는 운영 에이전트에 잇고, 5는 평가, 6은 문서와 마무리다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

모델 분리: **0~3·6은 Sonnet, 4~5는 Opus**(tool·프롬프트·카나리아·평가). 넘칠 때 나누는 경계도 3과 4 사이다.

## 0. 시작 전 기준 (Sonnet)

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 저장과 정가 조회 (Sonnet, design 결정 1·2, Migration Plan)

- [x] 1.1 새 `app/library/models/purchase_request.py`(`purchase_requests`, `purchase_request_items`, `ReasonKind`·`PriceSource` StrEnum, 복합 FK, `UNIQUE(purchase_request_id, isbn)`, 권수·금액 CHECK)와 `BookRequest.purchase_request_id`(복합 FK, RESTRICT)를 만들고 `app/models.py`의 `TENANT_TABLES`에 넣는다. 마이그레이션을 만들고 개발 DB를 백업한 뒤 `&&`로 업그레이드한다(확인: 스펙 database-schema "빈 DB에 upgrade"(28개), "희망도서의 구매 요청서 칸", "구매 요청서 테이블의 저장 계층 규칙"의 테스트, `alembic downgrade -1 && alembic upgrade head`가 됨)
- [x] 1.2 새 `app/central/list_prices.py`(`ListPriceLookup`, `PriceLookupUnavailable`, `Yes24ListPrices`: 같은 ISBN13 상품의 정가만, 0·없음은 None, `Yes24Stopped`·시간 초과는 Unavailable, 공유 호출 간격)와 키 없을 때의 조회기, 테스트용 가짜 조회기를 만든다. YES24 응답은 기존 응답 고정 파일 꼴로 가짜 HTTP를 쓴다(확인: 스펙 purchase-requests "정가만 씀", "다른 ISBN 상품"의 테스트, 층 규칙 테스트 통과)

## 2. 요청서와 승인·확정 (Sonnet, design 결정 2~5)

- [x] 2.1 `app/library/schemas/purchase_request.py`와 `services/purchase_requests.py`의 만들기·고치기·지우기·목록·제출·반려를 만든다(항목 규칙, ISBN 정규화, `require_status(DRAFT)`, `CONFIRMING`)(확인: 스펙 purchase-requests "정상 만들기", "제목 누락", "외부 대출 기관", "ISBN 정규화", "잘못된 ISBN", "같은 ISBN 두 번", "항목 수와 권수", "근거 한 줄 없음", "초안 고치기", "승인 대기 고치기", "제출과 반려", "초안 승인"의 테스트)
- [x] 2.2 금액 순수 함수 `price_items`와 상세의 추정 금액(저장 안 함, 장애면 `price_unavailable`)을 만든다(확인: 스펙 purchase-requests "추정 금액", "가격 없는 항목", "저장하지 않음", "목록은 조회하지 않음", "조회 장애 상세", "공식 서지 정가를 쓰지 않음"의 테스트. 기대 금액은 손으로 계산한 상수)
- [x] 2.3 승인(읽기 → 트랜잭션 밖 조회 → 조건부 갱신·항목 재확인·금액 기록·희망도서 닫기·`mark_executed`)을 만든다(확인: 스펙 purchase-requests "기록한 금액", "상세 뒤 가격이 바뀜", "가격 없는 항목 승인", "조회 장애 승인", "겹친 승인", "확정본 고치기", "확정본 상세", "같은 ISBN 신청 둘", "직접 넣은 항목", "닫지 않는 신청", "다른 기관의 같은 ISBN"의 테스트, 조회 중 반려·재제출이 끼면 409인 테스트)
- [x] 2.4 희망도서 관리자 목록 줄에 `purchase_request_id`를 더한다(확인: 스펙 book-requests "닫기", "요청서로 닫힌 신청"의 테스트, 기존 희망도서 테스트 통과)
- [x] 2.5 `app/library/api/purchase_requests.py`(경로 9개, `require_admin`, 조회기 의존성)를 만들고 `app/main.py`에서 조회기를 조립·등록한다(확인: 스펙 purchase-requests "키오스크", "다른 기관 요청서"의 테스트)

## 3. 구매 후보 (Sonnet, design 결정 6)

- [x] 3.1 `purchase_candidates`(희망도서 ISBN별 묶기·소장 제외·ISBN 없는 건수, 자체 대출 인기 순위, 외부 대출 대출 중 비율과 기준 시각, 분야 숫자, 허용 목록 필드)와 `GET /purchase-requests/candidates`를 만든다(확인: 스펙 purchase-requests "ISBN별 묶기", "신청 뒤 소장한 책", "ISBN 없는 신청", "회원 값 없음", "자체 대출 기관의 인기 후보", "외부 대출 기관의 인기 후보", "ISBN 없는 인기 책", "다른 기관 목록과 후보"의 테스트)
- [x] 3.2 `app/library/README.md`의 승인 흐름 절에 구매 요청서(정가 조회 접점, 확정 때 기록, 희망도서 닫기, 후보)를 적는다(확인: README에 구매 요청서 절이 있음)

## 4. 운영 에이전트 v4 (Opus, design 결정 7)

- [x] 4.1 새 `app/library/purchase_tools.py`에 `list_purchase_candidates`와 `draft_purchase_request`(후보 재계산으로 ISBN 검사, 근거 종류·서명·저자는 코드가, `submit=True`, `record_fields=("items",)`, 결과에 금액 없음, 조회기 안 씀)를 만든다(확인: 스펙 admin "구매 후보 tool" 둘, "구매 요청서 초안 tool" 넷의 테스트, 가짜 LLM)
- [x] 4.2 두 운영 방식 프로필에 두 tool을 넣고, 프롬프트(희망도서를 `no_data` 예에서 뺌, 구매 요청서 절, 승인 불가 목록, 외부 대출 인기 문구)를 고치며 v4로 올린다(확인: 스펙 admin "운영 방식별 tool" 셋의 테스트, 기존 운영 에이전트 테스트 통과)
- [x] 4.3 카나리아 테스트: 카나리아 회원이 희망도서를 신청한 기관에서 가짜 LLM이 두 tool을 부른 운영 대화 한 번 뒤, 가짜 LLM이 받은 모든 요청과 `agent_runs`·`agent_steps`·대화 기록·요청서·항목 행을 검사한다(확인: 스펙 admin "카나리아 신청 회원"의 테스트)

## 5. 평가 (Opus, design 결정 8, 스펙 admin-agent-evals)

- [x] 5.1 평가 기관에 희망도서와 외부 대출 기관의 대출 중 사본을 더하고, 시나리오 5개(`purchase-candidates`, `purchase-draft`, `purchase-budget`, `purchase-approve`, `purchase-external`)와 라벨(요청서 기대, 승인 대기 낱말), 초안 충실도의 요청서 판정을 더하며 README를 고친다(확인: 스펙 admin-agent-evals "되돌림", "같은 데이터", "희망도서가 분석 숫자를 바꾸지 않음", "스펙 추적", "기대하지 않은 초안", "후보에 없는 요청서 항목", "예산 숫자"의 테스트, 가짜 LLM)
- [x] 5.2 사람 확인: 새 라벨 5개를 사용자가 본다(확인: 사용자 확인 기록. 2026-11-22 고칠 곳 없이 "새 5개만 실행" 승인)
- [x] 5.3 실제 LLM 실행: 호출 수를 알리고 승인을 받은 뒤 새 시나리오 5개, 그다음 `evals.admin_agent` 전체를 한 번 돌려 design "결과"에 적는다(확인: 새 시나리오 모두 맞음, 전체가 지난 결과보다 나빠지지 않음. 사용자 결정으로 새 5개만: 4/5 → tool 설명 수정 뒤 `purchase-draft` 재실행 맞음. 전체 회귀는 design 미룰 것)

## 6. 문서와 마무리 (Sonnet)

- [x] 6.1 실제 YES24 확인: 호출 수(약 10회)를 알리고 승인을 받은 뒤 개발 DB 자체 대출 기관에서 ISBN 3~5개 요청서의 상세 한 번과 승인 한 번을 하고 확인용 행을 지운다(확인: 상세 추정 총액과 확정 총액이 손 계산과 같음, design "결과"에 기록)
- [x] 6.2 `docs/design.md`(tool 표, 구매 요청서의 의미, 테이블 목록), `docs/data-sources.md`·`app/central/README.md`(YES24 정가 조회 예외), `docs/backlog.md`(가격 조회 항목 지움), `docs/glossary.md`(보충 구매 요청서)를 고친다(확인: 문서에 각 항목이 있음)
- [x] 6.3 전체 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`를 돌린다(확인: 모두 통과, 0.1보다 테스트 수가 늘어남)

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive하고 `docs/roadmap.md`의 23b 상태, 확정된 기본값, "`add-purchase-request`에서 미룸"(design "미룰 것")을 고친다.
- `CLAUDE.md` "현재 단계"를 다음 change로 바꾼다.
