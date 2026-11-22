## Context

- **지금 상태**
  - 공통 승인 틀(`app/library/approval.py`)에는 `CONFIRMING`(실행 상태 `confirmed`, 내리기 없음), 조건부 갱신 `transition`, `mark_executed`, `ApprovalMixin`이 있다. 확정하는 종류는 연체 안내문 틀이 처음 썼다(`services/overdue_notices.py`).
  - 희망도서(`models/book_request.py`)는 `requested`/`closed`이고, 소장 검사는 `recommendable_ids`와 ISBN으로 한다(`services/book_requests.py`의 `_is_held`).
  - 대출 순위는 `services/analytics.py`의 `book_facts`·`_ranking`이 기관 도서 단위로 세지만 결과(`RankedBook`)에 ISBN과 사본 수가 없다. 외부 대출 기관은 `loans`가 비고, 사본마다 가져온 상태(`holdings.status`)와 `last_synced_at`만 있다.
  - YES24 호출은 `app/central/external/yes24/`에 있고 상품 상세 `get_items_by_isbn`, 호출 간격 `RateLimiter`(0.2초), 중단 예외 `Yes24Stopped`를 쓴다. 지금은 운영자 채움(`scripts/enrich_books.py`)만 부른다. 설정에 `yes24_api_key`(선택)가 있다.
  - 운영 에이전트는 admin v3이고, 프롬프트가 희망도서를 `no_data` 예로 든다(`admin_agent.py`). tool 실행 기록은 `record_fields`로 고른 맨 위 입력만 남는다.
- **제약**: MVP 출시가 우선이다. 정가는 예산·공적 보고용 기록이고 서비스 정보가 아니다(탐색 때 사용자 결정). YES24 이용 조건상 판매가·판매 상태는 저장하지 않는다.

## Goals / Non-Goals

**Goals:**

- 승인 틀 코드를 바꾸지 않고 `CONFIRMING` 종류를 하나 더한다.
- 확정본의 금액은 승인 순간 조회한 정가로 코드가 계산한 값과 같다(완료 기준). 확정 전에는 가격을 어디에도 저장하지 않는다.
- 회원 값과 금액이 LLM에 가지 않는 것을 tool 결과의 필드로 보장한다.

**Non-Goals:**

- 가격 캐시, 카카오 대체 출처, 할인·실제 납품가, 예산 상한.
- 관리자 화면, 내보내기·발송, 확정 취소, 승인하면서 항목 빼기.
- 소장하지 않은 책의 외부 후보(부족 분야의 책 추천).

## Decisions

### 1. 정가 조회는 운영자 층의 접점 하나

`app/central/list_prices.py`에 접점 `ListPriceLookup`(`async lookup(isbns) -> dict[str, int | None]`)과 예외 `PriceLookupUnavailable`, YES24 구현 `Yes24ListPrices`를 둔다.

- YES24 구현은 ISBN마다 `get_items_by_isbn`을 부르고, 같은 ISBN13 상품의 `list_price`(이미 `shopPrice`를 `parse_price`로 읽는 값)만 쓴다. 0이나 없음은 `None`이다. `Yes24Stopped`(한도, 인증, 장애)와 시간 초과는 `PriceLookupUnavailable`로 바꾼다. 받은 상품은 함수 밖으로 내보내지 않는다.
- 호출 간격 제한은 프로세스에 하나를 두고 함께 쓴다(여러 관리자가 동시에 상세를 열어도 0.2초 간격).
- `app/main.py`가 설정의 키로 조회기를 만들어 앱 상태에 둔다. 키가 없으면 항상 `PriceLookupUnavailable`을 내는 조회기를 둔다. 라우터는 의존성(`get_list_prices`)으로 받고, 테스트는 가짜 조회기로 바꾼다.
- **고른 이유**: 기관 공통은 운영자 층을 import해도 되지만 반대는 안 된다(층 규칙). 임베딩 인코더처럼 접점을 두면 pytest가 외부 호출 없이 돈다.
- **버린 안**: 저장된 `books.list_price`로 먼저 계산. 사용자가 실시간 정가를 정했고, 소장하지 않은 희망도서에는 공식 서지가 없다.

### 2. 테이블 둘과 희망도서 연결 칸

