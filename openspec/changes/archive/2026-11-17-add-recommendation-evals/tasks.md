# Tasks

## 0. 시작 전

- [x] 0.1 기준을 잰다: `uv run pytest`, `uv run ruff check .`, `uv run python -m evals.catalog_search`. 통과 수와 표를 design "결과"에 적는다

## 1. 검사 판정 (`related-anything`)

- [x] 1.1 `evals/librarian/checks.py`의 `related_met`: 기대가 `EMPTY`이고 그 턴에 검색 tool도 불렀으면 추천이 관련 책 결과 안인지 묻지 않는다. 테스트: 아무거나 뒤 검색은 맞음, 비슷한 책(`BOOK`)은 그대로 엄격. docstring에 `[agent/librarian] 관련 책 요청에 답함 / 아무거나 뒤 검색`
- [x] 1.2 `add-topic-search-tool`의 네 실행 JSON을 새 검사로 다시 채점한다(LLM 없음). `related-anything`이 맞음으로 바뀌고 다른 시나리오의 판정은 그대로인지 확인해 결과에 적는다

## 2. 실험 장서 적재와 대화 바꾸기

- [x] 2.1 `evals/conversation/` 패키지: 테스트 DB 되돌리는 세션에서 실험 장서 적재(`seed_experiment`, 평가용 시드 비밀번호), 두 층 벡터 적재와 문서 벡터 캐시(`data/doc_vectors.json`). 검사가 쓰는 장서 정보(추천 가능, 어린이, 서지 글, 책 키 ↔ id)를 만든다. `.gitignore`에 `evals/conversation/data/`. 테스트: 작은 가짜 장서 파일로 키 일치, 되돌린 뒤 기관 없음, 캐시 적중이면 인코더를 부르지 않음
- [x] 2.2 세트 항목을 대화로: 주제 한 턴, 비슷한 책은 고른 턴 → 정해 둔 문장, 최근 기록은 고른 턴들 → `아무거나 추천해 줘`. 어린이 항목은 어린이 문장. `run_scenario`가 고를 책 목록을 받게 넓힌다(기존 시나리오 동작은 그대로). 테스트: 세 세트의 턴 모양, 어린이 문장이 `is_children_request`에서 어린이, 마지막 턴 전 `session_books`가 기록과 같음
- [x] 2.3 tool handler 감싸기: 검색 낱말, 관련 책 id, 결과 책 id를 메모리에 받아 결과 파일에만 쓴다. 테스트: 한 턴 두 번 호출의 순서, 실행 단계에 낱말 없음, 관련 책 결과가 `runner._related`로 다시 구한 것과 같음

## 3. 채점, 요약, 비교

- [x] 3.1 카드와 tool 결과 앞 5권의 Hit@5·Recall@5·nDCG@5, 카드 없음, 라벨 없는 카드(`evals/recommendation/metrics.py` 재사용). 테스트: 스펙의 계산 예, 카드 없음, tool 결과 채점
- [x] 3.2 요약 `summary.md`: 머리(모델, 프로필 버전, 세트 해시, 라벨 수), 전체·묶음별 표, 규칙 위반, 턴·호출·토큰·비용(`LLM_PRICES`), 키워드 순위 빈 검색·`note` 수, 보충 전 표시. 항목별 JSON과 `results.json`(보충 도구 형식). 규칙 위반이면 종료 코드 1. 테스트: 묶음 나누기, 보충 전 표시, 비용, 위반으로 실패
- [x] 3.3 `evals/recommendation/draft.py`의 `--pool`이 대화 실행 폴더를 읽는다. 테스트: 후보가 카드와 tool 앞 5권 중 라벨 없는 책뿐
- [x] 3.4 `uv run python -m evals.conversation.compare <실행>...`: 지금 라벨로 다시 채점, 이김·비김·짐과 95% 구간, 묶음별 평균, 세트 해시가 다르면 종료 코드 1. 테스트 둘
- [x] 3.5 가짜 LLM으로 세트마다 한 항목씩 끝까지 도는 테스트. 테스트 DB `VACUUM ANALYZE` 뒤 `uv run pytest`와 `ruff`가 통과한다

## 4. 실제 LLM 낱말 실행 코드

- [x] 4.1 `evals.recommendation topic --keywords-from <대화 실행>`: 마지막 턴의 첫 검색 낱말로 바꾸고, 검색 없는 항목은 빼고 수를 적는다. 테스트: 스펙 두 시나리오(가짜 인코더). docstring에 `[platform/recommendation-experiments] 실제 LLM 낱말로 주제 실행 / …`

## 5. 실행 (승인 뒤)

- [x] 5.1 문서 벡터 캐시: 임베딩 서버를 띄우고 525권 문서를 인코딩한다(백그라운드, 약 12분). 걸린 시간과 캐시 수를 적고 서버를 내린다
- [x] 5.2 LLM 승인을 받는다: 두 실행, 항목 60개, LLM 턴 60개/실행, 호출 약 126회/실행, 입력 약 40만·출력 약 8.4천 토큰/실행, 두 실행 약 $0.09(캐시 없이), 상한 $0.15
- [x] 5.3 첫 실행(임베딩 서버 켬): `uv run python -m evals.conversation`. 끝나면 서버를 내리고 토큰·비용을 적는다
- [x] 5.4 라벨 보충: 라벨 셋을 `/home/pollux/chaekbang-backups/labels-<시각>-before-chat/`에 백업하고 경로를 알린다. Claude 초안(`draft dump/apply --pool`), 사용자 표본 검수(`review <세트> --sample --since <백업>`). 일치율을 적고 30% 이상 고치면 멈춘다
- [x] 5.5 둘째 실행. 라벨 없는 카드가 있으면 5.4를 한 번 더 한다. `compare`로 두 실행을 지금 라벨에서 나란히 내고 표를 design "결과"에 적는다(묶음별 카드·tool 앞 5권, 실제 사용량과 추정 비교)
- [x] 5.6 실제 LLM 낱말 실행: 임베딩 서버를 켜고 `topic --keywords-from <첫 실행> --split all --variants hybrid-k60,hybrid-best`, 끝나면 서버를 내린다. 상위 5권 보충과 표본 검수는 5.4와 같은 순서다. 결정 5의 미리 정한 읽기로 판정해 적는다(나쁨이면 멈추고 알린다)
- [x] 5.7 테스트 DB `VACUUM ANALYZE`

## 6. 문서와 마지막 점검

- [x] 6.1 `evals/conversation/README.md`와 `CLAUDE.md`(`@README.md`), `evals/recommendation/README.md`(`--keywords-from`, 대화 실행 보충), `CLAUDE.md` 자주 쓰는 명령 한 줄, `docs/reports/search-recommendation-strategy.md` 4·5.2·9절. 적은 명령이 실행되는지 확인한다
- [x] 6.2 이 change의 스펙 delta 시나리오가 모두 테스트 docstring에 연결돼 있는지 스크립트로 점검한다. `uv run pytest`, `ruff check`, `ruff format --check`가 통과한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 archive한다. archive 전에 `docs/roadmap.md`를 고친다. 19번 상태는 끝남이다. 확정된 기본값 근거에는 실제 LLM 낱말 결과를 넣는다. 미룬 일에는 "MVP 뒤"로 어린이 지표 둘·섞인 기록, 모델 비교, 사람 라벨 일치도, 없는 주제 세트와 빈 결과 규칙, 노출 기록 출처 칸, 87권 세 출처를 적는다.
- 다음 change는 `add-admin-agent`다.
