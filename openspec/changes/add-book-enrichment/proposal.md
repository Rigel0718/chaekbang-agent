# Proposal

## Why

가져온 장서에는 소개·표지가 없고, 파일에 어린이 표시가 없는 기관은 어린이 도서 대부분이 `general`로 남는다. 3주차 AI 사서가 데이터만으로 추천 이유를 말하고 어린이 요청에 답하려면, 소장 도서의 서지정보와 외부 분류 근거를 먼저 채워야 한다.

## What Changes

- **YES24 연동**
  - `app/external/yes24/`에 호출 코드를 둔다. 엔드포인트와 응답 필드는 정의 파일 한곳에 모은다.
  - 이번에 쓰는 기능은 상품 상세 조회(`itemDetail`, ISBN 기준) 하나다.
  - 키는 `.env`의 `YES24_API_KEY`에서만 읽고, 응답·로그·오류 메시지에 남기지 않는다.
- **서지정보 채움**
  - 관리자가 실행하면 로그인한 기관이 소장한 도서 중 처리 대기인 도서를 정해진 건수만큼 처리한다.
  - 출판사, 출간일, 정가, 소개, 표지 URL은 비어 있을 때만 채운다.
  - 부제, 쪽수, 목차, 시리즈명, 상품 링크, YES24 분류 값을 새로 보관한다.
  - 응답의 ISBN이 요청과 다르면 채우지 않는다.
- **외부 분류 근거**: 근거 `external_category`를 추가한다. YES24 분류 값이 정확히 `국내도서-유아`나 `국내도서-어린이`이고 성인물이 아니면 어린이 도서로 판단한다. 우선순위는 `manual`, `import_label`, `external_category`, `default` 순이다.
- **처리 상태와 현황**: 도서마다 처리 상태와 시각을 저장해 중단돼도 이어서 처리한다. 관리자는 기관별 처리 현황을 볼 수 있다.
- **호출 한도 대응**: 장서 가져오기 적용은 외부 API를 호출하지 않는다. 호출 속도를 제한하고, 한도 초과나 외부 장애가 나면 그 실행을 멈춘 뒤 남은 도서를 대기 상태로 둔다.
- **YES24 이용 조건 반영**
  - 소장 도서만 조회한다. 베스트셀러나 카테고리를 돌며 도서 정보를 쌓는 기능은 만들지 않는다.
  - 판매가와 판매 상태는 저장하지 않는다. 표지는 원본 URL만 저장한다.
  - 도서 조회 응답에 출처와 상품 링크를 함께 돌려준다.

**범위 밖 (이번 change에서 하지 않음)**

- ISBN 없는 도서의 제목 검색 매칭. 전집은 표본에서 대부분 ISBN이 없었다
- 상품 검색(`itemList`), 작가 정보(`author`) → `add-librarian-agent`에서 필요할 때
- 베스트셀러, 카테고리 목록을 쓰는 추천·큐레이션 근거
- 도서관 정보나루 연동 → 문서를 받은 뒤 별도 change
- 이미 채운 도서의 주기적 갱신, 구매 요청서를 위한 최신 가격 조회 → 구매 요청서 change에서
- 백그라운드 작업 큐, 에이전트 tool

## Capabilities

### New Capabilities

- `catalog/book-enrichment`: 외부 도서 API로 소장 도서의 서지정보를 채우는 실행, 처리 상태와 현황, 호출 한도 대응, 출처 표시, 외부 분류 판단

### Modified Capabilities

- `catalog/books`: 어린이/일반 도서 구분의 근거에 `external_category` 추가, 우선순위 변경
- `catalog/holdings-import`: 파일 근거가 `external_category` 근거보다 앞서도록 어린이 도서 분류 근거 변경

## Impact

- **새 코드**: `app/external/yes24/`, `app/services/book_enrichment.py`, `app/api/book_enrichment.py`
- **바뀌는 코드**: `app/models/catalog.py`, `app/schemas/catalog.py`, `app/core/config.py`, `app/services/books.py`(ISBN 변경 시 다시 대기), `app/services/holding_imports.py`(근거 우선순위), `app/main.py`
- **새 API**: `POST /book-enrichment/runs`, `GET /book-enrichment`
- **바뀌는 API**: 도서 조회 응답에 새 필드 추가. 기존 필드는 그대로다.
- **마이그레이션**: `books`에 열 추가, `audience_source` CHECK 변경. 기존 도서는 처리 대기가 된다.
- **의존성**: 추가 없음. 이미 있는 `httpx`를 쓴다.
- **외부 시스템**: YES24 Open API. 일일 20,000회, 초당 10회 한도를 키 하나로 함께 쓴다.
- **문서**: `CLAUDE.md`, `README.md`, `docs/design.md`
