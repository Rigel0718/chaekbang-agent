## 0. 시작 전

- [x] 0.1 issue 번호를 받는다(design을 요약한 issue 제목·본문을 텍스트로 준다). #35
- [x] 0.2 `main`(`fix-korean-title-order` 머지 `3dbfdf0`)에서 브랜치 `add-related-book-experiments`를 만든다
- [x] 0.3 기준 수치를 남긴다: `uv run pytest` 1216 통과·7 건너뜀(2026-11-16). `topic --split all --variants current,hybrid-k60`의 `runs/20261116-110040`이 `20261116-104400`과 같다(요약은 시각·걸린 시간·커밋 줄 빼고, `results.json`은 그대로)
- [x] 0.4 `uv run python -m evals.catalog_search` 결과를 기준으로 남긴다 (2026-11-16: `evals/catalog_search/data/runs/20261116-111631`)

## 1. topic 기준 다시 맞추기와 문서

- [x] 1.1 `CLAUDE.md` 현재 단계: `fix-korean-title-order`를 끝난 것으로, 진행 중 change를 `add-related-book-experiments`로 고친다
- [x] 1.2 라벨 파일을 `/home/pollux/chaekbang-backups/labels-<시각>/`에 백업하고 경로를 알린다 (`/home/pollux/chaekbang-backups/labels-20261116-1117/`, `seeds.json`도 함께)
- [x] 1.3 topic 23개 변형을 `--split all`로 돌리고(질의 벡터 캐시, 서버 없이) `draft dump topic --pool <실행>`으로 상위 10권의 라벨 없는 책을 모은다. Claude가 보충 초안을 달고(어느 변형의 책인지 보지 않고) `draft apply topic --pool`로 넣는다. 건수를 알린다 (2026-11-16: 실행 `20261116-111716`, 라벨 없는 책 37건, 1 이상 12건)
- [x] 1.4 다시 돌려 상위 5권 라벨 없음 0을 확인하고, design "결과"에 topic 기준 표(조정·확인, `current`·`vec-text`·`hybrid-k60`·`series1`·`mmr0.7`)를 적는다. `hybrid-k60` 채택이 뒤집히면 멈추고 알린다 (2026-11-16: 실행 `20261116-112024`, 라벨 없음 0, 채택 그대로)

## 2. 저장된 벡터로 이웃 조회

- [x] 2.1 `app/library/recommendation/embeddings.py`: 두 갈래 조회를 벡터를 받는 내부 함수로 나누고 `similar_books`는 인코딩 뒤 그것을 부른다. 기존 `similar_books` 테스트가 그대로 통과한다
- [x] 2.2 `neighbors_of`(기준 책들의 저장 벡터 평균, 두 층, 종류·가중치, `within`, 깊이, 그 기관의 책만). 테스트(`tests/library/test_book_embeddings.py`): 인코딩 없음, 두 층의 기준 책, 여러 권의 평균, 다른 기관의 기준 책 벡터

## 3. 비슷한 책 신호와 합치기

- [x] 3.1 `app/library/recommendation/related.py`: `series_ranking`, `kdc_ranking`(소수점 첫째 자리까지, 표시 값), `category_ranking`(같은 외부 분류 안 벡터 순서), `neighbor_ranking`, `author_ranking`(`same_author_books` 재사용). 테스트(`tests/library/test_related_recommendation.py`): 같은 시리즈, 시리즈 없는 기준 책, 같은 세목, KDC 없는 기준 책, 같은 외부 분류, 가까운 순서, 벡터 없는 기준 책
- [x] 3.2 `editions_of`(판본 표기 지운 서명의 비교용 값 + 지은이 겹침). 테스트: 개정판, 서명만 같은 다른 책
- [x] 3.3 `SimilarSettings`와 `find_similar`(RRF·규칙 먼저, 기준 책·판본 빼기, 시리즈 묶기, MMR, 근거). 테스트: 근거, 규칙 신호 먼저, 신호가 모두 비어 있음, 어린이 조건, 추천할 수 없는 책, 다른 기관의 기준 책, 두 번 실행
- [x] 3.4 `uv run pytest tests/platform/test_package_layers.py`가 통과한다(공통 코드가 어린이 기능을 import하지 않는다)

## 4. 최근 기록과 인기

