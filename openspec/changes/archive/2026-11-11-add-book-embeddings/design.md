## Context

- DB 이미지는 `postgres:16`(지금 컨테이너는 PostgreSQL 16.15, Debian 13 trixie, 콜레이션 버전 2.41)이고 pgvector가 없다. 개발 DB에는 기관 2개, 기관 도서 270권이 있다.
- 평가 표본 87권(`evals/librarian/data/yes24_sample.json`)은 개발 DB에 넣지 않는다. `evals/librarian/catalog.py`의 `load_catalog`가 테스트 DB의 되돌릴 트랜잭션 안에서 가상 기관에 적재한다.
- 추천 가능한 책의 조건은 `app/library/recommendation/search.py`의 `recommendable_ids`(대출 가능·대출 중 사본이 있는 그 기관의 기관 도서) 한 곳에 있다.
- 표시 값은 `LibraryBook.shown`(공식 값 먼저)으로 읽는다.
- LLM은 `app/agent/llm.py`의 접점과 `openai_client.py` 어댑터 하나로 나뉘어 있다. 임베딩도 같은 모양으로 둔다.
- 운영자 CLI `scripts/enrich_books.py`는 종료 코드 0(완료), 1(전제 조건·인자·키), 2(외부 장애로 중단)를 쓰고, 마이그레이션 확인(`check_migrations`)과 DB 연결 오류 안내를 한다.
- 개발 장비는 CPU 8개, 메모리 7GB(여유 약 5GB)다.

**확인한 것 (2026-11-11, 모델 저장소)**

| 항목 | 값 |
| --- | --- |
| `config_sentence_transformers.json`의 `prompts` | `{"query": "query: "}` |
| `default_prompt_name` | `null` (문서는 접두어 없음) |
| `similarity_fn_name` | `cosine` |
| 풀링 (`1_Pooling/config.json`) | CLS, `include_prompt: true` |
| 차원 / 라이선스 | 1024 / Apache-2.0 |
| 최대 길이 | 8192토큰 (학습은 최대 1300토큰) |
| 가중치 | `model.safetensors` 2.27GB. ONNX 파일은 없다 |
| 구조 | XLM-RoBERTa (`Snowflake/snowflake-arctic-embed-l-v2.0` 기반) |

요청의 `query: ` 접두어는 모델 설정과 같다.

## Goals / Non-Goals

**Goals:**

- 기관 도서를 벡터로 만들어 저장하고, 바뀐 책만 다시 만든다.
- 임베딩 텍스트 구성과 모델을 바꿔도 테이블, 적재 흐름, CLI가 그대로다. 모델·텍스트 버전이 다른 벡터가 공존해 비교 실험을 할 수 있다.
- YES24 소개글이 외부로 나가지 않고, 원문을 새로 쌓지 않는다.
- 테스트는 임베딩 서버 없이 돈다.

**Non-Goals:**

- 검색·추천 API, 랭킹, 하이브리드 점수, 비슷한 책, 저자 구조화(`add-related-books`).
- 서버 실행 중 자동 적재(등록·가져오기 뒤 바로 임베딩). 지금은 운영자가 CLI로 돌린다.
- 벡터 인덱스. 시간을 재서 필요할 때만 둔다(결정 9).
- 쓰지 않는 벡터 정리(옛 텍스트 버전, 제적된 책). 조회가 걸러 내므로 남아 있어도 결과에 영향이 없다.

## Decisions

### 1. 대상 id: 기관 도서(`library_book_id`) 기준

| 안 | 장점 | 단점 |
| --- | --- | --- |
| **A. 기관 도서 기준 (선택)** | 테이블 하나. ISBN 없는 책이 같은 경로. 기관 분리가 다른 기관 데이터 테이블과 같은 방식(복합 외래 키). 조회가 `recommendable_ids`와 바로 이어짐 | 여러 기관이 같은 책을 가지면 벡터가 기관 수만큼 중복 |
| B. 공식 서지 기준 + 기관 도서 보완 | 같은 ISBN은 한 번만 인코딩 | 테이블 두 개와 조회 합치기. 표시 값은 공식 값이 비면 기관 값으로 채워지므로 "공식 서지의 텍스트"가 기관마다 달라질 수 있어 공유가 깨짐. 기관 공통 테이블에 기관 실행이 쓰게 됨 |

