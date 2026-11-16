# central

서비스 운영자 층이다. 어느 기관에도 속하지 않는 공식 서지와 외부 연동을 맡는다.

## 맡는 일

- `books`: ISBN이 있는 책의 공식 서지. 기관 API로는 쓸 수 없다.
- `book_contributors`: 공식 서지의 기여자(이름, 이름 맞춤 키, 역할, 역할 원문, 순서). 저자 원문에서 다시 만들 수 있는 값이다.
- `official_book_embeddings`: 공식 서지 벡터. 공식 서지·모델·텍스트 버전·종류마다 하나, 공식 값만으로 만든다. 여러 기관이 함께 쓴다.
- YES24 호출과 응답 해석
- 서지정보 채움 실행. 운영자가 `scripts/enrich_books.py`로 돌린다.
- 임베딩 인코더 접점과 임베딩 서버 호출. 인코더는 문자열을 받아 벡터를 돌려줄 뿐이고 어떤 책인지 모른다.
- 공식 서지 벡터 적재와 두 층이 함께 쓰는 배치 흐름.

## 구성

| 파일 | 내용 |
| --- | --- |
| `models.py` | `Book`, `BookContributor`, `OfficialBookEmbedding`, `ExternalSource`, `EMBEDDING_DIM` |
| `contributors.py` | 출처별 저자 해석기 고르기, 기여자 저장 `sync_contributors`, 다시 맞추기 `rebuild_contributors` |
| `enrichment.py` | 채움 실행 `run_enrichment`, 접점 `EnrichmentTargets` |
| `official_books.py` | 공식 서지를 만드는 함수 `create_official`(기여자, 시리즈 키), `series_keys` |
| `external/yes24/definitions.py` | 엔드포인트, 응답 필드, 오류 코드 |
| `external/yes24/client.py` | 인증, 호출 속도 제한, 오류 구분 |
| `external/yes24/parsing.py` | 응답 상품을 `Yes24Item`으로 변환 |
| `external/yes24/goods.py` | GOODS API 역할 함수 |
| `external/yes24/category.py` | CATEGORY API 역할 함수 `steady_sellers`(실험 장서 받기 전용) |
| `external/yes24/contributors.py` | YES24 저자 원문 해석 `parse_yes24_author` |
| `embedding.py` | 인코더 접점 `Embedder`(`encode_documents`, `encode_queries`, `check`, `name`, `dim`), `EmbeddingError`, 두 층의 배치 흐름 `run_layer`·`EmbeddingLayer`·`EmbeddingRun` |
| `embedding_text.py` | 공식 서지 벡터의 텍스트 `official_embedding_text`(공식 값만, 조립 규칙은 `app/core/embedding_text.py`) |
| `official_embeddings.py` | 공식 서지 벡터 적재 `run_official_embedding`(대상은 공식 서지 전부, `within`으로 좁힘) |
| `external/tei.py` | Text Embeddings Inference 어댑터 `TeiEmbedder`, 모델별 질의 접두어 |

임베딩 서버 시작은 `docker/embedder/start.sh`다(모델 받기, 입력 한도 낮추기, 서버 이름 정하기).

## 규칙

- `app/library`, `app/features`를 import하지 않는다. `tests/platform/test_package_layers.py`가 막는다.
- 기관 모델을 모른다. 대상 ISBN과 연결은 `EnrichmentTargets`로 받고, `app/library/enrichment_targets.py`가 구현한다.
- 어린이 구분을 모른다. `books.external_category`는 YES24 분류 원문을 사실로만 보관한다.
- 이미 있는 공식 서지는 고치지 않는다.

## 기여자

