# central

서비스 운영자 층이다. 어느 기관에도 속하지 않는 공식 서지와 외부 연동을 맡는다.

## 맡는 일

- `books`: ISBN이 있는 책의 공식 서지. 기관 API로는 쓸 수 없다.
- YES24 호출과 응답 해석
- 서지정보 채움 실행. 운영자가 `scripts/enrich_books.py`로 돌린다.

## 구성

| 파일 | 내용 |
| --- | --- |
| `models.py` | `Book`, `ExternalSource` |
| `enrichment.py` | 채움 실행 `run_enrichment`, 접점 `EnrichmentTargets` |
| `external/yes24/definitions.py` | 엔드포인트, 응답 필드, 오류 코드 |
| `external/yes24/client.py` | 인증, 호출 속도 제한, 오류 구분 |
| `external/yes24/parsing.py` | 응답 상품을 `Yes24Item`으로 변환 |
| `external/yes24/goods.py` | GOODS API 역할 함수 |

## 규칙

- `app/library`, `app/features`를 import하지 않는다. `tests/platform/test_package_layers.py`가 막는다.
- 기관 모델을 모른다. 대상 ISBN과 연결은 `EnrichmentTargets`로 받고, `app/library/enrichment_targets.py`가 구현한다.
- 어린이 구분을 모른다. `books.external_category`는 YES24 분류 원문을 사실로만 보관한다.
- 이미 있는 공식 서지는 고치지 않는다.

## YES24 이용 조건

- 소장 도서의 ISBN만 조회한다. 베스트셀러나 카테고리를 돌며 도서 정보를 쌓지 않는다.
- 판매가, 판매 상태, 포인트, 판매지수, 평점은 저장하지 않는다.
- 표지는 원본 URL만 저장하고, 조회 응답에 출처와 상품 링크를 함께 돌려준다.
- 키는 `.env`의 `YES24_API_KEY`에서만 읽고 `X-Api-Key` 헤더로만 보낸다. 출력과 로그에 남기지 않는다.

## 새 YES24 기능 추가

1. `definitions.py`에 `Endpoint`를 추가한다. 응답 필드는 `ITEM_FIELDS`에 한 줄로 추가한다.
2. API 묶음별 파일(`goods.py`, 이후 `category.py`)에 역할 함수를 추가하고, 하는 일을 한국어로 적는다.
3. 응답 키 문자열은 `definitions.py` 밖에 쓰지 않는다.

API 문서는 `yes24-open-api-guide/`에 있다. 문서와 실제 응답이 다른 곳이 있어서, 새 필드는 실제 응답으로 확인한다.
