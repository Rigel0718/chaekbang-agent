## Why

비슷한 책 추천(`add-related-books`)과 이후의 의미 검색은 모두 도서 임베딩이 있어야 시작할 수 있다. 그런데 검색·추천 전략(임베딩 텍스트 구성, 모델, 점수 합치기)은 아직 정하지 않았다. 그래서 전략과 무관한 부분, 곧 도서를 벡터로 만들어 저장하고 바뀐 책만 다시 만드는 파이프라인을 먼저 확정한다. 텍스트 구성과 모델을 바꿔도 구조가 그대로 유지되게 해서, 다음 change가 추천 품질 실험에만 집중할 수 있게 한다.

`add-related-books`에 묶여 있던 pgvector 도입과 `book_embeddings`를 이 change로 옮긴다. DB 이미지 교체, 임베딩 서버 컨테이너, 적재 CLI만으로 며칠 분량이라 저자 구조화·하이브리드 점수와 한 change에 두면 1주를 넘는다.

## What Changes

- **DB**: 이미지를 `postgres:16`에서 pgvector 이미지(PostgreSQL 16)로 바꾸고 마이그레이션으로 `vector` 확장을 켠다. 기관 데이터 테이블 `book_embeddings`를 더한다(테이블 19개 → 20개).
- **임베딩 서버**: `docker compose`에 Hugging Face Text Embeddings Inference(TEI) CPU 컨테이너를 더한다. 모델은 `dragonkue/snowflake-arctic-embed-l-v2.0-ko`(1024차원)다. 로컬에서 돌려 YES24 소개글이 외부로 나가지 않는다. 앱에는 torch를 설치하지 않고 `httpx`로 부른다.
- **인코더 접점**: 문서(도서)와 질의를 나눠 인코딩하는 접점(`encode_documents`, `encode_queries`, `name`, `dim`)을 두고, TEI 호출은 얇은 어댑터 하나에 둔다. 질의에는 접두어 `query: `를 붙이고 문서에는 붙이지 않는다. 둘 다 정규화하고 입력은 512토큰(설정)으로 자른다.
- **임베딩 텍스트**: 기관 도서의 표시 값(공식 값 먼저)으로 텍스트를 만드는 함수를 별도 모듈에 두고 `TEXT_VERSION`으로 버전을 매긴다.
- **저장**: 기관 도서마다 (모델, 텍스트 버전)별로 벡터 하나와 텍스트의 SHA-256 해시를 저장한다. 원문 텍스트는 저장하지 않는다. 모델이나 텍스트 버전이 다른 벡터가 한 테이블에 공존한다.
- **적재 CLI**: 운영자가 실행하는 `scripts/embed_books.py`(`--full` / `--incremental`). 추천 가능한 기관 도서를 배치로 인코딩하고, 증분은 벡터가 없거나 해시가 달라진 책만 다시 인코딩한다. 진행률과 처리·건너뜀 건수를 출력하고, 종료 코드는 `scripts/enrich_books.py`와 같다.
- **확인 스크립트**: 질의 하나를 인코딩해 한 기관 범위 안에서 코사인 유사도 상위 5권을 출력한다. 평가 표본 87권으로 전체 적재·증분 적재·조회를 한 번에 확인하는 방식(`--sample`)도 둔다.
- **문서**: CLAUDE.md와 `docs/design.md`의 MVP change 순서에 `add-book-embeddings`를 10번으로 끼우고 `add-related-books` 이후를 한 칸씩 민다.

범위 밖: 검색·추천 API와 랭킹 전략, 하이브리드 검색, 비슷한 책, 저자 구조화(`add-related-books`), 대출 기록 기반 취향 반영, 벡터 인덱스(순차 탐색 시간을 재서 필요할 때만).

## Capabilities

### New Capabilities

- `catalog/book-embeddings`: 기관 도서의 임베딩 텍스트 구성, 문서·질의 인코딩 규칙, 벡터와 메타데이터 저장, 전체·증분 적재, 운영자 실행의 출력과 중단, 기관 범위 유사도 조회.

### Modified Capabilities

- `platform/database-schema`: 마이그레이션이 만드는 테이블이 20개가 되고 벡터 확장이 더해진다. 임베딩은 같은 기관의 기관 도서만 가리킨다.

## Impact

- **인프라**: `docker-compose.yml`(DB 이미지 교체, 임베딩 서버 서비스와 모델 캐시 볼륨). 개발 DB 볼륨은 그대로 쓰되 바꾸기 전에 백업한다. 모델 내려받기(약 2.3GB)와 이미지 내려받기는 외부 호출이라 실행 전에 승인받는다. 임베딩 서버는 메모리를 3~4GB 쓸 것으로 보이는데 개발 장비는 7GB다.
- **코드**: `app/central/`(인코더 접점, TEI 어댑터), `app/library/models/`(`BookEmbedding`), `app/library/recommendation/`(임베딩 텍스트, 저장, 적재, 조회), `app/core/config.py`(임베딩 설정), `app/models.py`, `scripts/`(스크립트 2개), `migrations/`.
- **의존성**: `pgvector`(SQLAlchemy 벡터 타입)를 더하고 `httpx`를 실행 의존성으로 올린다. 둘 다 2주 이상 된 정확한 버전으로 고정한다.
- **API**: 바뀌는 것이 없다. REST 엔드포인트와 에이전트 tool을 더하지 않는다.
- **테스트**: 가짜 인코더로 TEI 없이 돈다. 실제 TEI를 쓰는 테스트는 TEI가 떠 있을 때만 돈다.