- `purchase_requests`: `library_id`, 제목, 납품처 이름, 메모, `ApprovalMixin`, 확정 때만 채우는 `total_amount`(int), `priced_at`, `price_source`(StrEnum, 값 `yes24_list_price` 하나).
- `purchase_request_items`: `library_id`, `purchase_request_id`, 순서, ISBN, 서명, 저자, 권수, `reason_kind`(StrEnum 넷), 근거 한 줄, 확정 때만 채우는 `unit_price`·`amount`(int). `(library_id, purchase_request_id)` 복합 FK(큐레이션 항목과 같은 방식), `UNIQUE(purchase_request_id, isbn)`, 권수 1~10과 금액 0 이상 CHECK.
- `book_requests.purchase_request_id`(nullable): `(library_id, purchase_request_id)` 복합 FK, `ON DELETE RESTRICT`. 확정본은 지울 수 없으니 실제로 걸리지 않는다.
- 항목은 희망도서나 기관 도서 id를 갖지 않는다. 항목의 식별은 ISBN이고, 어떤 신청에서 왔는지는 신청 쪽 칸이 답한다. 같은 ISBN 신청 여러 건을 항목 하나에 잇기 위해서다(탐색 결정 6).
- `app/models.py`의 `TENANT_TABLES`에 두 테이블을 더한다.

### 3. 금액 계산은 순수 함수 하나

`price_items(items, prices) -> Priced`(항목별 단가·금액, 합계, 가격 없는 ISBN 목록)를 상세와 승인이 함께 쓴다. 모두 `int`이고 금액은 `단가 * 권수`, 합계는 `sum`이다. 테스트는 이 함수의 결과를 손으로 계산한 상수와 비교하고, 같은 함수를 기대값 계산에 쓰지 않는다.

### 4. 승인: 조회는 트랜잭션 밖, 기록은 짧은 트랜잭션

`approve_purchase_request`는 다음 순서다.

1. 요청서와 항목을 읽는다. `pending_approval`이 아니면 409. 읽기 트랜잭션을 끝낸다(`rollback`).
2. 항목 ISBN의 정가를 조회한다. `PriceLookupUnavailable`이면 503, 가격 없는 ISBN이 있으면 409(메시지에 ISBN). DB는 바뀌지 않았다.
3. 새 트랜잭션에서 `transition(APPROVE)`(조건부 갱신) → 항목을 다시 읽어 1번의 (ISBN, 권수) 집합과 같은지 확인(다르면 409, 되돌림) → 항목 단가·금액, 총액, `priced_at`, `price_source` 기록 → 같은 ISBN 희망도서 닫기 → `mark_executed` → 커밋.

- **고른 이유**: 30항목이면 조회가 약 6초다. 그동안 DB 트랜잭션을 열어 두지 않는다. 겹친 승인은 조건부 갱신이 하나만 통과시킨다. 조회하는 사이에 반려·수정·재제출이 끼어들면 3번의 비교가 잡는다.
- **버린 안**: 행을 `SELECT … FOR UPDATE`로 잡고 조회. 외부 호출 동안 잠금이 남는다.

### 5. 상세의 추정 금액

`GET /purchase-requests/{id}`는 확정 전이면 1번 접점으로 조회하고 `price_items` 결과를 응답 스키마에만 담는다(`estimated_total`, `missing_price_count`, `priced_at`, `price_unavailable`). 조회기가 `PriceLookupUnavailable`을 내면 금액을 비우고 `price_unavailable=true`로 200이다. 확정본은 기록한 칸을 그대로 돌려준다. 목록 GET은 조회하지 않는다.

### 6. 후보 service 하나, 출구 둘

`purchase_candidates(session, library_id, period)`가 결과 모델 하나를 만들고 REST(`GET /purchase-requests/candidates`)와 tool이 함께 쓴다.

