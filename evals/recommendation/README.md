# 추천 실험

추천 방식의 변형을 같은 평가 세트와 사람이 단 어울림 라벨로 나란히 잰다. LLM과 외부 API를 부르지 않아 비용이 없다. 서비스 경로가 아니다.

```bash
uv run python -m evals.recommendation.pick                 # 기준 책 20권·최근 기록 10개 고르기 (한 번)
uv run python -m evals.recommendation.draft dump topic     # 실행 전 후보를 data/draft/에 쓴다(초안을 달 때 읽는다)
uv run python -m evals.recommendation.draft apply topic <초안.json>   # 초안(Claude)을 라벨 파일에 넣는다
uv run python -m evals.recommendation.draft dump topic --pool <실행 폴더>   # 보충: 상위 10권 중 라벨 없는 책 (apply도 --pool)
uv run python -m evals.recommendation.review topic         # 검수 화면 http://127.0.0.1:8765 (사람이 확인·고침)
uv run python -m evals.recommendation.label topic          # 터미널에서 직접 달기, 목록 방식 (similar, history도. --cards는 한 권씩)
uv run python -m evals.recommendation topic --variants current,vec-text,hybrid   # 조정 세트로 실행
uv run python -m evals.recommendation topic --split all --variants current,best
uv run python -m evals.recommendation.label topic --pool <실행 폴더 이름> --variants current,best   # 보충 라벨
uv run python -m evals.recommendation similar --split all --variants sim-vec,sim-rrf,sim-best     # 비슷한 책 (임베딩 서버 필요 없음)
uv run python -m evals.recommendation history --split all --variants hist-mean,hist-per-book     # 최근 기록
uv run python -m evals.recommendation.draft dump similar   # 후보: data/draft/similar-items.txt, similar-books.txt (history도, apply·--pool도 같다)
uv run python -m evals.recommendation.review similar --sample   # 고정 표본 검수 (history도)
uv run python -m evals.recommendation.review topic --sample --since <백업 라벨 파일>   # 그 백업 뒤에 단 보충 라벨에서만 표본
uv run python -m evals.recommendation compare <기준 실행 폴더> <새 실행 폴더>   # 같은 세트의 두 실행을 지금 라벨로 짝 비교
uv run python -m evals.recommendation similar --split all --variants sim-rrf,sim-best-co   # 함께 대출 변형: 대출 신호 파일을 읽는다(--loan-signals <파일>)
uv run python -m evals.recommendation.pick --holdout       # 남겨 둔 분야 기준 책 8권·최근 기록 4개 (한 번)
uv run python -m evals.recommendation similar --holdout --variants sim-vec,sim-rrf,sim-best   # 남겨 둔 분야 세트 (정해 둔 변형만)
uv run python -m evals.recommendation.review similar --sample --since <백업> --size 12   # 표본 수를 바꿔 보충 표본
```