A로 정한다. 중복 비용은 작다. 1024차원 float4 벡터는 약 4KB라 5,000권이 약 20MB다. 기관이 늘어 인코딩 시간이 문제가 되면 `content_hash`가 같은 벡터를 복사하는 최적화를 테이블을 바꾸지 않고 더할 수 있다.

### 2. 테이블 `book_embeddings`

| 열 | 타입 | 비고 |
| --- | --- | --- |
| `id` | PK | |
| `library_id` | FK → libraries, NOT NULL | 기관 데이터 테이블 |
| `library_book_id` | int, NOT NULL | (`library_id`, `library_book_id`) → `library_books` 복합 외래 키, `ON DELETE CASCADE` |
| `model_name` | varchar(200) | 인코더의 `name` |
| `text_version` | int | `TEXT_VERSION` |
| `embedding` | `vector(1024)` | 정규화된 벡터 |
| `content_hash` | char(64) | 임베딩 텍스트(UTF-8)의 SHA-256 16진수 |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin` |

- 유니크: (`library_id`, `library_book_id`, `model_name`, `text_version`). 기관 도서 id가 이미 전역에서 유일하므로 요청의 (대상 id, `model_name`, `text_version`)과 같은 뜻이고, `library_id`를 앞에 둬 기관별 조회에 쓴다.
- 외래 키는 `CASCADE`다. 다른 기관 데이터 테이블은 `RESTRICT`지만 임베딩은 기관 도서에서 다시 만들 수 있는 파생 값이라, 기관 도서를 지우는 일을 막을 이유가 없다.
- 원문 텍스트 열은 없다.
- **`vector(1024)`의 한계**: 차원이 다른 모델(API 임베딩 1536·3072 등)은 이 열에 못 넣는다. 비교 후보 `nlpai-lab/KURE-v1`은 1024차원이라 그대로 공존한다. 차원이 다른 모델을 비교하게 되면 그때 차원 없는 `vector` 열로 바꾸는 마이그레이션을 한다(지금은 DB가 차원을 검사해 주는 쪽을 택한다).
- 모델은 `app/library/models/embedding.py`의 `BookEmbedding`이다. `app/models.py`의 `TENANT_TABLES`에 더한다.

### 3. 인코더 접점은 `app/central/`, 어댑터 하나

```python
class Embedder(Protocol):
    name: str  # 벡터와 함께 저장하는 모델 이름
    dim: int

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]: ...
```

- `app/central/embedding.py`: `Embedder`, `EmbeddingError`(종류: `unreachable`, `server_error`, `bad_response`, `model_mismatch`).
- `app/central/external/tei.py`: `TeiEmbedder`. TEI 요청·응답 형식은 이 파일 밖으로 나가지 않는다. `httpx.AsyncClient`를 받아 테스트에서 `httpx.MockTransport`로 바꾼다.
- 운영자 층에 두는 이유: 외부 서비스 연동이고 기관 모델을 모른다(문자열을 받아 벡터를 돌려줄 뿐). `library`는 `central`을 import할 수 있어 이후 검색 service가 `encode_queries`를 쓴다. `app/agent`에 두지 않는 이유는 실행기와 무관하기 때문이다.
- DB I/O가 async라 접점도 async다.

### 4. 질의 접두어는 앱이 붙인다

| 안 | 내용 |
| --- | --- |
| **A. 앱이 문자열을 붙인다 (선택)** | `encode_queries`가 `"query: " + text`를 만들어 `/embed`에 보낸다 |
| B. TEI의 `prompt_name: "query"` | TEI가 모델 설정의 `prompts`를 읽어 붙인다 |

A로 정한다.

- sentence-transformers의 `prompt_name`은 토큰화 전에 문자열을 앞에 붙이는 것이라 결과가 같다.
- 접두어 규칙이 `Embedder` 구현 안에 있어야 모델을 바꿀 때 한 곳만 고친다. 접두어가 없는 모델(KURE-v1)이나 TEI가 아닌 API 모델도 같은 접점으로 들어온다.
- TEI 없이 테스트로 고정할 수 있다(보낸 요청 본문을 확인).
- TEI가 모델 설정을 읽는 방식이 버전에 따라 바뀌어도 영향이 없다.

접두어는 어댑터의 모델별 표(`QUERY_PREFIXES`)로 둔다. TEI가 떠 있을 때만 도는 테스트가 앱 접두어 방식의 벡터와 TEI `prompt_name="query"` 방식의 벡터가 같은지(코사인 0.999 이상) 확인한다. 실제로 잰 값은 0.9999999이고, 접두어 없이 인코딩한 벡터와는 0.867이다.

### 5. 입력 길이 512토큰과 TEI 설정

구현 때 TEI 1.9.4로 확인해 정했다(2026-11-11).

- **TEI에는 입력 길이 한도를 낮추는 서버 옵션이 없다.** 한도는 모델 폴더의 `sentence_bert_config.json`(`max_seq_length`, 이 모델은 8192)에서 읽는다.
- **모델의 한도 그대로는 이 장비에서 서버가 뜨지 않는다.** 준비 단계(warm-up)가 한도 길이의 입력을 넣어 보는데, 8192토큰에서 메모리를 6.2GB 넘게 써 커널이 프로세스를 죽였다(OOM). 그래서 처음 계획의 2안(`/tokenize`로 앱이 자르기)은 쓸 수 없다. 서버가 떠야 부를 수 있기 때문이다.
- **정한 것**: `docker/embedder/start.sh`가 컨테이너를 띄울 때 모델 파일을 볼륨(`/data/local/<모델>`)에 받고, `sentence_bert_config.json`의 `max_seq_length`만 `EMBEDDING_MAX_TOKENS`로 바꾼 뒤 그 폴더를 `--model-id`로 넘긴다. `--served-model-name`으로 원래 모델 이름을 유지한다. 가중치와 토크나이저는 그대로다. 이미지에 있는 `curl`과 `sed`만 쓴다.
  - 서버의 `/info`가 `max_input_length: 512`를 돌려주고, 요청의 `truncate: true`가 512토큰(문장 시작·끝 토큰 2개 포함)에서 자른다. `truncate: false`로 긴 입력을 보내면 422로 거부한다.
  - 512토큰 한도로 띄운 서버의 메모리는 3.9GB(대기)~4.3GB(적재 중)다.
- 앱은 요청마다 `normalize: true`, `truncate: true`를 보낸다. 응답 벡터의 수나 길이가 다르면 `bad_response`다.
- `check()`가 `/info`의 `served_model_name`과 `max_input_length`를 설정(`EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS`)과 비교하고, 다르면 `model_mismatch`로 멈춘다(종료 코드 1). 한도가 서버 쪽에 있으므로 설정과 어긋난 채 적재하는 일을 여기서 막는다. `check`는 `Embedder` 접점에 더했다.
- `content_hash`는 자르기 전 전체 텍스트의 해시다. 한도 설정을 바꾸면 해시가 그대로라 증분이 알아채지 못하므로, 한도를 바꾼 뒤에는 `--full`로 다시 적재한다(README에 적었다).
- 확인한 요청 형식: `/embed`의 `inputs`, `normalize`(기본 true), `truncate`, `prompt_name`, `dimensions`. 오류 응답은 `{"error", "error_type"}`이고 종류는 `Unhealthy`, `Backend`, `Overloaded`, `Validation`, `Tokenizer`, `Empty`다. `/tokenize`의 토큰 위치는 UTF-8 바이트 기준이다. 한 요청의 입력은 32개까지다(33개는 422).
- TEI가 떠 있을 때 도는 테스트가 고정한다: 한도를 넘는 긴 텍스트의 벡터가 한도까지의 앞부분만 넣은 벡터와 같다.

### 6. 임베딩 텍스트: `app/library/recommendation/embedding_text.py`

```python
TEXT_VERSION = 1