- **희망도서**: `requested`, ISBN 있음, 그 ISBN이 `_is_held`가 아님. ISBN별로 묶어 신청 건수, 서명·저자는 가장 이른 신청의 값. 줄 순서는 신청 건수 → 가장 이른 신청 시각 → ISBN. ISBN 없는 처리 전 신청은 건수만.
- **인기(자체 대출)**: `book_facts`와 기간 해석(`resolve_period`)을 그대로 쓰고, 표시 ISBN(공식 서지 먼저, 없으면 기관 도서)이 있는 추천 가능한 책만 대출 수 순으로 10권. 줄에 대출 수, 제적을 뺀 사본 수, 대출 중 수. 같은 수는 `korean_order` → id.
- **인기(외부 대출)**: 기간을 쓰지 않는다. 제적을 뺀 사본 중 `on_loan`이 1권 이상인 책을 대출 중 비율 → 대출 중 수 → `korean_order` 순으로 10권. 줄에 사본 수, 대출 중 수, 그 책 사본의 가장 늦은 `last_synced_at`.
- **분야 숫자**: 기존 `collection_status(group_by=field)`의 분야별 권수와, 자체 대출이면 `loan_stats(group_by=field)`의 권당 대출을 그대로 싣는다.
- 결과 모델의 필드는 허용 목록 상수로 고정하고 pytest로 지킨다(분석 tool과 같은 방식). 회원 칸과 가격 칸이 없다.

### 7. 운영 에이전트 tool과 v4

- `list_purchase_candidates`: 입력 `period`(선택, 기본 `last_90_days`, 외부 대출 기관에서는 무시). 결과는 6번 모델 그대로.
- `draft_purchase_request`: 입력 `title`, `note`(선택), `period`(선택, 후보를 다시 계산할 기간), `items[{isbn, quantity, reason?}]`. tool이 같은 기간으로 후보를 다시 계산해, 항목 ISBN이 희망도서 후보나 인기 후보에 없으면 오류 결과를 준다. 서명·저자·`reason_kind`는 후보에서 코드가 채운다(희망도서 먼저). 그다음 REST와 같은 `create_purchase_request(..., submit=True)`를 부른다. 결과는 `purchase_request_id`, `status`, `item_count`, 안내 `note`이고 금액이 없다. `record_fields=("items",)`.
- 두 운영 방식 프로필에 모두 넣는다. `PROFILE_VERSION = "v4"`.
- 프롬프트: 희망도서를 `no_data` 예에서 빼고 "구매 요청서" 절(후보 먼저, 후보에 없는 책 금지, 금액·예산 숫자 말하지 않고 관리 화면 안내, 승인 대기 안내)을 더한다. 승인 불가 목록에 구매 요청서를 더한다. 외부 대출 절에 "인기는 가져온 파일 기준이고 기준 시각을 말하며 대출 수를 말하지 않는다"를 더한다.
- **버린 안**: LLM이 근거 종류를 고르게 하기. 근거 종류는 후보 출처로 정해지는 사실이라 코드가 한다(원칙 7).

### 8. 평가

- 분석 평가 기관에 희망도서 5건(서로 다른 ISBN 둘, 같은 ISBN 두 건, ISBN 없는 한 건)을 더한다. 희망도서는 장서·대출 숫자에 들어가지 않으므로 기존 라벨은 그대로여야 하고, 기존 분석 시나리오의 기대 호출을 코드로 불러 확인한다.
- 큐레이션 평가 기관의 외부 대출 기관에 회원 하나, 희망도서 두 건, 가져온 파일 기준 `on_loan` 사본을 더한다. 큐레이션 라벨이 바뀌지 않는지 같은 방법으로 확인한다.
- 시나리오 5개: `purchase-candidates`, `purchase-draft`, `purchase-budget`, `purchase-approve`, `purchase-external`. 초안 충실도에 요청서 판정(항목 ISBN ⊆ 그 턴의 구매 후보 결과, 회원 값 없음, 승인 대기 낱말)을 더한다.
- LLM 호출: 새 5개 약 15~20회, 운영 전체 회귀 1회 약 120~150회. apply 때 호출 수를 알리고 승인을 받는다.

### 9. 문서

- `docs/design.md`: tool 표의 `list_purchase_candidates`·`draft_purchase_request`, "구매 요청서의 의미"에 정가 실시간 조회와 확정 때 기록, 테이블 목록.
- `docs/data-sources.md`, `app/central/README.md`: YES24는 구매 요청서 항목의 ISBN도 상품 상세로 조회하되 정가만 읽고 저장은 확정본의 금액 기록뿐이라는 예외. 판매가·판매 상태는 그대로 저장하지 않는다.
- `docs/backlog.md`: "구매 요청서를 쓸 때의 최신 가격 조회"를 지운다. `docs/glossary.md`: 보충 구매 요청서는 YES24 정가 기준 예정 금액.
- archive 때 `docs/roadmap.md`(23b 상태, 확정된 기본값, "`add-purchase-request`에서 미룸")와 `CLAUDE.md` 현재 단계.

