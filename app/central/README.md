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

임베딩 서버 시작은 `docker/embedder/start.sh`다(모델 받기, 입력 한도 낮추기, 서버 이름 정하기).

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

### 실행 방식: ONNX 변환본

- **서버는 ONNX 변환본으로만 띄운다.** 같은 가중치의 변환본(`TEI_MODEL_ID`, 기본 `Rigel97/snowflake-arctic-embed-l-v2.0-ko-onnx`)을 ONNX(ort) 실행기로 띄운다. 저장소에 `onnx/model.onnx`가 없으면 시작 스크립트가 이유를 출력하고 멈춘다. 원본 저장소에는 ONNX 파일이 없어 Candle 실행기로만 돌았고, 적재가 1.7배쯤 느렸다(아래 표). 설정을 잘못 넣어 모르는 사이에 느린 실행기로 도는 일을 막으려고 Candle로 띄우는 길은 두지 않는다.
- 벡터와 함께 저장하는 이름은 원본 이름(`EMBEDDING_MODEL`, `dragonkue/snowflake-arctic-embed-l-v2.0-ko`) 그대로다. 같은 벡터가 나오므로(아래) 이미 만든 벡터를 다시 만들지 않는다. 시작 스크립트가 이 이름을 `--served-model-name`으로 넘기고 `check()`가 비교한다.
- **같은 벡터인지는 `tests/embedding_live/test_reference_vectors.py`가 지킨다.** 원본(Candle)으로 만든 기준 벡터(`tests/embedding_live/data/reference_vectors.json`, 직접 쓴 문서 5개와 질의 2개)와 지금 서버의 벡터가 모두 코사인 0.999 이상이어야 한다. 2026-11-11 ONNX 변환본은 0.99998 이상이었다. 실행 방식이나 TEI 버전을 바꾸면 임베딩 서버를 띄우고 `uv run pytest tests/embedding_live`를 돌린다. 미달이면 같은 모델이 아니므로 `EMBEDDING_MODEL`을 새 이름으로 두고 다시 적재한다.

**ONNX 실행기로 떴는지 확인하는 방법.** TEI 1.9.4는 시작 로그에 실행기 이름을 찍지 않는다(디버그 로그로도 안 나온다). 아래 셋으로 본다.

1. 실행 중인 서버가 ONNX 가중치를 열었다. 가장 확실하다.
   ```bash
   docker compose --profile embedding exec embedder grep -c model.onnx_data /proc/1/maps
   ```
   1 이상이면 ONNX다. 0이면 다른 가중치를 읽은 것이다.
2. 시작 로그에 `Could not start ORT backend` 오류와 Candle의 `Starting Bert model on Cpu`가 없다.
3. 시작 로그의 묶음 한도가 `Backend does not support a batch size > 8`이다(Candle은 `> 4`). `/info`의 `max_batch_requests`도 8이다.

**교체 전후 측정** (교체를 정할 때 잰 값. 2026-11-11, CPU 8개·메모리 7.7GB, 입력 한도 512토큰, 표본 87권의 임베딩 텍스트 v1)

| | Candle (원본) | ONNX (변환본) |
| --- | --- | --- |
| 질의 1건 p50 / p95 (워밍업 3건 제외, 질의 20개) | 134ms / 152ms | 131ms / 190ms |
| 87권 적재, 배치 1 | 167.5초 | 126.5초 |
| 87권 적재, 배치 4 | 191.2초 | 128.6초 |
| 87권 적재, 배치 8 | - | 145.3초 |
| 87권 적재, 배치 32 | 252.7초 | 152.1초 |
| 컨테이너 메모리 (대기 / 적재 중 최고) | 3.96GiB / 4.26GiB | 3.44GiB / 3.95GiB |
| 서버 시작 (모델을 받은 뒤) | 약 20초 | 약 6초 |

적재 시간은 두 번 잰 평균이다. 같은 조건에서도 10~20% 흔들렸다(ONNX 배치 1이 139초, 114초). 질의 p95는 20건 중 느린 한 건이라 흔들림이 크다.

- 가장 빠른 조건끼리 비교하면 약 24% 빠르고(배치 1, 167.5초 → 126.5초), 지금 기본값인 배치 32로는 약 40% 빠르다. 권당 약 1.45초, 5,000권이면 약 2시간이다.
- ONNX에서도 배치가 클수록 느리다. 서버가 한 번에 묶는 책들을 가장 긴 책 길이로 채워 계산하는 것으로 보인다. 배치 1과 4는 흔들림 안에서 같다.

### 모델 바꾸기

1. 모델을 ONNX로 변환해 Hugging Face에 올린다. 서버는 ONNX 변환본만 띄운다. 저장소에 `onnx/model.onnx`(2GB가 넘으면 `onnx/model.onnx_data`도), 토크나이저, `1_Pooling/config.json`, `sentence_bert_config.json`, `config_sentence_transformers.json`이 있어야 한다.
2. `.env`의 `TEI_MODEL_ID`(변환본 저장소)와 `EMBEDDING_MODEL`(벡터와 함께 저장할 이름, 보통 원본 모델 이름), 필요하면 `EMBEDDING_MAX_TOKENS`를 바꾸고 `docker compose --profile embedding up -d --force-recreate embedder`로 다시 띄운다.
3. 기준 벡터를 새 모델로 다시 만든다(`uv run python -m tests.embedding_live.reference --write`). 원본 실행기로 만들 수 없으면 변환할 때 sentence-transformers로 원본 벡터와 비교해 둔다.
4. 질의 접두어가 있는 모델이면 `external/tei.py`의 `QUERY_PREFIXES`에 더한다. 모델 저장소 `config_sentence_transformers.json`의 `prompts`를 확인한다.
5. `book_embeddings`의 벡터 열은 1024차원이다. 차원이 다른 모델은 마이그레이션이 먼저다.
6. `scripts/embed_books.py --incremental`을 돌린다. 모델 이름이 다르면 새 벡터가 따로 저장되고 이전 모델의 벡터는 남는다.
7. TEI가 아닌 서버나 API를 쓰려면 `Embedder`를 구현한 어댑터를 `external/`에 더한다.

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