- 저자 원문(`Book.author`)은 그대로 두고 표시와 서명·저자 찾기에 쓴다. 기여자는 원문을 역할별 사람으로 푼 파생 값이고, 추천의 "같은 저자" 신호와 역할 표시에 쓴다.
- **외부 응답으로 공식 서지를 만드는 경로는 `official_books.create_official`을 부른다**: 채움(`enrichment.py`)과 실험 장서 적재(`app/seed/experiment.py`). 외부 값만 쓰고, 이미 있는 공식 서지는 고치지 않고, 기여자(`sync_contributors`)와 시리즈 키를 함께 만든다. 시드(`app/seed/catalog.py`)와 평가 표본 적재(`evals/librarian/catalog.py`)는 응답 상품이 없어 `sync_contributors`만 부른다. 새 경로를 만들면 함께 부른다. 같은 값이면 쓰지 않는다.
- **시리즈 키**(`books.series_keys`): 응답의 시리즈 목록(`Yes24Item.series_names`)에서 시리즈마다 `match_key`를 계산한다. 빈 키와 중복은 빼고 순서는 지킨다. 표시용 `series_name`(이은 문자열)에서는 만들지 않는다. 시리즈명에 쉼표가 들 수 있어서다. 그래서 다시 계산할 수 없고, `rebuild_contributors.py --check`가 "시리즈 키가 빈 시리즈 있는 공식 서지" 건수를 함께 보고한다. 시드와 평가 표본은 빈 목록이다.
- 역할 표와 기관 파일 해석기는 `app/core/contributors.py`에 있다(운영자 층과 기관 공통이 함께 쓴다). 역할은 일곱(`author`, `illustrator`, `translator`, `editor`, `supervisor`, `original`, `other`)이다.
- 역할 표나 이름 맞춤 규칙(`app/core/text.py`의 `match_key`)을 고치면 `uv run python scripts/rebuild_contributors.py`로 다시 맞춘다. `--check`는 차이만 센다.
- 외국 저자의 다른 음역(`조앤 K. 롤링` / `J.K. 롤링`)과 동명이인은 풀지 않는다.

### 출처별 해석기 더하기

1. `external/<출처>/contributors.py`에 `parse_<출처>_author(author: str) -> list[Contributor]`를 둔다. 묶음 나누기만 출처에 맞게 하고, 역할 읽기·이름 나누기는 `app/core/contributors.py`의 조각(`parse_suffix_group`, `read_roles`, `split_names`)을 쓴다.
2. `contributors.py`의 `PARSERS`에 `ExternalSource` → 해석기를 더한다. 출처가 없거나 표에 없으면 기관 파일 해석기(`parse_author_text`)를 쓴다.
3. 그 출처의 실제 표기로 테스트를 고정하고, 처음 보는 역할 표기가 있으면 역할 표에 더한다.

## 임베딩

- **벡터는 두 층이다.** 공식 서지에 연결된 책은 공식 서지 벡터(여기, `official_book_embeddings`), 연결되지 않은 책은 기관 도서 벡터(`app/library/recommendation/embeddings.py`, `book_embeddings`)를 쓴다. 공식 서지 벡터는 `Book`만 받는 `official_embedding_text`로 만들어 기관 값이 들어갈 길이 없다. 적재 대상은 공식 서지 전부다. 기관을 지정한 실행은 부르는 쪽이 공식 서지 id 조건(`within`)을 넘긴다.
- 텍스트는 서명(: 부제), 분류, 소개다. 저자는 넣지 않는다(텍스트 버전 2). 공식 소개가 없으면 소개 없이 만든다(기관 소개로 채우지 않는다). `scripts/embed_books.py`가 끝에 "공식 소개 없음 N건(그중 기관 소개 있음 M건)"을 출력한다.
- **텍스트 종류**(`TextKind`, `scripts/embed_books.py --kind`): 기본 `full` 밖에 추천 실험의 비교용으로 `with_author`(서명, 저자 원문, 분류, 소개. 버전 1과 같은 필드), `description`(소개만), `title`·`category`(필드별 벡터)가 있다. 텍스트 버전은 2 그대로이고 종류마다 벡터가 따로 저장된다. 조립 규칙은 `app/core/embedding_text.py` 한 곳이다.
- **빈 텍스트는 벡터를 만들지 않는다.** 그 종류의 값이 없는 책(소개 없는 책의 `description`)은 인코딩하지 않고 "빈 텍스트 N건"으로 센다. 빈 문자열을 인코딩하면 그런 책들이 모두 같은 벡터를 갖게 된다.
- 배치 기본값은 4권이다(`EMBEDDING_BATCH_SIZE`). CPU ONNX에서는 배치가 클수록 느리고 1과 4가 같다(아래 표). GPU에서는 큰 배치가 빠를 수 있어 설정과 `--batch-size`를 남겼다.
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