- [x] 4.1 `popular_ranking`(최근 180일 대출 행, 기관 시간대 오늘, 추천 가능·`within`, 서명 정렬 순서). 테스트: 대출 수 순서, 다른 기관의 대출
- [x] 4.2 `HistorySettings`와 `find_from_history`(`mean`, `per-book` RRF, 기록 책·판본 빼기, 다른 기관의 기록 책은 근거에서 뺌, 인기로 채우기). 테스트: 책별 순위 합치기, 다른 기관의 기록 책, 기록 결과가 모자람
- [x] 4.3 `app/library/README.md`의 추천 패키지 설명을 고친다

## 5. 실험 틀 넓히기

- [x] 5.1 `__main__.py`: 항목 루프·요약 쓰기를 세트 공통으로 나누고 `similar`, `history` 명령을 더한다(어린이 항목의 `within`과 위반 검사, 실험 기관 찾기, 지문). `topic` 요약이 나누기 전과 같은지 `runs/`로 확인한다. 테스트(`tests/evals/`): 비슷한 책 실행, 어린이 기준 책, 다른 세트의 변형, 기존 topic 테스트 그대로
- [x] 5.2 `variants.py`: 세트별 변형 표(design 결정 6·7의 이름). 묶음(관련 책 있음·없음, 같은 분야·섞인 분야·어린이)과 신호 건수를 요약에 적는다. 테스트: 비슷한 책 묶음, 빈 신호
- [x] 5.3 `label.py`의 `related_candidates`에 판본 빼기와 어린이 조건을 더한다. 테스트: 기준 책의 다른 판본, 어린이 기준 책의 후보. 바뀐 후보 수를 센다 (2026-11-16: 바꾸기 전 세트에서 비슷한 책 821 → 817건, 최근 기록 599 → 597건)
- [x] 5.4 `draft.py`·`review.py`가 `similar`·`history`를 받는다(검수 화면 위쪽에 기준 책 카드). 테스트: 비슷한 책 초안, 최근 기록 검수 화면
- [x] 5.4a 고정 표본(`sample.py`: 등급별 고르게, 항목 id·책 키의 SHA-256 순서), `review --sample`, 요약의 표본 수·등급별 일치율·보지 않은 표본 수. 테스트: 같은 표본, 등급별로 고르게, 일치율
- [x] 5.5 `evals/recommendation/README.md`(명령, 세트, 결과 자리)를 고치고 적힌 명령의 `--help`가 맞는지 확인한다

## 6. 세트와 라벨 (Claude가 단다, 사용자는 표본만)

- [x] 6.1 `data/seeds.json`을 백업하고, Claude가 s03(학습지)과 s10(s12와 같은 지은이)을 design "기준 책·최근 기록 다듬기"의 규칙으로 바꾼다. 세트 검사를 다시 돌리고 후보 수를 다시 센다. 바꾼 내역을 한 줄씩 사용자에게 보여 준다(훑어보기만) (2026-11-16: s03 → `바다 100층짜리 집`, s10 → `이상한 과학책`. 원본은 `/home/pollux/chaekbang-backups/labels-20261116-1117/seeds.json`. 후보 비슷한 책 807건, 최근 기록 597건)
- [x] 6.2 라벨 파일을 백업하고 경로를 알린다. Claude가 비슷한 책·최근 기록의 실행 전 라벨을 단다(외부 LLM 호출 없음, 단 쪽 `claude`). 끝날 때까지 비슷한 책·최근 기록 변형을 돌리지 않는다. 등급별 수를 알린다 (2026-11-16: 비슷한 책 807건(2: 116, 1: 302, 0: 389), 최근 기록 597건(2: 84, 1: 236, 0: 277). 두 라벨 파일은 이때 처음 생겼다. 단 뒤 백업 `/home/pollux/chaekbang-backups/labels-20261116-1150-before-run/`, 등급을 적은 스크립트 `data/draft/make_related_draft.py`)

## 7. 실행