def build_embedding_text(book: LibraryBook) -> str: ...
def content_hash(text: str) -> str: ...  # SHA-256 16진수
```

- 이 모듈은 `LibraryBook`(과 `shown`)만 안다. DB, 인코더, 설정을 import하지 않는다. 자주 바뀔 곳이라 다른 코드와 떼어 둔다.
- v1 구성(줄바꿈으로 잇고 빈 값은 건너뛴다):
  1. 서명. 부제가 있으면 `서명: 부제`
  2. 저자(원문 그대로. 구조화는 `add-related-books`)
  3. 분류: 공식 서지의 외부 분류 원문(`external_category`)과 KDC(`kdc`)의 주류 이름. 주제어 필드는 지금 데이터에 없다
  4. 소개(`description`)
- 소개를 마지막에 둔다. 512토큰에서 잘릴 때 서명·저자·분류가 남고 긴 소개의 뒷부분이 잘리게 하기 위해서다.
- 항목 이름표(`제목:` 등)는 붙이지 않는다. 구성을 바꾸면 `TEXT_VERSION`을 올린다.
- 어린이 구분은 넣지 않는다(기관 개별 기능의 값이고, 추천에서는 필터로 강제한다).

### 7. 적재: `app/library/recommendation/embeddings.py`

```python
@dataclass
class EmbeddingRun:
    targets: int; encoded: int; skipped: int; stopped: EmbeddingError | None