## Risks / Trade-offs

- [YES24 장애나 한도로 승인이 막힘] → 503으로 아무것도 바꾸지 않고 다시 시도하게 한다. 하루 한도 20,000회에 비해 요청서 호출은 작다.
- [초안 추정과 확정 금액이 다름] → 응답에 조회 시각을 담는다. 차이 표시는 개선 사항이다.
- [YES24에 없는 책(독립출판 등)은 확정할 수 없음] → 409에 ISBN을 담아 관리자가 그 항목을 빼게 한다. 카카오 대체 출처는 개선 사항이다.
- [상세를 열 때마다 항목 수만큼 호출해 느림(30항목 약 6초)] → 상한 30개. 짧은 캐시는 개선 사항이다.
- [외부 대출 기관의 인기 근거가 한 시점의 상태라 약함] → 근거 이름과 기준 시각을 따로 보여 주고 대출 수처럼 말하지 않게 한다. 대출 기록 파일 가져오기는 개선 사항이다.
- [평가 기관에 데이터를 더해 기존 라벨이 흔들림] → 기존 시나리오의 기대 호출을 코드로 불러 숫자가 같은지 pytest로 먼저 확인한다.

## Migration Plan

- 마이그레이션 하나: 두 테이블 생성, `book_requests.purchase_request_id` 추가(기존 행은 NULL). downgrade는 칸과 테이블을 지운다.
- 개발 DB는 적용 전에 `pg_dump`로 백업하고 명령을 `&&`로 잇는다.
- 실제 YES24 확인은 apply 끝에 개발 DB 자체 대출 기관에서 ISBN 3~5개 요청서의 상세 한 번과 승인 한 번(약 10회)으로 하고, 호출 전에 승인을 받는다. 확인용 행은 지운다.

## 미룰 것

archive 때 `docs/roadmap.md`의 "`add-purchase-request`에서 미룸"으로 옮긴다(2026-11-22 탐색, MVP 우선이라 개선 사항으로 둠).

- 화면: 관리자 요청서 목록·상세·승인 화면 → `add-web-ui`
- 기록: CSV·PDF 내보내기, 책방 발송, 확정 취소, 확정본 복사로 새 초안, 상세의 "해결한 신청 n건"
- 금액: 할인율·실제 납품가, 예산 상한 경고, 카카오 정가 대체 출처, 상세 조회의 짧은 캐시, 승인 직전 금액과 추정 금액의 차이 표시
- 항목: ISBN 없는 항목, 승인하면서 항목 빼기, 다른 초안에 이미 든 후보 표시, 기증 희망 표시
- 근거: 부족 분야의 책 추천(외부 후보), 복본 필요 문턱, 외부 대출 기관의 대출 기록 파일 가져오기, 정보나루 인기 대출 근거(`add-loan-signal-store` 뒤)
- 희망도서: "구매 중인 책" 신청 거부·안내, 도착 알림, 거절 사유
- 납품처 관리 테이블
- 에이전트: 예산에 맞춘 권수 조절, 초안 고치기 tool, 요청서 초안 품질 채점
- 평가: 운영 평가 전체 회귀(36개, 약 110~140회 호출). 이번에는 새 시나리오 5개만 돌렸다(2026-11-22 사용자 결정). 프롬프트 v4가 모든 시나리오에 걸리므로 다음 운영 에이전트 change 전에 한 번 돌린다

## 결과

