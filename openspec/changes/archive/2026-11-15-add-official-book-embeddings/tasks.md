## 0. 시작 전

- [x] 0.1 issue 번호를 받는다(제안 승인 뒤 design을 요약한 issue 제목·본문을 텍스트로 준다). #29
- [x] 0.2 `main`(`add-book-contributors` 머지 `d456541` 포함)에서 브랜치 `add-official-book-embeddings`를 만든다
- [x] 0.3 기준 수치를 남긴다: `docker compose up -d db` 뒤 `uv run pytest` 통과·건너뜀 수(이전 1059 통과, 7 건너뜀), `uv run python -m evals.catalog_search` 결과. 끝날 때 다시 비교한다

## 1. 임베딩 텍스트 모듈 나눔

- [x] 1.1 `kdc_class_name`을 `app/core/kdc.py`로 옮기고 import를 고친다. 기존 KDC 테스트가 그대로 통과한다
- [x] 1.2 `app/core/embedding_text.py`: `TEXT_VERSION`(2), `TextKind`(`full`), `compose`(저자 인자 없음), `content_hash`. 테스트(`tests/core/test_embedding_text.py`): 빈 값 건너뛰기, 부제 붙이기, 소개가 마지막, 같은 값 같은 텍스트, 텍스트 버전 2
- [x] 1.3 `app/central/embedding_text.py`: `official_embedding_text(book, kind)`. 테스트: 공식 값만 들어간다, 소개 없는 공식 서지, 저자 미포함(글/그림 저자 원문의 이름이 텍스트에 없다)
- [x] 1.4 `app/library/recommendation/embedding_text.py`를 `library_embedding_text(book, kind)`로 고친다(`shown`을 쓰지 않는다). 테스트(`tests/library/test_embedding_text.py`): ISBN 없는 책, 저자 미포함, 두 층의 같은 조립 규칙(같은 값이면 같은 텍스트). 저자가 든 기대 텍스트와 "잘릴 때 서명·저자·분류가 남는다" docstring을 고친다
- [x] 1.5 `uv run pytest tests/platform/test_package_layers.py`가 통과한다(운영자 층이 기관 모델을 import하지 않는다)

## 2. 스키마

- [x] 2.1 `app/central/models.py`: `EMBEDDING_DIM`을 옮기고 `OfficialBookEmbedding`을 더한다. `Book.series_keys`(`text[]`, NOT NULL, 서버 기본값 `'{}'`)를 더한다
- [x] 2.2 `app/library/models/embedding.py`: `kind` 열(빈 값 금지)과 유니크 키 교체
- [x] 2.3 `app/models.py`의 `SHARED_TABLES`에 `official_book_embeddings`를 더한다
- [x] 2.4 마이그레이션 하나: 새 테이블, `book_embeddings.kind`(기존 행 `full` 뒤 기본값 제거)와 유니크 키 교체, `books.series_keys`. 테스트 DB에서 `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`가 통과한다
- [x] 2.5 스키마 테스트(`tests/platform/test_database_schema.py`): 테이블 22개, 기관 공통 구분, 공식 서지 임베딩 테이블의 저장 계층 규칙 넷, 종류가 다른 기관 도서 벡터 공존, 종류가 빈 행 거부, 공식 서지를 지우면 벡터도 지워짐, 시리즈 키 없는 공식 서지는 빈 목록
- [x] 2.6 개발 DB를 백업하고 경로를 알린 뒤 2.4의 명령을 개발 DB에 적용한다. `uv run python scripts/rebuild_contributors.py --check`의 차이가 0이다

## 3. 두 층 적재와 조회