async def run_embedding(session, embedder, *, full: bool, library_id: int | None,
                        batch_size: int, on_progress=None) -> EmbeddingRun
async def similar_books(session, embedder, *, library_id: int, query: str, limit: int = 5)
```

- **대상**: `recommendable_ids`와 같은 조건(대출 가능·대출 중 사본이 있는 기관 도서). 제적·분실·파손 사본만 남은 책은 뺀다. 추천할 수 없는 책을 인코딩할 이유가 없고, 소장 도서만 다룬다는 원칙과 맞다. 조건식은 `search.py`의 것을 다시 쓰고 복사하지 않는다(기관을 지정하지 않는 실행을 위해 기관 조건만 선택으로 만든다).
- **흐름**: 대상 도서를 id 순서로 배치만큼 읽는다 → 텍스트와 해시를 만든다 → 증분이면 저장된 (`model_name`, `TEXT_VERSION`) 행의 해시와 비교해 같은 책을 건너뛴다 → 남은 책을 `encode_documents`로 인코딩한다 → `INSERT … ON CONFLICT DO UPDATE`로 저장하고 커밋한다.
- 인코딩 호출 동안 트랜잭션을 잡지 않는다(읽고 커밋한 뒤 호출, 실행기의 LLM 규칙과 같다). 배치마다 커밋하므로 중간에 멈춰도 끝난 배치는 남고, 증분으로 이어 한다.
- `EmbeddingError`가 나면 `stopped`에 담아 돌려준다. 재시도는 하지 않는다(로컬 서버라 꺼져 있거나 설정이 틀린 경우가 대부분이다).
- `--full`은 해시 비교 없이 대상을 모두 다시 인코딩한다. 행을 지우고 다시 만들지 않고 덮어쓴다.
- **조회** `similar_books`: `encode_queries`로 질의를 인코딩하고, `library_id`·`model_name`·`TEXT_VERSION`이 맞고 `recommendable_ids`에 있는 행을 코사인 거리(`<=>`) 순으로 가져온다. 유사도는 `1 - 거리`다. 확인 스크립트와 이후 `add-related-books`가 쓴다. REST와 tool에는 잇지 않는다.

### 8. CLI 위치와 실행 주체

- **`scripts/embed_books.py`** — 운영자 실행.
  - `--full | --incremental`(둘 중 하나 필수), `--library-id N`(없으면 모든 기관), `--batch-size N`(기본은 설정 값 32).
  - 진행 출력: 배치마다 `[64/270] 인코딩 60, 건너뜀 4`. 끝에 `대상 270권: 인코딩 266건, 건너뜀 4건 (모델 …, 텍스트 버전 1)`.
  - 종료 코드: 0 완료, 1 전제 조건(인자, DB 연결, 마이그레이션, 모델 불일치), 2 임베딩 서버 장애로 중단. 서버에 닿지 않으면 `docker compose --profile embedding up -d embedder`를 안내한다.
  - `enrich_books.py`의 `_Parser`, 엔진 생성, `check_migrations` 구조를 따른다.
- **운영자 실행으로 두는 이유**: 임베딩 서버는 서비스 운영자가 띄우는 자원이고, 공식 서지 채움 뒤에 이어 돌리는 작업이다(채움으로 소개가 생기면 해시가 달라져 증분이 잡는다). 기관 담당자가 누를 버튼이 아니다. 적재 코드는 기관 도서를 다루므로 `app/library/`에 있고, 스크립트가 인코더(운영자 층)와 적재(기관 공통)를 잇는다. 운영자 실행이지만 기관이 정한 값은 바꾸지 않는다(파생 값만 쓴다). 훅을 부르지 않는다.
- **`scripts/embedding_search.py`** — 확인용.
  - `"질의" --library-id N`: 개발 DB에서 그 기관의 상위 5권(순위, 유사도, 서명, 저자)을 출력한다.
  - `"질의" --sample`: 테스트 DB의 트랜잭션 안에서 표본 87권을 가상 기관에 적재하고(`load_catalog`), 전체 적재 → 증분 적재(0건 확인) → 상위 5권 출력을 한 뒤 되돌린다. 표본을 개발 DB에 넣지 않는 기존 규칙을 지키면서 완료 기준을 한 번에 확인한다. 표본 파일이 없으면 안내하고 종료 코드 1이다.

### 9. pgvector 이미지와 인덱스

- 이미지: `pgvector/pgvector`의 PostgreSQL 16 태그 중 **지금 컨테이너와 같은 Debian 13(trixie) 변형**을 정확한 버전으로 고정한다(`<버전>-pg16-trixie`). 볼륨을 만든 OS와 glibc가 다르면 콜레이션 버전 불일치 경고가 나고 텍스트 인덱스를 다시 만들어야 할 수 있어서다. 같은 PostgreSQL 16이고 OS도 같으면 볼륨을 그대로 쓴다. 바꾼 뒤 `datcollversion`(지금 2.41)과 경고 유무를 확인한다.
- `pgvector/pgvector:0.8.6-pg16-trixie`(8월 13일)로 고정했다. 최신 `0.8.7`은 10월 31일에 올라와 2주가 안 됐다. 이미지의 PostgreSQL은 16.15, Debian 13으로 바꾸기 전과 같고, 바꾼 뒤 콜레이션 버전(2.41)과 데이터가 그대로이며 경고가 없었다.
- 확장은 마이그레이션에서 `CREATE EXTENSION IF NOT EXISTS vector`로 켠다. 테스트 DB도 같은 컨테이너라 같은 이미지를 쓴다.
- Python 쪽은 `pgvector` 패키지의 SQLAlchemy `Vector` 타입을 쓴다(asyncpg 지원 포함). Alembic autogenerate가 이 타입을 알아보게 `migrations/env.py`를 확인한다.
- **인덱스는 두지 않는다.** 한 기관 5,000권(무작위 정규화 벡터)에서 상위 5권 조회를 재니 첫 호출 75ms, 이후 세 번 54·49·50ms(중앙값 50ms)로 기준 100ms 아래다. 테이블 크기는 28MB다. 기관이 수만 권이 되거나 조회가 대화마다 여러 번 불리면 HNSW(`vector_cosine_ops`)를 다시 본다. 모델·버전이 섞인 테이블이라 부분 인덱스가 필요하다.

### 10. 임베딩 서버 컨테이너

```yaml
embedder:
  image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4
  profiles: ["embedding"]
  entrypoint: ["sh", "/start.sh"]          # 모델 받기, 입력 한도 낮추기, TEI 실행 (결정 5)
  environment: {EMBEDDING_MODEL: …, EMBEDDING_MAX_TOKENS: …}
  ports: ["127.0.0.1:${EMBEDDING_PORT:-8090}:80"]
  volumes: [tei-data:/data, ./docker/embedder/start.sh:/start.sh:ro]