- 개발 DB(`DATABASE_URL`)의 `실험용 가상 작은도서관`(이름으로 찾는다)에서 읽기만 한다. 실험 장서는 `scripts/seed_experiment.py`가 넣는다.
- 재는 코드는 제품 패키지의 것이다(`app/library/recommendation/topic.py`, `related.py`, `ranking.py`, `embeddings.py`). 기관 범위, 추천 가능, 어린이 조건이 그 함수에서 강제된다. 여기에는 변형 정의, 세트, 라벨, 지표만 있다.
- 질의 인코딩만 로컬 임베딩 서버를 쓴다(`docker compose --profile embedding up -d embedder`). 질의 벡터를 `data/query_vectors.json`에 캐시해, 한 번 돌린 질의는 서버 없이 돈다. 비슷한 책(`similar`)과 최근 기록(`history`)은 기준 책의 저장된 벡터만 써서 서버가 필요 없다.
- 세트는 셋이다: `topic`(주제 질의), `similar`(기준 책 하나), `history`(최근 기록 책 목록). 변형 표는 세트마다 따로이고(`variants.py`) 다른 세트의 변형 이름은 오류다. 어린이 기준 책(기록이면 책이 모두 어린이 도서)에는 어린이 도서 조건을 건다.
- 장서는 YES24 카테고리 스테디셀러로 고른 525권이고 기관과 사본 상태는 가상이다. 2026-11-17부터 공식 서지는 세 출처(정보나루·카카오·YES24)를 합친 값이다(`scripts/seed_experiment.py`, `--sources`로 출처를 고를 수 있다). 수치를 실제 서비스 성능으로 쓰지 않는다.
- **실행 사이 비교**(`compare`): 장서 값을 바꾸기 전과 뒤처럼 같은 세트를 다른 장서 상태에서 돌린 두 실행을, 두 실행의 상위 10권 책 키를 지금 라벨로 다시 채점해 짝 비교한다. 세트 해시가 다르면 멈춘다. 요약은 `<새 실행>-vs-<기준 실행>/summary.md`에 쓴다. DB·인코딩이 없다. 실행 요약의 지문에는 공식 서지 출처별 수가 있다.

## 파일

| 위치 | 내용 | 저장소 |
| --- | --- | --- |
| `sets/topic.json` | 주제 질의 30개. 이용자 문장, 사서가 넘길 낱말, 어린이 요청 여부, 결(`topic` 주제어 / `mood` 상황·기분), 관련 분야, 구분(`tune` 조정 / `check` 확인) | 넣는다(사람이 쓴 문장) |
| `data/seeds.json` | 비슷한 책의 기준 책, 아무 조건 없음의 최근 기록(책 키) | 뺀다 |
| `data/labels/<세트>.json` | 어울림 라벨. `{"t01": {"isbn:978…": {"grade": 2, "stage": "before", "by": "user"}}}` | 뺀다 |
| `data/query_vectors.json` | 질의 벡터 캐시 | 뺀다 |
| `sets/topic-holdout.json` | 남겨 둔 분야 주제 질의 8개(모두 `check`) | 넣는다 |
| `data/seeds-holdout.json` | 남겨 둔 분야 기준 책 8권·최근 기록 4개 | 뺀다 |
| `data/labels/holdout-<세트>.json` | 남겨 둔 분야 라벨(기존 라벨 해시가 흔들리지 않게 따로) | 뺀다 |
| `evals/collection/data/loan_signals.json` | 정보나루 대출 신호(ISBN 순위·수만). 함께 대출·인기를 쓰는 변형만 읽고, 없으면 받기 명령을 출력하고 종료 코드 1. 받지 않은 ISBN은 빈 신호로 보고 요약에 수를 적는다 | 뺀다 |
| `data/runs/<시각>/` | `summary.md`(표), `results.json`(질의·변형별 상위 10권) | 뺀다 |

- `data/`는 책 키가 실험 장서를 가리켜 저장소에 넣지 않는다. **라벨은 다시 만들 수 없으니 `data/labels/`를 따로 백업한다.**
- 책 키는 `isbn:<13자리>`, ISBN이 없으면 `acc:<가장 앞선 등록번호>`다. DB의 id는 장서를 다시 넣으면 바뀌어서 쓰지 않는다.
- 저장소의 질의 파일에 ISBN이나 등록번호 모양의 값이 있으면 세트 검사가 실패한다.
- 남겨 둔 분야(종교·예술·건강 취미·여행)는 질의의 관련 분야, 기준 책, 최근 기록에 쓸 수 없다(세트 검사가 거부). 그 책들은 후보로는 남는다.
- **남겨 둔 분야 세트**(`--holdout`, `add-loan-signals`)는 반대로 남겨 둔 분야를 반드시 담고, 모든 항목이 확인 세트다. 기본값을 모두 정한 뒤 정해 둔 변형만 한 번 돌려 방향(같음·반대·차이 없음)만 읽는다. 이 결과로 설정을 바꾸지 않는다.

