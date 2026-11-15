## 0. 시작 전

- [x] 0.1 issue 번호를 받는다(제안 승인 뒤 design을 요약한 issue 제목·본문을 텍스트로 준다). #31
- [x] 0.2 `main`(`add-official-book-embeddings` 머지 `d18e61e` 포함)에서 브랜치 `add-recommendation-experiments`를 만든다
- [x] 0.3 기준 수치를 남긴다: `docker compose up -d db` 뒤 `uv run pytest` 통과·건너뜀 수, `uv run python -m evals.catalog_search` 결과. 끝날 때 다시 비교한다 (2026-11-15: 1132 통과, 7 건너뜀. catalog_search 기준은 `runs/20261115-201742`)

## 1. 임베딩 텍스트 종류

- [x] 1.1 `app/core/embedding_text.py`: `TextKind`에 `with_author`, `description`, `title`, `category`를 더하고 `compose`에 `author` 인자와 종류별 줄 고르기를 둔다(`TEXT_VERSION`은 2 그대로). 테스트(`tests/core/test_embedding_text.py`): 저자 넣기, 소개만, 서명만과 분류만, 기존 `full` 기대 텍스트 그대로
- [x] 1.2 `app/central/embedding_text.py`, `app/library/recommendation/embedding_text.py`가 저자 원문을 넘긴다. 테스트: 공식 서지 텍스트에 기관 저자 없음, 두 층의 같은 종류 규칙, 기본 종류 저자 미포함(기존)
- [x] 1.3 `run_layer`가 빈 텍스트를 인코딩하지 않고 `EmbeddingRun.blank`로 센다. 테스트: 소개 없는 책(인코더에 빈 문자열이 가지 않는다, 빈 텍스트 1건)
- [x] 1.4 `scripts/embed_books.py --kind`와 출력의 종류·빈 텍스트 건수. 테스트(`tests/library/test_embedding_scripts.py`): 종류 지정(`full` 해시·고친 시각 그대로), 없는 종류(종료 코드 1, 인코딩 없음)
- [x] 1.5 `app/central/README.md`(텍스트 종류, 빈 텍스트)를 고치고 적힌 명령의 사용법(`--help`)이 맞는지 확인한다

## 2. 유사도 조회 넓히기

- [x] 2.1 `similar_books`에 `within`(순위 전에 거는 조건)과 결과 수를 받는다. 테스트(`tests/library/test_book_embeddings.py`): 조건을 먼저, 깊은 조회(40권 중 30권), 조건이 다른 기관의 책을 가리킴. 기존 조회 테스트가 그대로 통과한다
- [x] 2.2 `weights`(종류별 가중 평균, 없는 종류는 빼고 평균)를 더한다. 테스트: 가중 평균(0.65), 없는 종류는 빼고 평균, 종류 하나는 지금과 같음
- [x] 2.3 `book_vectors`(MMR용, 그 기관의 책만, 두 층). 테스트: 두 층의 벡터를 돌려줌, 다른 기관의 id는 빠짐
- [x] 2.4 테스트 DB 5,000건(공식 4,500, 기관 500)에서 종류 셋 합친 상위 30권 조회 시간을 두 번 재서 design 결정 5에 적는다. 테스트 DB에 대량 삽입·롤백 뒤 `VACUUM ANALYZE`를 한다

## 3. 주제로 찾기 순위 함수

- [x] 3.1 `app/library/recommendation/ranking.py`: `fuse_rrf`, `cap_series`, `mmr`(순수 함수). 테스트(`tests/library/test_ranking.py`): 점수 계산, 신호 가중치, 근거, 같은 점수, 상한 1, 시리즈 없는 책, 비슷한 책 뒤로, λ가 1
- [x] 3.2 `app/library/recommendation/topic.py`: `keyword_ranking`(키워드 검색과 같은 점수, 깊이). 테스트: 상한보다 깊게(앞 10권이 `search_collection`과 같다), 맞지 않는 책
- [x] 3.3 `find_by_topic`과 `TopicSettings`. 테스트(`tests/library/test_topic_recommendation.py`): 어린이 조건(어린이 기능의 조건을 넘김), 추천할 수 없는 책, 다른 기관의 책, 두 번 실행 같은 결과
- [x] 3.4 `uv run pytest tests/platform/test_package_layers.py`가 통과한다(공통 코드가 어린이 기능을 import하지 않는다). `app/library/README.md`의 추천 패키지 설명을 고친다