```

- `profiles`로 둬서 `docker compose up -d db`와 테스트는 임베딩 서버 없이 그대로 돈다. 포트는 로컬에만 연다.
- 버전: v1.9.4(9월 15일). `cpu-1.9.4` 태그가 있는 것을 확인했다.
- 저장소에 ONNX 파일이 없어 TEI가 ONNX 실행기를 포기하고 Candle 실행기로 safetensors를 읽는다. 동작은 하지만 느리다(Risks).
- 모델 파일은 볼륨 `tei-data`에 둔다. 처음 한 번만 내려받는다(약 2.3GB, 이 장비에서 3분 35초). 다시 띄우면 30초쯤 걸린다.
- 설정(`app/core/config.py`, `.env.example`): `EMBEDDING_BASE_URL`(기본 `http://localhost:8090`), `EMBEDDING_MODEL`, `EMBEDDING_DIM`(1024), `EMBEDDING_MAX_TOKENS`(512), `EMBEDDING_BATCH_SIZE`(32), `EMBEDDING_TIMEOUT_SECONDS`(600. 512토큰 32권 한 배치가 128초 걸려 120초로는 모자란다). 배치 32는 TEI의 클라이언트 배치 한도 기본값(32)과 같다. 더 크게 쓰려면 TEI 쪽 한도도 올려야 한다.