- **0.1 기준(2026-11-22)**: `uv run pytest` 1895 통과·7 건너뜀·2 실패, `ruff check` 통과. 실패 2건(`test_scenarios_trace_admin_eval_requirements`, `test_scenarios_cover_eval_requirements`)은 이 change의 `agent/admin` delta가 "평가로 확인한다" 시나리오 5개를 더했는데 평가 시나리오가 아직 없어서 생긴 것이다(change 폴더를 치우면 둘 다 통과). 5.1에서 풀린다.
- **0~3 끝(2026-11-22, Sonnet 몫)**: `uv run pytest` 1978 통과·7 건너뜀·2 실패(0.1과 같은 2건, 5.1에서 풀림). 0.1보다 83개 늘었다. `ruff check`·`ruff format --check` 통과. 마이그레이션 `edf9ea084b6c`는 `upgrade`·`downgrade -1`·`upgrade`가 되고 `alembic check`에 차이가 없다. 개발 DB는 적용 전에 백업했다(scratchpad의 `chaekbang_before_purchase_request.dump`). 구현 중 정한 것 둘: ① 항목 테이블의 복합 FK 이름이 식별자 한도(63자)를 넘어 줄였다(`fk_purchase_request_items_library_id_request_id_requests`). ② 읽기 구간 정리는 `rollback`이 아니라 `commit`이다(테스트 세션이 savepoint 위라 `rollback`이 아직 커밋 전인 데이터를 되돌린다). 금액 계산을 일부러 망가뜨렸을 때(단가만 곱하지 않음) 7개, 소장 제외 규칙을 껐을 때 2개가 실패해 테스트가 그 규칙을 지키는 것을 확인했다.
- **4~5.1 끝(2026-11-22, Opus 몫)**: `uv run pytest` 1993 통과·7 건너뜀·실패 0(0.1의 추적 실패 2건이 5.1에서 풀림), `ruff` 통과. 구현 중 정한 것: ① 프롬프트의 외부 대출 문구 "인기 책을 알 수 없다"를 "기간별 대출 순위"로 바꿨다(가져온 파일 기준 인기 후보와 충돌). ② 프롬프트 예시에 숫자(날짜·권수)를 넣지 않았다(LLM이 따라 쓰면 숫자 충실도가 틀린다). ③ 예산 질문은 `unsupported=other`로 답하게 프롬프트에 적었다(라벨을 정하려고). ④ 평가 기관의 책에 가상 ISBN(`eval_isbn`)을 줬다. ISBN이 없으면 인기 후보가 비어서다. 분석 라벨 숫자가 그대로인지는 `test_wishes_do_not_change_analysis_labels`가 본다. ⑤ 두 후보에 모두 있는 ISBN은 사본이 모두 분실된 인기 책에서 생긴다(희망도서 소장 검사는 추천 가능한 책만 본다).
- **5.3 새 시나리오 5개(2026-11-22, `gpt-6-luna`, admin v4, 입력 59,967·출력 820 토큰)**: 4/5. 사용자 결정으로 전체 회귀는 돌리지 않았다. 틀린 `purchase-draft`는 답의 "최근 90일"이 결과에 없는 숫자였다. 원인은 `list_purchase_candidates` 입력 설명의 "null(최근 90일)"이다(LLM이 결과의 `period.label` 대신 설명 문구를 썼다). 설명에서 숫자를 빼고 "답에서 기간은 결과의 period.label로 말한다"를 넣었다.
  고친 뒤 `purchase-draft`만 다시 돌려 맞음(1/1, 입력 18,560·출력 558 토큰). 새 시나리오는 모두 맞았다. 운영 전체 회귀는 미룸(아래 "미룰 것"에 더함).
- **6.1 실제 YES24 확인(2026-11-22, 사용자 승인, 호출 10회)**: 개발 DB `햇살 작은도서관`에 실험 장서의 실제 ISBN 5개(권수 2·1·1·3·1)로 요청서를 만들어 상세 한 번(5회), 승인 한 번(5회). 상세 추정 총액·확정 총액·손 계산이 모두 107,000원(22,000 + 13,000 + 17,000 + 42,000 + 13,000)으로 같았고 항목 금액은 단가 × 권수와 같았다. 가격 출처는 `yes24_list_price`. 단가 5개는 저장돼 있던 `books.list_price`와 같았다(참고). 확인용 행은 SQL로 지워 요청서·항목·연결된 희망도서가 0건이다. 스크립트는 scratchpad에만 있고 저장소에 넣지 않았다.
- **6.3 최종(2026-11-22)**: `uv run pytest` 1993 통과·7 건너뜀·실패 0(0.1은 1895 통과·2 실패, 98개 늘었다), `ruff check`·`ruff format --check` 통과, `openspec validate --strict` 통과.