## 4. 실험 틀

- [x] 4.1 `.gitignore`에 `evals/recommendation/data/`를 더한다. `evals/recommendation/keys.py`: 책 키(`isbn:`/`acc:`), 실험 장서 파일에서 분야 읽기(등록번호의 순서 번호). 테스트(`tests/evals/test_recommendation_sets.py`): 두 갈래 키, 데이터 폴더(무시 목록)
- [x] 4.2 `sets.py`: 세 종류 세트 읽기와 검사. 테스트: 빠진 칸, 세 종류 읽기, 남겨 둔 분야의 질의, 남겨 둔 분야의 기준 책, 질의 파일의 ISBN
- [x] 4.3 `label.py`: 라벨 도구(카드, 0·1·2, Enter는 0, 답마다 저장, 이어 하기, 단계 기록), 실행 전 후보, 실행 뒤 보충 목록. 입력을 넘겨 받는 함수로 테스트: 이어 하기, 잘못된 답, 분야와 어린이, 라벨 없는 책만
- [x] 4.4 `metrics.py`: nDCG@5, Hit@5, Recall@10, 겹침, 라벨 없음, 짝 비교(이김·비김·짐, 고정 시드 부트스트랩). 테스트: 값 계산, 라벨 없는 책, 같은 변형
- [x] 4.5 `cache.py`(질의 벡터), `variants.py`(design 결정 7의 이름들), `__main__.py`(`topic` 실행, 실험 기관 찾기, 지문, 요약·질의별 결과 쓰기, 위반 검사). 테스트: LLM 없이, 없는 변형, 실험 기관이 없음, 없는 키, 어린이 위반, 묶음별, 두 번 실행, 캐시, 라벨이 바뀜
- [x] 4.6 `pick.py`: 기준 책 20권·최근 기록 10개를 규칙으로 고른다(책 키의 SHA-256 순서, 남겨 둔 분야 제외, design 결정 8의 구성). 테스트: 두 번 고르면 같다, 남겨 둔 분야의 책이 없다
- [x] 4.7 `evals/recommendation/README.md`: 명령, 세트·라벨 위치와 백업, 라벨 기준, 채택 규칙. 적힌 명령의 `--help`가 맞는지 확인한다
- [x] 4.8 라벨 도구에 목록 방식을 더한다(2026-11-16, 카드 방식으로는 주제만 1,384건이라 사용자가 멈춤): 실행 전 단계의 기본, `--cards`로 카드 방식, `?번호`로 카드 보기, `Labels.put_many`. 테스트: 목록에서 고르기, 잘못된 번호, 확인하지 않고 끝내기. README를 고친다
- [x] 4.9 라벨 초안과 검수(2026-11-16, 목록 방식도 오래 걸려 바꿈): `Labels`에 단 쪽 `by`, 초안 넣기(`draft.py`: 사람 라벨은 덮지 않음), 검수 화면(`review.py`: 로컬 페이지, 누를 때마다 저장), 요약에 단 쪽별 수. 테스트: 초안 기록, 검수에서 고침, 사람 라벨은 덮지 않음, 단 쪽별 수. README를 고친다

## 5. 평가 세트와 라벨 (사용자와 함께)

- [x] 5.1 Claude가 장서를 보지 않고 주제 질의 30개 초안을 `evals/recommendation/sets/topic.json`에 쓴다(어린이 12/일반 18, 주제어 18/상황 12, 조정 20/확인 10, 남겨 둔 분야 없음). 세트 검사가 통과한다. 사용자에게 보이고 고친 뒤 확정한다 (2026-11-15 사용자가 초안 그대로 확정)
- [x] 5.2 `uv run python -m evals.recommendation.pick`으로 기준 책·최근 기록을 고르고 사용자가 확인한다(바꾸면 바꾼 파일이 기준) (2026-11-16: 골라서 `data/seeds.json`에 두었다. 두 세트를 쓰는 `add-related-book-experiments`에서 사용자가 확인한다)
- [x] 5.3 Claude가 주제 질의의 실행 전 라벨 초안을 달고 사용자가 검수 화면에서 확인·고친다. 끝날 때까지 어떤 변형도 돌리지 않는다. 단계별 라벨 수를 기록한다. 비슷한 책·최근 기록의 라벨은 `add-related-book-experiments`로 넘긴다(2026-11-16 결정) (2026-11-16: 초안 1,384건, 사용자가 6개 질의에서 13건을 고침)