### 11. 테스트

- **가짜 인코더**(`tests/`의 도우미): 텍스트의 해시로 정해지는 정규화 벡터를 돌려주고 호출을 기록한다. 유사도 순서 테스트는 벡터를 직접 정해 주는 가짜를 쓴다. 적재·조회·CLI 테스트가 모두 이것으로 돈다.
- **어댑터 테스트**: `httpx.MockTransport`로 요청 본문(접두어, `normalize`, `truncate`)과 오류 구분을 확인한다.
- **TEI가 떠 있을 때만 도는 테스트**(`tests/embedding_live/`, 마커 `tei`): `EMBEDDING_BASE_URL`에 닿지 않으면 표본 테스트처럼 폴더 전체를 건너뛴다. 접두어 동등성, 512토큰 잘림, 정규화, 차원, 서버 설정 일치를 확인한다. 표본도 있으면 표본의 앞 6권으로 전체 적재 → 증분 0건 → 조회를 확인한다. 87권 전체는 3분 반이 걸려 테스트에 넣지 않고 `scripts/embedding_search.py --sample`로 확인한다.
- 스펙 시나리오와 테스트의 대응은 테스트 docstring에 요구사항 이름을 적어 추적한다. 에이전트 동작 시나리오는 없어 `evals/`에 더할 것이 없다.

### 문서 초안과 다르게 정한 것

| 항목 | 초안 | 정한 것 | 이유 |
| --- | --- | --- | --- |
| 대상 id | `book_id` | `library_book_id` + `library_id` | 기관 분리, ISBN 없는 책, `docs/design.md`의 기존 결정(결정 1) |
| CLI | `python -m embeddings.build --full\|--incremental` | `scripts/embed_books.py --full\|--incremental` | 최상위 `embeddings` 패키지는 층 구조 밖이다. 운영자 CLI는 `scripts/`에 두고 층을 잇는다(결정 8) |
| 모델 로드 | 프로세스 안에서 sentence-transformers | TEI 컨테이너 + `httpx` | 앱에 torch를 넣지 않는다. 이미 정한 것 |
| 질의 인코딩 | `prompt_name="query"` | 앱이 `query: `를 붙인다 | 접점을 모델·서버와 무관하게 두고 TEI 없이 테스트한다(결정 4) |
| 코드 위치 | 한 패키지 | 인코더는 `central`, 텍스트·저장·적재는 `library/recommendation` | 의존 방향 `library → central` |
| 표본 적재 | 샘플 데이터를 DB에 넣고 실행 | `--sample`이 테스트 DB 트랜잭션에서 적재하고 되돌린다 | 표본을 개발 DB에 넣지 않는 기존 규칙 |

## Risks / Trade-offs