- [x] 7.1 비슷한 책 단계 0~2(기준, 텍스트 종류, 분야 좁히기, 규칙만)를 조정 세트로 실행하고 승자를 `variants.py`에 적는다 (2026-11-16: 승자 `full`. 채택 규칙을 넘은 종류 없음. 분야 좁히기·규칙만은 낮음)
- [x] 7.2 비슷한 책 단계 3·4(합치기, 묶기·다양화)를 실행하고 승자를 정한다. `sim-best-kdc0`이 `sim-best`와 같은지 본다 (2026-11-16: 채택 규칙을 넘은 변형 없음. RRF 1:1은 `sim-vec`와 차이 없음(0·13·1), 시리즈 묶기·MMR 끔. `sim-best-kdc0`은 `sim-best`와 같다. 기본값은 사용자 결정으로 RRF 1:1 그대로, design "결과")
- [x] 7.3 최근 기록 단계 0~2를 실행하고 승자를 정한다 (2026-11-16: 승자 벡터 평균 `hist-mean`. 책별 RRF k 60은 0·0·7로 짐. 진단 변형 `hist-per-book-k1`을 결과를 본 뒤 더함. 시리즈 묶기·MMR 끔)
- [x] 7.4 보충: 보고할 변형들의 상위 10권에서 라벨 없는 책을 모아 Claude가 단다(건수를 알린다). 상위 5권 라벨 없음 0 (2026-11-16: 비슷한 책 161건(1 이상 59), 최근 기록 60 + 9건(1 이상 28). 상위 10권까지 라벨 없음 0)
- [x] 7.4a (2026-11-16: 45건 모두 확인, 고친 것 0건) 사용자가 고정 표본 45건(비슷한 책 25, 최근 기록 20)을 `review similar --sample`, `review history --sample`에서 본다(약 15분). 30% 이상(14건 이상)을 고치면 결과를 쓰지 않고 멈춰 알린다(기준을 맞춰 그 세트를 다시 달고 다시 돌린다)
- [x] 7.5 최종 실행을 두 번 해(조정·확인, 세 세트) 요약이 시각·걸린 시간 줄을 빼고 같은지 확인한다 (2026-11-16: 비슷한 책 `20261116-153424`=`153444`, 최근 기록 `20261116-153438`=`153457`. topic은 1.4의 `112024`와 틀을 나눈 뒤의 `113219`가 같다)

## 8. 결정 기록과 문서

- [x] 8.1 design "결과"에 비슷한 책·최근 기록의 단계별 표(조정·확인, 묶음별), 신호 건수(KDC·인기 0건), 라벨 단 쪽과 표본 일치율, 채택 설정과 근거, 책→책 텍스트 종류 결론, 판본 묶음, 지문, 걸린 시간을 쓴다. 기본 종류가 `full`이 아니면 스펙 delta를 먼저 고치고 알린다 (표본 일치율 100%, 45건 중 고친 것 0건)
- [x] 8.2 `SimilarSettings`·`HistorySettings` 기본값을 채택한 설정으로 둔다. 테스트가 그대로 통과한다 (2026-11-16: `HistorySettings.method` 기본값을 `mean`으로. `SimilarSettings`는 그대로)
- [x] 8.3 `CLAUDE.md`(현재 단계, 결과, 명령, 디렉터리 구조), `docs/design.md`(추천 품질 평가, 주차 표)를 고친다

## 9. 마무리 확인

- [x] 9.1 스펙 시나리오마다 테스트 docstring에 "요구사항 / 시나리오"가 있는지 점검한다 (2026-11-16: delta의 시나리오 모두 있음)
- [x] 9.2 `uv run pytest`와 `uv run ruff check . && uv run ruff format --check .`가 통과한다. 테스트 DB에 대량 삽입·롤백을 했으면 `VACUUM ANALYZE` 뒤 돌린다. 0.3과 통과 수를 비교하고 `evals.catalog_search` 결과가 0.4와 같은지 확인한다 (2026-11-16: 1253 통과, 7 건너뜀. 기준 1216에서 37개 늘었다. 첫 전체 실행에서 7개가 실패했다: 공식 서지를 만드는 테스트가 늘어 `tests/helpers.py`의 `make_isbn`이 1000번을 넘으면 14자리 ISBN을 냈다. 도우미를 고쳤다(1000 미만의 값은 그대로). ruff 통과. catalog_search는 `runs/20261116-153856`이 0.4와 같다)
- [x] 9.3 `openspec validate add-related-book-experiments --strict`가 통과한다

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다.
- 다음 change `add-bibliographic-sources`(카카오·정보나루, 실제 KDC, 함께 대출된 책, 정보나루 인기, 빈 기록, 실험 장서 지우기).
