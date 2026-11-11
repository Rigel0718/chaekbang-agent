## 1. 사전 확인 (외부 호출은 실행 전에 알리고 승인받는다)

- [x] 1.1 이미지 태그 확정: pgvector PostgreSQL 16 trixie 변형의 정확한 버전(릴리스 2주 이상), TEI CPU 이미지의 정확한 버전 태그(`cpu-1.9.4` 존재 여부). `pgvector` Python 패키지와 `httpx`의 고정 버전도 정한다
  - 확정(2026-11-11): `pgvector/pgvector:0.8.6-pg16-trixie`(8월 13일. 0.8.7은 10월 31일이라 2주가 안 됨), `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4`(9월 15일, 태그 있음), `pgvector==0.5.1`(10월 9일), `httpx==0.28.1`(지금 설치된 버전)
- [x] 1.2 승인받은 뒤 TEI 컨테이너를 띄워 모델(약 2.3GB)을 내려받고, safetensors만 있는 이 모델이 CPU 이미지에서 뜨는지 확인한다. 안 뜨면 멈추고 대안을 묻는다
- [x] 1.3 TEI `/docs`로 `/embed` 요청 필드(`inputs`, `normalize`, `truncate`, `prompt_name`), `/info` 응답, `/tokenize`를 확인하고, 512토큰으로 자르는 방법을 design 결정 5의 순서로 정한다. 정한 방법을 design.md에 적는다(스펙과 달라지면 delta를 먼저 고치고 알린다)

## 2. pgvector와 스키마

- [x] 2.1 개발 DB를 `pg_dump`로 백업하고 경로를 알린다
- [x] 2.2 `docker-compose.yml`의 DB 이미지를 pgvector 이미지로 바꾸고 다시 띄운다. 콜레이션 버전(2.41)과 경고 유무, 기존 데이터 조회를 확인한다
- [x] 2.3 `pgvector` 의존성을 더하고 `httpx`를 실행 의존성으로 올린다(정확한 버전 고정)
- [x] 2.4 `app/library/models/embedding.py`에 `BookEmbedding`을 만들고 `app/models.py`의 `TENANT_TABLES`에 더한다
- [x] 2.5 마이그레이션: `vector` 확장, `book_embeddings`(복합 외래 키 CASCADE, 유니크 키, `vector(1024)`). `migrations/env.py`가 벡터 타입을 알아보는지 확인한다
- [x] 2.6 `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
- [x] 2.7 `tests/platform/test_database_schema.py`: 테이블 20개와 벡터 확장, 임베딩 테이블의 저장 계층 규칙(중복 키, 차원), 다른 기관 도서로 임베딩 직접 저장 거부

## 3. 인코더 접점과 TEI 어댑터

- [x] 3.1 `app/core/config.py`와 `.env.example`에 임베딩 설정(`EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_MAX_TOKENS`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_PORT`)을 더한다
- [x] 3.2 `app/central/embedding.py`: `Embedder` 프로토콜, `EmbeddingError`와 종류
- [x] 3.3 `app/central/external/tei.py`: `TeiEmbedder`(`encode_documents`, `encode_queries`, 모델 확인). 질의 접두어 상수, `normalize`·`truncate`, 차원 검사, 오류 구분
- [x] 3.4 어댑터 테스트(`httpx.MockTransport`): 질의 접두어, 문서에는 접두어 없음, 정규화·잘라내기 요청, 차원 불일치, 연결 실패·서버 오류·모델 불일치 구분
- [x] 3.5 `docker-compose.yml`에 `embedder` 서비스(프로필 `embedding`, 로컬 포트, 모델 캐시 볼륨)를 더한다. 입력 한도를 낮춰 띄우는 `docker/embedder/start.sh`를 함께 둔다(design 결정 5, 구현 중 추가)
- [x] 3.6 가짜 인코더 도우미를 `tests/`에 만든다(해시로 정해지는 정규화 벡터, 호출 기록, 벡터를 직접 정하는 방식, 실패를 내는 방식)

## 4. 임베딩 텍스트

- [x] 4.1 `app/library/recommendation/embedding_text.py`: `TEXT_VERSION`, `build_embedding_text`, `content_hash`. DB·인코더·설정을 import하지 않는다
- [x] 4.2 테스트: 공식 값 먼저, 빈 값 건너뛰기, ISBN 없는 책, 같은 값 같은 텍스트와 해시, 소개가 마지막에 오는 순서