- **[처리 시간이 예상보다 훨씬 길다 (측정)]** 표본 79권(87권 중 추천 가능한 책) 전체 적재가 205.8초로 한 권에 약 2.6초다. 5,000권이면 약 3시간 40분이다(제안 때 예상은 25분~1시간 20분). 512토큰을 꽉 채운 32권 한 배치는 128초였다. ONNX가 없어 Candle 실행기로 도는 것이 주된 이유로 보인다 → 전체 적재는 처음 한 번과 모델·텍스트 버전을 바꿀 때만 하고 평소에는 증분으로 돌린다. 적재는 중간에 멈춰도 이어 할 수 있다. 더 줄이려면 ONNX 변환본을 만들어 쓰거나(변환에 torch가 필요해 일회성 도구로), GPU가 있는 장비에서 적재만 돌리는 방법이 있다. 실제 기관 장서를 적재하기 전에 정한다.
- **[메모리 (측정)]** 512토큰 한도로 띄운 서버는 3.9GB(대기)~4.3GB(적재 중)를 쓴다. 장비가 7.7GB라 DB·테스트와 함께 돌릴 수 있었지만 여유가 크지 않다. 모델의 원래 한도(8192)로는 6.2GB를 넘어 죽는다(결정 5) → 쓰지 않을 때는 `docker compose --profile embedding stop embedder`로 내려 둔다.
- **[모델 폴더의 설정 파일을 고쳐 쓴다]** TEI가 한도 옵션을 주지 않아 `max_seq_length`만 바꾼 폴더를 쓴다. 가중치는 그대로이고 512토큰 안에서는 결과가 같다. TEI 버전을 올릴 때 한도를 읽는 방식이 바뀌면 `check()`의 한도 비교와 `tests/embedding_live/`의 잘림 테스트가 잡는다.
- **[이미지 교체로 개발 DB가 깨질 수 있다]** → 바꾸기 전에 `pg_dump`로 백업하고 경로를 알린다. 같은 주 버전·같은 OS 변형을 쓴다. 문제가 생기면 이미지를 `postgres:16`으로 되돌리면 된다(마이그레이션을 먼저 내린다. 확장이 켜진 채 되돌리면 `vector` 타입을 못 읽는다).
- **[`vector(1024)` 고정]** 차원이 다른 모델은 못 넣는다 → 결정 2. 필요해질 때 마이그레이션.
- **[쓰지 않는 벡터가 쌓인다]** 텍스트 버전을 올리거나 책이 제적되면 옛 행이 남는다 → 조회가 모델·버전·추천 가능 조건으로 거른다. 정리 명령은 비교 실험이 끝난 뒤(`add-related-books`) 정한다.
- **[YES24 이용 조건]** 원문은 로컬 컨테이너에만 가고 저장하지 않는다. 벡터가 "도서 정보의 축적"에 해당하는지는 `docs/design.md`의 YES24 확인 항목에 더한다. 소장 도서만 임베딩하고 서비스 전 서지 출처를 바꿀 예정이라 MVP에서는 진행한다.
- **[한도 설정 변경을 증분이 모른다]** → `--full`로 다시 적재한다고 README에 적는다.
- **[1주 분량]** 나누지 않고 끝냈다.

## Migration Plan

1. 외부 호출 승인: pgvector 이미지, TEI 이미지, 모델(약 2.3GB) 내려받기.
2. 개발 DB 백업(`pg_dump`)을 만들고 경로를 알린다.
3. `docker-compose.yml`의 DB 이미지를 바꾸고 `docker compose up -d db`. 콜레이션 경고와 기존 테이블 조회를 확인한다.
4. `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
5. 되돌리기: `uv run alembic downgrade -1`(테이블과 확장 제거, 다른 데이터는 그대로) 뒤 이미지를 `postgres:16`으로 되돌린다.

## Open Questions

- 실제 기관 장서(수천 권)를 적재하기 전에 처리 시간을 줄일지(ONNX 변환본, GPU 장비). `add-related-books`에서 텍스트 구성을 바꿔 가며 다시 적재하게 되면 먼저 필요해진다.
  - → archive 뒤 2026-11-11에 같은 가중치의 ONNX 변환본으로 바꿨다(스펙 동작은 그대로라 change 없이). 87권이 배치 32에서 252.7초 → 152.1초, 배치 1에서 167.5초 → 126.5초. 측정과 확인 방법은 `app/central/README.md`의 "실행 방식: ONNX 변환본". 배치 기본값을 32에서 낮출지는 스펙의 기본값을 바꾸는 일이라 `add-related-books`에서 정한다.
- **임베딩 텍스트 구성 비교는 `add-related-books`에서 한다** (2026-11-11 정함). 이번 change는 v1(서명·부제, 저자, 분류, 소개)을 기본으로 끝낸다.
  - 비교할 버전: v1 다 넣기 / 저자 빼기(서명·분류·소개) / 소개만(서명·저자·분류는 키워드 점수로). `TEXT_VERSION`으로 나눠 같은 테이블에 함께 적재한다.
  - 표본 87권으로 버전마다 약 3분 반. 판단 기준은 질의 15~20개와 나와야 할 책을 정해 5위 안에 드는 수를 센다. `add-recommendation-evals`에서 다시 쓴다.
  - 참고 수치(표본, 실제 토크나이저): 임베딩 텍스트 중앙값 275토큰, p95 600, 최대 994. 512토큰을 넘는 책 6권(7%), 잘리는 토큰 중앙값 140. 서명·저자·분류는 중앙값 49자(약 28토큰)라 빼도 넘치는 책은 그대로 넘친다. 한국어 소개는 토큰 하나에 약 1.75자.
  - 소개가 없는 책(표본 3권)은 "소개만" 버전에서 벡터가 없거나 빈약하다. 하이브리드 점수의 "소개가 없으면 임베딩 0" 규칙과 함께 본다.