## 라벨

- **초안은 Claude, 검수는 사람**이다(2026-11-16). 실행 전 후보가 주제만 1,384건이라 사람이 다 달지 못했다. Claude가 대화에서 후보의 서명·분류·소개를 읽고 초안을 달고(외부 LLM API 호출 없음, 변형을 돌리기 전), 사람이 검수 화면에서 1 이상인 책을 소개 전문과 함께 확인하거나 고치고 0인 책 목록에서 빠진 책을 올린다.
- 라벨마다 단 쪽 `by`(`claude` 초안 / `user` 사람이 확인·고침)를 적고 요약에 수를 적는다. 0은 대부분 초안 그대로라 정답이 LLM 판단에 기댄다. 수치를 읽을 때 이 점을 함께 적는다.
- 검수 화면은 `127.0.0.1`에서만 열리고 누를 때마다 라벨 파일에 쓴다. 노란 띠는 초안, 초록 띠는 확인한 책이다.
- 주제: **2** 이 요청에 받으면 바로 납득(주제와 대상이 모두 맞음), **1** 관련은 있으나 일부만 맞음, **0** 맞지 않음.
- 비슷한 책·최근 기록: **2** 이 책(들)을 좋게 읽은 사람에게 권하면 납득, **1** 같은 갈래지만 결이 다름, **0** 아님.
- **실행 전**(`before`): 어떤 변형도 돌리기 전에 단다. 후보는 질의의 관련 분야에 든 추천 가능한 책(어린이 요청은 어린이 도서만), 기준 책의 분야와 같은 지은이·같은 시리즈의 책이다. 결과를 보고 달면 그 방식 쪽으로 기운다.
- **실행 뒤 보충**(`pool`): 보고할 변형들의 상위 10권 중 라벨이 없는 책만 단다. 다른 분야에 있던 어울리는 책을 잡는다. 보고한 변형에 조금 유리한 치우침이 있어 단계별 수를 요약에 적는다.
- **목록 방식**(실행 전 기본): 질의 하나의 후보를 번호 목록 한 화면으로 본다. `2인 번호`와 `1인 번호`를 공백이나 쉼표로 넣고(없으면 Enter) 확인하면 나머지는 0으로 한 번에 쓴다. `?12`는 12번 책의 카드(소개 300자), `r`은 다시, `q`는 끝내기(그 질의는 쓰지 않는다). 한 권씩 물으면 주제만 1,384건이라 이렇게 단다.
- **카드 방식**(보충 단계, 또는 `--cards`): 한 권씩 묻고 답마다 쓴다. Enter는 0, `q`는 끝내기.
- 다시 열면 라벨 없는 책부터 이어 간다.
- 비슷한 책·최근 기록의 후보는 기준 책들의 분야 + 같은 지은이·같은 시리즈의 책이다. 기준 책과 그 다른 판본은 빼고, 어린이 기준 책이면 어린이 도서만이다. 검수 화면은 기준 책의 소개 전문을 후보 위에 보여 준다.
- **비슷한 책·최근 기록의 라벨은 Claude가 달고 사람은 고정 표본만 본다**(2026-11-16, `add-related-book-experiments`). 실행 전 1,400여 건에 보충까지 사람이 다 보기에는 많다. 표본은 등급(2·1·0)마다 고르게, 항목 id와 책 키의 SHA-256 순서로 뽑는다(비슷한 책 25건, 최근 기록 20건). 결과를 보지 않고 정해져 언제 봐도 특정 변형 쪽으로 기울지 않는다. `review <세트> --sample`에서 지금 등급이 맞으면 그 숫자를, 틀리면 맞는 숫자를 누른다. 요약에 일치율(사람이 고치지 않은 비율)과 보지 않은 표본 수를 적는다. 표본의 30% 이상을 고치면 결과를 쓰지 않고 기준을 다시 맞춘다. 사람이 고친 라벨에는 초안 등급이 `draft`로 남는다.