## 6. 적재와 실행

- [x] 6.1 개발 DB를 `pg_dump`로 백업하고 경로를 알린다. 임베딩 서버를 띄우고 실험 기관만 종류 넷을 적재한다(`--full --library-id <실험 기관> --kind …`, 약 20분, 백그라운드). 종류마다 `--incremental`이 0건인지 확인한다
- [x] 6.2 단계 0~2(기준, 벡터 입력, 텍스트 종류)를 조정 세트로 실행하고 승자를 `variants.py`에 적는다 (승자: 벡터 질의 입력은 문장, 텍스트 종류는 `full`. `BEST_*` 그대로)
- [x] 6.3 단계 3·3'(합치기 격자, 합친 순위에서 텍스트 종류)를 실행하고 승자를 정한다 (승자: k 60, 1:1, `full`)
- [x] 6.4 단계 4·5(시리즈 묶기, MMR)를 실행하고 승자를 정한다 (둘 다 끔. 겹침만 줄어 `add-related-books`에서 다시 정한다)
- [x] 6.5 보고할 변형들의 상위 10권으로 보충 목록을 만들고 사용자가 라벨을 단다. 상위 5권의 라벨 없음이 0이 될 때까지 (2026-11-16: 전체 변형의 상위 10권에서 583건. Claude가 초안을 달았고 사용자 검수는 하지 않음. 상위 5권 라벨 없음 0)
- [x] 6.6 최종 실행을 두 번 해(조정·확인 모두) 요약이 시각·걸린 시간 줄을 빼고 같은지 확인한다. 임베딩 서버를 내린 상태로 한 번 더 돌려 캐시만으로 같은 수치가 나오는지 확인한다. 임베딩 서버를 내린다 (`20261116-032456`과 `20261116-032739`가 같다. 둘 다 서버를 내린 채 캐시로)

## 7. 결정 기록과 문서

- [x] 7.1 design의 "결과"에 단계별 표(조정·확인, 묶음별), 채택한 설정과 근거, 텍스트 종류 비교와 기본 결정(추천과 이유), 지문, 걸린 시간을 쓴다. 기본 종류가 `full`이 아니면 스펙 delta를 먼저 고치고 알린다
- [x] 7.2 `TopicSettings` 기본값을 채택한 설정으로 둔다. 테스트가 그대로 통과한다 (기본값이 이미 채택한 설정이라 바꾸지 않음)
- [x] 7.3 `CLAUDE.md`(현재 단계, change 순서에 `add-related-book-experiments`, 명령, 디렉터리 구조, 임베딩 텍스트 기본), `docs/design.md`(주차 표, 추천 품질 평가의 평가 세트·라벨·지표·채택 규칙)를 고친다

## 8. 마무리 확인

- [x] 8.1 스펙 시나리오마다 테스트 docstring에 "요구사항 / 시나리오"가 있는지 점검한다(공백을 하나로 접어 비교) (시나리오 65개 모두 있음)
- [x] 8.2 `uv run pytest`와 `uv run ruff check . && uv run ruff format --check .`가 통과한다. 0.3의 기준과 통과 수를 비교하고, `uv run python -m evals.catalog_search` 결과가 같은지 확인한다(바뀌면 이유와 전후 수치를 보고한다) (2026-11-16: 1198 통과, 7 건너뜀. 기준 1132에서 66개 늘었다. 첫 전체 실행에서 `test_lookup_speed`가 한 번 실패했고 테스트 DB `VACUUM ANALYZE` 뒤 통과. catalog_search는 `runs/20261116-033720`이 기준과 같다)
- [x] 8.3 `openspec validate add-recommendation-experiments --strict`가 통과한다

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다.
- 다음 change `add-related-book-experiments`를 제안한다(이번 세트·라벨 도구와 확정한 텍스트 종류를 쓴다). 비슷한 책 821건·최근 기록 599건의 실행 전 라벨을 그 change에서 목록 방식으로 단다.
- 그 앞에 작은 change `fix-korean-title-order`를 먼저 한다(2026-11-15 결정): DB collation이 `en_US.utf8`이라 서명 정렬이 가나다순이 아니다. 서명 정렬 6곳(`library_books.py`, `search.py`의 `ranked_query`, `lookup.py` 4곳)에 `COLLATE "ko-x-icu"`를 쓰는 안을 추천했다. 이번 실험 중에는 바꾸지 않는다(키워드 동점 순서가 기준이라서).