## 5. 저장, 적재, 조회

- [x] 5.1 `app/library/recommendation/embeddings.py`: 대상 조회(`recommendable_ids` 조건을 다시 쓰고 기관 조건을 선택으로), upsert, `run_embedding`(전체·증분, 배치마다 커밋, 진행 콜백, 인코딩 중 트랜잭션 없음)
- [x] 5.2 `similar_books`: 기관·모델·텍스트 버전·추천 가능 조건으로 거르고 코사인 거리 순으로 가져온다
- [x] 5.3 적재 테스트: 전체 적재, 증분 재실행 0건(인코더 호출 없음), 바뀐 책만, 새 책만, 배치 크기, 전체 재실행, 같은 키 한 행, 텍스트 버전 공존, 모델 이름 공존, 원문 미저장
- [x] 5.4 대상 테스트: 제적·분실 사본만 남은 책 제외, ISBN 없는 책 포함, 기관을 지정한 실행(다른 기관 벡터 없음)
- [x] 5.5 중단 테스트: 두 번째 배치 실패 시 첫 배치가 남고 증분으로 이어 한다
- [x] 5.6 조회 테스트: 유사도 순서, 다른 기관의 책 없음, 적재 뒤 제적된 책 없음, 다른 모델의 벡터가 섞이지 않음, 적재 전 빈 결과

## 6. 스크립트

- [x] 6.1 `scripts/embed_books.py`: `--full|--incremental`, `--library-id`, `--batch-size`, 진행·요약 출력, 종료 코드 0/1/2, 임베딩 서버·DB·마이그레이션 안내
- [x] 6.2 테스트: 완료 출력과 종료 코드, 임베딩 서버 꺼짐(2), 잘못된 인자(1), 모델 불일치(1)
- [x] 6.3 `scripts/embedding_search.py`: `"질의" --library-id N`으로 상위 5권 출력, `--sample`로 테스트 DB 트랜잭션에서 표본 적재 → 전체 → 증분(0건) → 상위 5권 → 되돌리기
- [x] 6.4 테스트: 가짜 인코더로 상위 5권 출력, 표본 파일이 없을 때 `--sample`의 안내와 종료 코드

## 7. 실제 임베딩 서버로 확인 (TEI가 떠 있을 때만)

- [x] 7.1 `tests/embedding_live/`(마커 `tei`, 서버에 닿지 않으면 폴더 전체 건너뛰기): 앱 접두어 방식과 TEI `prompt_name="query"` 방식의 벡터가 같음, 512토큰 잘림, 정규화(길이 1), 1024차원
- [x] 7.2 표본이 있을 때: 표본의 앞 6권으로 전체 적재 → 증분 재실행 0건 → 조회(87권 전체는 3분 반이 걸려 7.3의 `--sample`로 확인한다)
- [x] 7.3 `uv run python scripts/embedding_search.py "질의" --sample`을 돌려 상위 5권이 나오는지 확인하고 결과를 보고한다
- [x] 7.4 측정해 design.md에 적는다: 87권 전체 적재 시간과 5,000권 환산, 임베딩 서버 메모리(`docker stats`), 5,000권 순차 탐색 조회 시간(세 번 재서 중앙값). 100ms를 넘으면 인덱스를 묻는다

## 8. 문서와 마무리

- [x] 8.1 `app/central/README.md`, `app/library/README.md`에 인코더 접점, 임베딩 텍스트·적재·조회, 운영자 실행 규칙을 적는다. 모델을 바꾸는 방법과 한도 변경 뒤 `--full`을 포함한다
- [x] 8.2 CLAUDE.md: 기술 스택(pgvector, TEI), 자주 쓰는 명령(임베딩 서버 실행, `embed_books.py`, `embedding_search.py`), 디렉터리 구조, 현재 단계
- [x] 8.3 `docs/design.md`: 데이터 모델의 `book_embeddings` 설명(모델·텍스트 버전·해시, 원문 미저장), YES24 확인 항목에 벡터 저장을 더한다
- [x] 8.4 `uv run pytest`와 `uv run ruff check . && uv run ruff format .`가 통과하는지 확인한다
- [x] 8.5 모든 스펙 시나리오가 테스트에 대응하는지 점검하고(docstring의 요구사항 이름), 한 일을 요약한 뒤 멈춘다