- [x] 3.1 `EmbeddingRun`과 배치 흐름의 뼈대를 `app/central/`로 옮긴다(대상 읽기, 텍스트 만들기, 저장을 층이 넘긴다)
- [x] 3.2 `app/central/official_embeddings.py`: `run_official_embedding`(대상은 공식 서지 전부, `within`으로 좁힘). 테스트(`tests/central/` 또는 `tests/catalog/`): 전체, 증분 0건, 새 공식 서지만, 같은 키는 한 행, 텍스트 버전 공존, 원문 미저장, 배치 크기, 중간 실패 뒤 이어 하기
- [x] 3.3 `app/library/recommendation/embeddings.py`: `run_library_embedding`(대상은 연결되지 않은 추천 가능한 책), `held_official_ids`. 테스트: 연결된 책은 기관 도서 벡터 없음, ISBN 없는 책 포함, 제적·분실만 남은 책, 바뀐 책만 다시, 기관을 지정한 실행(두 층), 나중에 연결된 책
- [x] 3.4 기관 값이 섞이지 않는다는 테스트: 공식 서지에 없는 소개, 기관마다 다른 값(해시가 공식 값만의 해시와 같다), 기관 값을 고쳐도 증분 0건, 두 기관이 가진 책은 한 번만 인코딩
- [x] 3.5 `similar_books`를 두 층 조회로 고친다. 테스트(`tests/library/test_book_embeddings.py`): 유사도 순서, 두 층이 한 순위로, 다른 기관의 책, 다른 기관만 가진 공식 서지, 두 기관이 가진 같은 책은 한 번, 적재 뒤 제적, 연결된 책에 남은 기관 도서 벡터, 다른 모델, 종류가 다른 벡터, 적재 전 조회
- [x] 3.6 배치 기본값을 4로 바꾼다(`app/core/config.py`, `.env.example`). 테스트: 배치를 주지 않으면 5권이 4권, 1권으로 불린다
- [x] 3.7 `scripts/embed_books.py`: `--layer`, 층별 진행과 건수, 소개 없음 건수 출력. 테스트(`tests/library/test_embedding_scripts.py`): 완료 출력(층별), 층을 지정한 실행, 서버 꺼짐, 잘못된 인자, 다른 모델, 기본 종류 `full`
- [x] 3.8 `scripts/embedding_search.py`: `--library-id`와 `--sample`이 두 층을 쓴다. 기존 스크립트 테스트를 고쳐 통과시킨다
- [x] 3.9 `tests/embedding_live/`의 표본 적재 테스트를 두 층으로 고친다(임베딩 서버가 꺼져 있으면 건너뛴다)
- [x] 3.10 조회 속도를 잰다: 테스트 DB에 무작위 정규화 벡터 5,000건(공식 4,500, 기관 500)을 넣고 상위 5권 조회 네 번의 시간을 design 결정 7에 적는다. 100ms를 넘으면 수치만 보고한다
- [x] 3.11 문서: `app/central/README.md`(맡는 일, 구성, 임베딩의 두 층과 배치 기본값), `app/library/README.md`(기관 도서 벡터의 대상, 두 층 조회)를 고친다. README의 명령을 적힌 대로 실행해 사용법이 맞는지 확인한다

## 4. 공식 서지 만들기 함수와 시리즈 키

- [x] 4.1 `Yes24Item.series_names`(응답 목록 그대로)를 더한다. 테스트(`tests/external/`): 시리즈 여러 개, 쉼표가 든 시리즈명, 시리즈 없음, 기존 `series_name`은 그대로
- [x] 4.2 `_create_official`을 `app/central/official_books.py`의 `create_official`로 옮기고 시리즈 키를 저장한다. 채움이 이것을 부른다. 테스트: 시리즈 키 시나리오 넷(여러 개, 쉼표, 없음, 표기가 다른 같은 시리즈), 이미 있는 공식 서지는 고치지 않는다. 기존 채움 테스트가 그대로 통과한다
- [x] 4.3 `scripts/rebuild_contributors.py --check`가 "시리즈명이 있는데 시리즈 키가 빈 공식 서지" 건수를 함께 출력한다. 테스트 하나
- [x] 4.4 문서: `app/central/README.md`의 기여자 절에 "공식 서지를 만드는 경로는 `create_official`을 부른다"와 시리즈 키를 적는다

## 5. 실험 장서 받기

- [x] 5.1 `definitions.py`: 스테디셀러 엔드포인트, 성인 표시 키, 저장하지 않는 변동 값 키 목록. `app/central/external/yes24/category.py`: `steady_sellers`(원본 상품 목록). 테스트(`httpx.MockTransport`): 요청 파라미터, 빈 결과, 외부 장애
- [x] 5.2 `evals/collection/plan.py`: design 결정 12의 분야 구성(분야 키, 이름, 카테고리 id, 목표, `holdout`, 받는 순서). 테스트: 카테고리 id 형식, 목표 합계 525, 하위 카테고리가 상위보다 앞
- [x] 5.3 `evals/collection/fetch.py`: 받기, 거르기, 중복, 기록, 변동 값 제거, 파일 쓰기, `--dry-run`. 테스트: 목표에서 자름, 책이 아닌 상품 제외, 분야 사이의 중복, 목표보다 적은 분야, 기록 내용, 변동 정보 미저장, 시리즈 목록 유지, 파일이 이미 있음, 중간에 외부 장애, 호출 수 미리 보기
- [x] 5.4 `.gitignore`에 `evals/collection/data/`를 더한다. `git status`에 데이터 폴더가 나오지 않는다
- [x] 5.5 **외부 호출(승인 필요)**: 카테고리 API 확인 1~3회(`detail=Y`의 소개·시리즈·분류, 12자리 하위 카테고리, `totalCount`). 결과를 design 결정 11에 적는다. 어긋나면 받기 전에 design·스펙·5.1~5.3을 고치고 알린다
- [x] 5.6 **외부 호출(승인 필요)**: `uv run python -m evals.collection.fetch --dry-run`의 호출 수를 알리고 승인받아 받는다. 분야별 받은 권수, 거른 건수(이유별), 소개 없는 책 수, 평가 표본과 겹친 ISBN 수를 보고한다