## 지표와 읽는 법

| 지표 | 정의 |
| --- | --- |
| nDCG@5 (주 지표) | 라벨의 이득 `2^라벨 − 1`, 이상적 순위는 그 질의의 라벨 전체로. AI 사서가 최대 5권을 낸다 |
| Hit@5 | 라벨 2인 책이 상위 5권에 하나라도 있다 |
| Recall@10 | 라벨 1 이상인 책 중 상위 10권에 든 비율. 분모는 그 수와 10 중 작은 값 |
| 겹침 | 상위 5권에서 지은이가 같은 쌍 + 시리즈가 같은 쌍 |
| 라벨 없음 | 상위 5권 중 라벨 없는 책 수(0으로 센다). 보충 라벨 뒤 0이어야 결과를 읽는다 |
| 위반 | 추천할 수 없는 책, 어린이 요청의 일반 도서. 하나라도 있으면 종료 코드 1 |

- 질의가 적어(조정 20, 확인 10) 평균만 보지 않는다. 기준 변형과 질의별 nDCG@5 차이로 이김·비김·짐을 세고, 고정 시드 부트스트랩(2,000번)으로 평균 차이의 95% 구간을 낸다.
- **채택 규칙**: 조정 세트에서 평균 차이 > 0, 이김 > 짐, 구간 하한 > 0이면 채택한다. 아니면 "차이 없음"으로 보고 더 단순한 쪽을 둔다. 확인 세트는 마지막에 한 번, 뒤집히지 않는지만 본다.
- 비슷한 책·최근 기록의 요약에는 묶음별 표(어린이·일반, 관련 책 있음·없음 / 같은 분야·섞인 분야·어린이)와 **신호 건수**(신호마다 결과가 비지 않은 항목 수와 평균 권수)가 있다. 실험 장서에 값이 없는 신호(같은 KDC 세목, 우리 도서관 인기)는 0건으로 나온다. 겹침(같은 지은이·시리즈 쌍)은 비슷한 책에서는 나쁜 값이 아니라 채택 근거로 쓰지 않는다.
- 변형은 `variants.py`에 있다. 단계(기준 → 벡터 입력 → 텍스트 종류 → 합치기 → 시리즈 묶기 → 다양화)마다 앞 단계의 승자 위에 얹고, 승자는 `BEST_*`에 적는다.

## 결과

표와 근거는 change의 design "결과"에 있다(`openspec/changes/…/add-recommendation-experiments/design.md`, `add-related-book-experiments/design.md`).

- **주제로 찾기**: 키워드 순위 + 벡터 순위 RRF(k 60, 1:1, `hybrid-k60`)가 지금 키워드 검색을 이겼다. 서명 가나다순 뒤 기준은 조정 0.453 → 0.519, 확인 0.384 → 0.522(`data/runs/20261116-112024`).
- **비슷한 책**: 벡터 이웃(`sim-vec`, `full`)을 채택 규칙으로 넘은 변형이 없다. 규칙 신호(같은 시리즈·같은 저자) RRF는 품질이 같다. 텍스트 종류는 책→책에서도 `full`이다(`data/runs/20261116-153444`).
- **최근 기록**: 벡터 평균(`hist-mean`)이 책별 RRF(k 60)를 이겼다(`data/runs/20261116-153457`).
- 같은 KDC 세목과 우리 도서관 인기는 YES24 실험 장서에서 0건이었다.
- **세 출처로 다시 채운 뒤**(`add-bibliographic-sources`, 2026-11-17): A(세 출처)에서 `hybrid-k60`·`hist-mean`은 그대로이고, `sim-rrf`가 정보나루 KDC 덕에 같은 KDC 세목 신호가 14권에서 값을 가지면서 처음으로 채택 규칙을 넘었다(조정 +0.052). B(YES24 뺌)는 대체로 낮다(최근 기록 조정 -0.224). A 최종 실행 `data/runs/20261117-025721`·`025753`·`025756`.
