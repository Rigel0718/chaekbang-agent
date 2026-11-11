# central

서비스 운영자 층이다. 어느 기관에도 속하지 않는 공식 서지와 외부 연동을 맡는다.

## 맡는 일

- `books`: ISBN이 있는 책의 공식 서지. 기관 API로는 쓸 수 없다.
- YES24 호출과 응답 해석
- 서지정보 채움 실행. 운영자가 `scripts/enrich_books.py`로 돌린다.
- 임베딩 인코더 접점과 임베딩 서버 호출. 문자열을 받아 벡터를 돌려줄 뿐이고 어떤 책인지 모른다.

## 구성

| 파일 | 내용 |
| --- | --- |
| `models.py` | `Book`, `ExternalSource` |
| `enrichment.py` | 채움 실행 `run_enrichment`, 접점 `EnrichmentTargets` |
| `external/yes24/definitions.py` | 엔드포인트, 응답 필드, 오류 코드 |
| `external/yes24/client.py` | 인증, 호출 속도 제한, 오류 구분 |
| `external/yes24/parsing.py` | 응답 상품을 `Yes24Item`으로 변환 |
| `external/yes24/goods.py` | GOODS API 역할 함수 |
| `embedding.py` | 인코더 접점 `Embedder`(`encode_documents`, `encode_queries`, `check`, `name`, `dim`), `EmbeddingError` |
| `external/tei.py` | Text Embeddings Inference 어댑터 `TeiEmbedder`, 모델별 질의 접두어 |

## 규칙

- `app/library`, `app/features`를 import하지 않는다. `tests/platform/test_package_layers.py`가 막는다.
- 기관 모델을 모른다. 대상 ISBN과 연결은 `EnrichmentTargets`로 받고, `app/library/enrichment_targets.py`가 구현한다.
- 어린이 구분을 모른다. `books.external_category`는 YES24 분류 원문을 사실로만 보관한다.
- 이미 있는 공식 서지는 고치지 않는다.

## 임베딩

- 모델을 실행하는 코드는 `external/tei.py` 하나다. TEI의 요청·응답 형식은 이 파일 밖으로 나가지 않는다. 적재와 조회는 `Embedder`만 알고, 테스트는 가짜 인코더(`tests/embedding_helpers.py`)로 돈다.
- 문서(도서)는 접두어 없이, 질의는 모델이 정한 접두어(`query: `)를 붙여 인코딩한다. TEI의 `prompt_name`을 쓰지 않고 앱이 문자열을 붙인다. 결과가 같다는 것은 `tests/embedding_live/`가 확인한다.
- 항상 `normalize`와 `truncate`를 켠다. 입력 길이 한도(기본 512토큰)는 서버가 정한다. TEI에는 한도를 낮추는 옵션이 없어서 `docker/embedder/start.sh`가 모델 폴더의 `max_seq_length`를 `EMBEDDING_MAX_TOKENS`로 바꿔 띄운다. 모델의 원래 한도(8192토큰)로 띄우면 준비 단계에서 메모리가 6GB를 넘는다.
- `check()`가 서버의 모델 이름과 입력 한도를 설정과 비교한다. 다르면 적재를 시작하지 않는다.
- 오류에는 상태 코드와 종류만 남기고 입력 텍스트를 넣지 않는다.
- 소개글은 로컬 컨테이너에만 보낸다. 외부 임베딩 API로 바꾸려면 YES24 이용 조건을 먼저 확인한다.

### 모델 바꾸기

1. `.env`의 `EMBEDDING_MODEL`(필요하면 `EMBEDDING_MAX_TOKENS`)을 바꾸고 임베딩 서버를 다시 띄운다.
2. 질의 접두어가 있는 모델이면 `external/tei.py`의 `QUERY_PREFIXES`에 더한다. 모델 저장소 `config_sentence_transformers.json`의 `prompts`를 확인한다.
3. `book_embeddings`의 벡터 열은 1024차원이다. 차원이 다른 모델은 마이그레이션이 먼저다.
4. `scripts/embed_books.py --incremental`을 돌린다. 모델 이름이 다르면 새 벡터가 따로 저장되고 이전 모델의 벡터는 남는다.
5. TEI가 아닌 서버나 API를 쓰려면 `Embedder`를 구현한 어댑터를 `external/`에 더한다.

## YES24 이용 조건

- 소장 도서의 ISBN만 조회한다. 베스트셀러나 카테고리를 돌며 도서 정보를 쌓지 않는다. 상품 검색 `search_items`는 평가 표본 스크립트만 쓴다. 서비스 경로에서 부르지 않는다.
- 판매가, 판매 상태, 포인트, 판매지수, 평점은 저장하지 않는다.
- 표지는 원본 URL만 저장하고, 조회 응답에 출처와 상품 링크를 함께 돌려준다.
- 키는 `.env`의 `YES24_API_KEY`에서만 읽고 `X-Api-Key` 헤더로만 보낸다. 출력과 로그에 남기지 않는다.

## 새 YES24 기능 추가

1. `definitions.py`에 `Endpoint`를 추가한다. 응답 필드는 `ITEM_FIELDS`에 한 줄로 추가한다.
2. API 묶음별 파일(`goods.py`, 이후 `category.py`)에 역할 함수를 추가하고, 하는 일을 한국어로 적는다.
3. 응답 키 문자열은 `definitions.py` 밖에 쓰지 않는다.

API 문서는 `yes24-open-api-guide/`에 있다. 문서와 실제 응답이 다른 곳이 있어서, 새 필드는 실제 응답으로 확인한다.