## 6. 실험 장서 적재

- [x] 6.1 `app/seed/experiment.py`: 가상 기관과 계정, 공식 서지(`create_official`), 기관 도서(ORM), 사본, 어린이 구분. design 결정 16의 규칙. `scripts/seed_experiment.py`: 연결·마이그레이션·파일 확인, 한 트랜잭션, 건수 출력
- [x] 6.2 테스트(`tests/platform/test_experiment_collection.py`, 테스트 안에서 만든 문서): 빈 DB에 적재, 기여자와 시리즈 키, 이미 있는 공식 서지, 상태 구성(40권), ISBN 없는 책의 값과 저자 키, 어린이 구분, ISBN 없는 어린이 책, 두 번 실행, 다른 기관은 그대로, 파일 없음
- [x] 6.3 테스트: 같은 응답 상품을 채움과 적재로 각각 넣으면 공식 서지의 서지 값, 기여자, 시리즈 키가 같다(`catalog/books`의 "두 경로의 같은 결과")
- [x] 6.4 개발 DB를 백업하고 경로를 알린 뒤 `uv run python scripts/seed_experiment.py`를 두 번 돌린다. 두 번째 실행 뒤 건수가 같고, 시드 기관 둘의 기관 도서·사본·회원·대출 건수가 그대로인지 SQL로 확인한다
- [x] 6.5 역할 표 넓히기: 500권의 기여자에서 기여자 0명인 공식 서지와 이름 끝에 붙어 남은 역할 표기를 훑는다. 찾은 표기를 `app/core/contributors.py`와 `tests/external/test_yes24_contributors.py`에 더하고 `uv run python scripts/rebuild_contributors.py && uv run python scripts/rebuild_contributors.py --check`(차이 0). 평가 표본의 역할별 건수 테스트가 달라지면 전후 수치를 보고한다
- [x] 6.6 실험 장서 전체 테스트(`tests/samples/`, 파일이 없으면 건너뜀): 모든 책이 `parse_item`으로 읽히고 기여자가 1명 이상이며 역할 표기가 이름에 붙어 남은 것이 없다
- [x] 6.7 문서: `evals/collection/`의 모듈 설명(받은 날짜와 방식, 다시 받지 않는 이유), `evals/librarian/fetch_sample.py`·`catalog.py`의 주석을 고친다

## 7. 텍스트 버전 2 임베딩 적재와 확인

- [x] 7.1 `docker compose --profile embedding up -d embedder` 뒤 `uv run python scripts/embed_books.py --full`을 백그라운드로 돌린다(약 12분). 층별 건수, 걸린 시간, 소개 없음 건수를 보고한다
- [x] 7.2 `uv run python scripts/embed_books.py --incremental`의 인코딩 건수가 두 층 모두 0이다
- [x] 7.3 `uv run python scripts/embedding_search.py "<질의>" --library-id <가상 기관>`을 질의 서너 개로 돌린다. 연결된 책과 ISBN 없는 책이 한 결과에 함께 나오는 질의가 하나 이상 있고, 분실·제적 사본만 남은 책과 다른 기관의 책이 없다는 것을 SQL로 대조한다
- [x] 7.4 `uv run pytest tests/embedding_live`를 돌린 뒤 `docker compose --profile embedding stop embedder`로 서버를 내린다

## 8. 문서와 마무리

- [x] 8.1 `CLAUDE.md`: 현재 단계, 자주 쓰는 명령, 디렉터리 구조, YES24 예외 문구, 임베딩 텍스트 비교 문장(기본은 저자 없음, "저자 넣기"가 비교 대상), 도메인 용어(공식 서지 벡터, 기관 도서 벡터, 시리즈 키, 실험 장서). 적힌 명령이 실제 옵션과 맞는지 `--help`로 확인한다
- [x] 8.2 `docs/design.md`: 데이터 모델 표, YES24 이용 조건의 예외, YES24 확인 항목, 일정 표의 완료 기준
- [x] 8.3 `app/central/README.md`의 YES24 이용 조건과 "새 YES24 기능 추가"를 고친다
- [x] 8.4 스펙 시나리오와 테스트의 대응을 점검한다: delta 넷의 시나리오마다 테스트 docstring에 요구사항 이름이 있다
- [x] 8.5 `uv run pytest`, `uv run ruff check . && uv run ruff format .`, `openspec validate add-official-book-embeddings --strict`가 통과한다. 0.3의 기준 수치와 비교해 `evals.catalog_search` 결과가 같은지, 달라진 테스트 수와 이유를 보고한다
- [x] 8.6 design의 측정값과 확인 결과(카테고리 API, 조회 속도, 적재 시간, 분야별 권수)를 채우고 요약한 뒤 멈춘다

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다.
- PR은 요청하면 제목과 본문 텍스트만 쓴다(push와 PR 생성은 하지 않는다).
