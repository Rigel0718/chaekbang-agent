## Why

작은도서관 담당자는 희망도서와 많이 빌리는 책을 보고 동네 책방에 보낼 보충 구매 목록을 손으로 만들고, 예산과 보고에 쓸 금액도 따로 계산한다. 희망도서(`book_requests`)가 `add-librarian-actions`에서 생겨 구매 근거가 모였고, 구매 요청서 확정은 설계 원칙 3의 확정 작업 중 아직 없는 마지막 종류다. 공통 승인 틀의 확정하는 종류(`CONFIRMING`)를 그대로 쓴다.

정가는 이용자에게 보여 주는 서비스 정보가 아니라 **예산 추정과 공적 보고를 위한 기록**이다. 가격이 바뀔 수 있어서 초안을 보는 동안에는 YES24 정가를 실시간으로 조회만 하고 저장하지 않으며, 승인하는 순간 다시 조회해 계산한 금액을 확정본에 기록한다. 금액은 코드가 계산하고 LLM은 보지 않는다.

## What Changes

- **보충 구매 요청서**: 기관별 요청서(제목, 납품처 이름·메모 선택)와 항목(ISBN 필수, 서명, 저자, 권수 1~10, 근거 종류 필수, 근거 한 줄 선택). 항목은 1~30개이고 요청서 안에서 ISBN이 겹치지 않는다. 회원 값은 없다.
  - 승인 틀의 `CONFIRMING`: 만들기·고치기·삭제(`draft`만), 제출, 승인(→ `confirmed`), 반려. 내리기는 없다. 확정본은 고치거나 지울 수 없다.
  - 관리자 REST: 목록·상세·만들기·고치기·삭제·제출·승인·반려와 후보 목록. 키오스크는 403.
- **정가 조회와 금액 기록**: 운영자 층에 ISBN별 정가 조회 접점을 두고 YES24 상품 상세의 정가(`shopPrice`)로 구현한다. 초안·승인 대기 상세는 조회한 정가로 항목 금액(정가 × 권수)과 추정 총액을 응답에만 담는다. 승인은 트랜잭션 밖에서 모든 항목을 다시 조회한 뒤, 같은 트랜잭션에서 항목 정가·금액, 총액, 조회 시각, 가격 출처를 기록하고 확정한다. 정가를 찾지 못한 항목이 있으면 409, 조회를 쓸 수 없으면 503이고 아무것도 바뀌지 않는다. 판매가·판매 상태·응답 원본은 저장하지 않는다.
- **구매 후보**: 희망도서(처리 전, ISBN 있음, 지금 소장 안 함, ISBN별로 묶어 신청 건수. ISBN 없는 신청은 건수만), 인기(자체 대출 기관은 기간 대출 순위, 외부 대출 기관은 가져온 파일의 대출 중 상태와 기준 시각), 분야별 권수·권당 대출 숫자. 회원 값과 가격은 없다.
- **희망도서 닫기**: 희망도서에 요청서 연결 칸을 더한다. 확정하면 같은 기관에서 확정본 항목과 ISBN이 같은 처리 전 신청을 모두 닫고 그 요청서를 가리키게 한다. 희망도서 상태 값은 그대로 둘이다.
- **운영 에이전트 v4**: `list_purchase_candidates`와 `draft_purchase_request`(후보에 있는 ISBN만, 근거 종류는 코드가 정함, 바로 승인 대기)를 두 운영 방식 프로필에 더한다. tool 결과에 금액이 없고 YES24를 부르지 않는다. 희망도서를 "데이터 없음"의 예에서 뺀다.
- **평가**: `evals/admin_agent`에 구매 요청서 시나리오 5개(후보, 초안, 예산 질문, 승인 요청, 외부 대출 기관)와 초안 충실도의 요청서 판정.
- **범위 밖**: 관리자 화면(`add-web-ui`), CSV·PDF 내보내기와 발송, 확정 취소, 할인율·실제 납품가, 예산 상한, ISBN 없는 항목, 승인하면서 항목 빼기, 부족 분야의 책 추천, 외부 대출 기관의 대출 기록 파일 가져오기, 정보나루 인기 근거, 도착 알림, 납품처 관리.

## Capabilities

### New Capabilities

- `library/purchase-requests`: 요청서와 항목의 내용 규칙, 승인(확정)과 확정본 불변, 정가 조회와 금액 계산·기록, 조회 실패 처리, 구매 후보, 확정 때 희망도서 닫기, 기관 분리

### Modified Capabilities

- `circulation/book-requests`: 관리자 목록 줄에 요청서 연결 값을 더하고, 요청서 확정으로 닫히는 경우를 정함
- `agent/admin`: 두 운영 방식 프로필에 구매 후보·요청서 초안 tool을 더함, 두 tool의 계약(후보 ISBN만, 금액·회원 값 없음), 회원 값 카나리아, 구매 요청서 요청에 답하는 동작과 구매 요청서 승인 요청 안내(평가)
- `platform/admin-agent-evals`: 구매 요청서 시나리오의 기관 데이터, 라벨, 초안 충실도 판정
- `platform/database-schema`: 테이블 26개에서 28개(`purchase_requests`, `purchase_request_items`)로, 희망도서의 요청서 연결 칸

## Impact

- 코드: 새 `app/central/list_prices.py`(정가 조회 접점과 YES24 구현), 새 `app/library/models/purchase_request.py`, 새 `schemas/purchase_request.py`, 새 `services/purchase_requests.py`(후보 포함), 새 `api/purchase_requests.py`, 새 `app/library/purchase_tools.py`, `app/library/models/book_request.py`·`schemas`·`services/book_requests.py`(연결 칸), `app/library/admin_agent.py`(v4, 프롬프트), `app/main.py`(조회기 조립), `app/models.py`(`TENANT_TABLES`)
- DB: 마이그레이션 하나. `purchase_requests`, `purchase_request_items`, `book_requests.purchase_request_id`
- API: 새 `/purchase-requests` 경로들과 `GET /purchase-requests/candidates`, 관리자 희망도서 목록 줄에 `purchase_request_id`
- 외부 호출: YES24 상품 상세(관리자 요청서 상세와 승인 때만, 항목 수만큼, 0.2초 간격). pytest는 가짜 조회기를 쓰고, 실제 확인은 apply 끝에 약 10회로 승인 뒤
- LLM: 평가 실행만(새 시나리오 약 15~20회, 운영 평가 전체 회귀 약 120~150회). 호출 수를 알리고 승인을 받은 뒤 한다
- 문서: `docs/design.md`(tool 표, 구매 요청서의 의미, 테이블 목록), `docs/data-sources.md`·`app/central/README.md`(YES24 정가 조회 예외), `docs/backlog.md`(가격 조회를 옮김), `docs/glossary.md`(보충 구매 요청서), `docs/roadmap.md`(23b 상태, 미룬 일), `CLAUDE.md`(현재 단계), `app/library/README.md`, `evals/admin_agent/README.md`