- 가장 빠른 조건끼리 비교하면 약 24% 빠르고(배치 1, 167.5초 → 126.5초), 당시 기본값인 배치 32로는 약 40% 빠르다. 이 표로 기본값을 4로 낮췄다(`add-official-book-embeddings`). 권당 약 1.45초, 5,000권이면 약 2시간이다.
- ONNX에서도 배치가 클수록 느리다. 서버가 한 번에 묶는 책들을 가장 긴 책 길이로 채워 계산하는 것으로 보인다. 배치 1과 4는 흔들림 안에서 같다.

### 모델 바꾸기

1. 모델을 ONNX로 변환해 Hugging Face에 올린다. 서버는 ONNX 변환본만 띄운다. 저장소에 `onnx/model.onnx`(2GB가 넘으면 `onnx/model.onnx_data`도), 토크나이저, `1_Pooling/config.json`, `sentence_bert_config.json`, `config_sentence_transformers.json`이 있어야 한다.
2. `.env`의 `TEI_MODEL_ID`(변환본 저장소)와 `EMBEDDING_MODEL`(벡터와 함께 저장할 이름, 보통 원본 모델 이름), 필요하면 `EMBEDDING_MAX_TOKENS`를 바꾸고 `docker compose --profile embedding up -d --force-recreate embedder`로 다시 띄운다.
3. 기준 벡터를 새 모델로 다시 만든다(`uv run python -m tests.embedding_live.reference --write`). 원본 실행기로 만들 수 없으면 변환할 때 sentence-transformers로 원본 벡터와 비교해 둔다.
4. 질의 접두어가 있는 모델이면 `external/tei.py`의 `QUERY_PREFIXES`에 더한다. 모델 저장소 `config_sentence_transformers.json`의 `prompts`를 확인한다.
5. `official_book_embeddings`와 `book_embeddings`의 벡터 열은 1024차원이다(`EMBEDDING_DIM`). 차원이 다른 모델은 마이그레이션이 먼저다.
6. `scripts/embed_books.py --incremental`을 돌린다. 모델 이름이 다르면 새 벡터가 따로 저장되고 이전 모델의 벡터는 남는다.
7. TEI가 아닌 서버나 API를 쓰려면 `Embedder`를 구현한 어댑터를 `external/`에 더한다.

## YES24 이용 조건

- 소장 도서의 ISBN만 조회한다. 베스트셀러나 카테고리를 돌며 도서 정보를 쌓지 않는다.
- 예외는 둘이고 둘 다 한 번만 받아 저장소 밖 파일(`.gitignore`)에 둔다. 서비스 경로에서 부르지 않는다.
  - 상품 검색 `search_items`: 평가 표본 약 100권(`evals/librarian/fetch_sample.py`). 테스트 DB 트랜잭션에서만 쓴다.
  - 카테고리 스테디셀러 `category.steady_sellers`: 실험 장서 약 500권(`evals/collection/fetch.py`). 개발 DB의 가상 기관에만 넣는다(`scripts/seed_experiment.py`). 파일이 있으면 받기가 멈춘다. 서지 출처를 바꾸는 `add-bibliographic-sources`에서 지운다.
- 판매가, 판매 상태, 포인트, 판매지수, 평점은 저장하지 않는다. 받은 원본 파일에도 넣지 않는다(키 목록은 `definitions.py`의 `VOLATILE_ITEM_KEYS`).
- 표지는 원본 URL만 저장하고, 조회 응답에 출처와 상품 링크를 함께 돌려준다.
- 키는 `.env`의 `YES24_API_KEY`에서만 읽고 `X-Api-Key` 헤더로만 보낸다. 출력과 로그에 남기지 않는다.

## 새 YES24 기능 추가

1. `definitions.py`에 `Endpoint`를 추가한다. 응답 필드는 `ITEM_FIELDS`에 한 줄로 추가한다.
2. API 묶음별 파일(`goods.py`, `category.py`)에 역할 함수를 추가하고, 하는 일을 한국어로 적는다. 서비스 경로에서 쓰지 않는 함수는 누가 쓰는지와 이용 조건의 예외인지를 적는다.
3. 응답 키 문자열은 `definitions.py` 밖에 쓰지 않는다.

API 문서는 `api-guides/yes24-open-api-guide/`에 있다. 문서와 실제 응답이 다른 곳이 있어서, 새 필드는 실제 응답으로 확인한다.
