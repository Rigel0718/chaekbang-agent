# Proposal

## Why

공식 서지(`books`)는 구조만 있고 비어 있어서 소장 도서에 소개·표지가 없다. 3주차 AI 사서가 데이터만으로 추천 이유를 말하려면 소장 도서의 공식 서지를 먼저 채워야 한다. 또 MVP의 작은도서관은 파일에 어린이 표시가 없으면 어린이 도서 대부분이 `general`로 남으므로, 기관 층이 공식 서지의 분류 원문을 어린이 구분의 근거로 쓸 수 있게 한다.

## What Changes

- **YES24 연동**
  - `app/external/yes24/`에 호출 코드를 둔다. 엔드포인트와 응답 필드는 정의 파일 한곳에 모은다.
  - 이번에 쓰는 기능은 상품 상세 조회(`itemDetail`, ISBN 기준) 하나다.
  - 키는 `.env`의 `YES24_API_KEY`에서만 읽고, 출력·로그·오류 메시지에 남기지 않는다.
- **운영자 채움 실행**
  - 서비스 운영자가 `scripts/enrich_books.py`로 실행한다. 기관 API에는 실행 경로를 두지 않는다.
  - 어느 기관이든 소장한 처리 대기 ISBN을 정해진 건수만큼 처리한다. 같은 ISBN은 한 번만 조회한다.
  - YES24 값으로 `books` 행을 만들고 같은 ISBN의 기관 도서를 모두 연결한다. 기관 값과 어린이 구분은 바꾸지 않는다.
  - 공식 서지가 이미 있으면 외부 호출 없이 연결한다.
  - 응답의 ISBN이 요청과 다르면 공식 서지를 만들지 않는다.
- **공식 서지 필드 추가**: 부제, 목차, 시리즈명, 출처, 상품 링크, 외부 분류 원문
- **기관의 어린이 구분에 외부 분류 근거 추가** (기관 층의 기능)
  - 운영자 층은 어린이를 모른다. YES24 분류 값은 공식 서지에 원문으로만 보관한다.
  - 어린이 구분은 기관의 요청에서만 바뀐다. 등록, 가져오기, ISBN 수정과 기관 관리자의 어린이 구분 갱신이 원문을 보고 근거 `external_category`를 정한다. 값이 정확히 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나이면 근거다.
  - 우선순위는 `manual`, `import_label`, `external_category`, `default` 순이다.
  - 어린이 도서를 영유아·초등학생 대상 도서로 정의한다.
- **파일 근거 정리**: 부가기호 첫 자리 6(초등 학습참고서)을 근거에 넣고, 출처를 찾지 못한 별치기호 `어`, `c`를 뺀다.
- **어린이 구분 갱신**: 기관 관리자가 `POST /library-books/audience/refresh`로 공식 서지가 채워진 자기 기관 도서의 어린이 구분을 갱신한다. 실행하지 않는 기관의 값은 바뀌지 않는다.
- **처리 상태와 현황**: 기관 도서마다 처리 상태와 시각을 저장해 중단돼도 이어서 처리한다. 기관 관리자는 자기 기관의 처리 현황을 볼 수 있다.
- **호출 한도 대응**: 장서 가져오기 적용은 외부 API를 호출하지 않는다. 호출 속도를 제한하고, 한도 초과나 외부 장애가 나면 실행을 멈춘 뒤 남은 도서를 대기 상태로 둔다.
- **YES24 이용 조건 반영**
  - 소장 도서의 ISBN만 조회한다. 베스트셀러나 카테고리를 돌며 도서 정보를 쌓는 기능은 만들지 않는다.
  - 판매가와 판매 상태는 저장하지 않는다. 표지는 원본 URL만 저장한다.
  - 기관 도서 조회 응답에 출처와 상품 링크를 함께 돌려준다.

**범위 밖 (이번 change에서 하지 않음)**

- 기관 관리자가 실행하는 API, 스케줄러
- 기관별로 어린이 구분을 끄는 설정 → 군부대·대학 같은 기관 유형을 추가할 때
- ISBN 없는 도서의 제목 검색 매칭. 전집은 표본에서 대부분 ISBN이 없었다
- 저자 구조화(이름·역할 분리)와 저자 검색 → 다음 change에서 검토. `books.author`에 YES24 원문을 그대로 둔다
- 상품 검색(`itemList`), 작가 정보(`author`) → `add-librarian-agent`에서 필요할 때
- 베스트셀러, 카테고리 목록을 쓰는 추천·큐레이션 근거
- 도서관 정보나루 연동 → 문서를 받은 뒤 별도 change
- 이미 만든 공식 서지의 갱신, 어느 기관도 소장하지 않게 된 공식 서지의 정리, 구매 요청서를 위한 최신 가격 조회

## Capabilities

### New Capabilities

- `catalog/book-enrichment`: 외부 도서 API로 공식 서지를 만드는 운영자 실행, 호출 한도 대응, 처리 현황, 출처 표시

### Modified Capabilities

- `catalog/books`: 공식 서지를 만드는 주체를 채움 실행으로 명시
- `catalog/library-books`: 공식 서지 연결에 처리 상태 추가, 어린이 도서 정의, 외부 분류 근거, 어린이 구분 갱신 추가
- `catalog/holdings-import`: 파일 근거가 `external_category` 근거보다 앞서도록 변경, 부가기호 6 추가, 별치기호 정리

## Impact

- **새 코드**: `app/external/yes24/`, `app/services/audience.py`, `app/services/book_enrichment.py`, `app/api/book_enrichment.py`, `scripts/enrich_books.py`
- **바뀌는 코드**: `app/models/catalog.py`, `app/schemas/catalog.py`, `app/core/config.py`, `app/services/library_books.py`, `app/services/holding_imports.py`, `app/importing/classify.py`, `app/seed/catalog.py`, `app/main.py`
- **새 API**: `GET /book-enrichment`, `POST /library-books/audience/refresh`
- **바뀌는 API**: 기관 도서 조회 응답에 새 필드 추가. 기존 필드는 그대로다.
- **마이그레이션**: `books`와 `library_books`에 열 추가, `audience_source` CHECK 변경. 연결된 기관 도서는 `enriched`, 나머지는 `pending`이 된다.
- **의존성**: 추가 없음. 이미 있는 `httpx`를 쓴다.
- **외부 시스템**: YES24 Open API. 일일 20,000회, 초당 10회 한도를 키 하나로 쓴다.
- **문서**: `CLAUDE.md`, `README.md`, `docs/design.md`
