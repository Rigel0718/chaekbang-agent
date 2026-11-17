순서: 기준 실행(4)은 AI 사서 행동을 바꾸는 5·6보다 먼저 한다. 1~3은 AI 사서 행동을 바꾸지 않는다.

## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`, `uv run python -m evals.catalog_search`, similar·history 기준 실행(`evals.recommendation similar --split all --variants sim-vec,sim-rrf`, `history`의 `hist-mean`)을 돌려 run 이름과 수치를 design "결과"에 적는다(확인: 직전 실행 `20261117-162249`·`162253`·`162209`와 `results.json`·표가 같음)

## 1. 벡터 질의 입력 확인 실험 (design 결정 2, LLM 없음, 개발 DB 읽기만)

- [x] 1.1 `evals/recommendation/variants.py`: `hybrid-k60` 등 합친 순위 변형에 `vector_input="text"`를 직접 적고, `hybrid-vkw`(낱말 입력)와 `hybrid-best`(= `TopicSettings()`)를 더한다(확인: 스펙 recommendation-experiments "합친 순위의 벡터 질의 입력 변형" 시나리오 셋의 테스트, `hybrid-k60` 결과가 직전 실행과 같음)
- [x] 1.2 `evals/recommendation/data/query_vectors.json`에 `hybrid-vkw`의 질의 벡터가 모두 있는지 센다. 없는 질의가 있을 때만 임베딩 서버를 띄워(백그라운드) 인코딩하고 내린다(확인: 새로 인코딩한 질의 수를 결과에 적음)
- [x] 1.3 라벨을 `/home/pollux/chaekbang-backups/labels-<시각>-before-topic-input/`에 백업하고 경로를 알린다 → `topic --split all --variants current,hybrid-k60,hybrid-vkw,hybrid-best` 실행 → 상위 5권 중 라벨 없는 책만 Claude가 보충 → 표본 검수(`review --sample --since <백업 라벨 파일>`, 고친 비율이 30% 이상이면 멈춤) → 같은 명령으로 최종 두 번(확인: 두 실행의 `results.json`이 같음, 표본 일치율, 보충 건수, 규칙 위반 0)
- [x] 1.4 결정 2의 규칙으로 판정한다. 낱말이면 `TopicSettings.vector_input` 기본값을 `"keywords"`로 바꾸고 `hybrid-best`가 `hybrid-vkw`와 같은지 본다. 문장이면 스펙 delta(제품 경로의 주제로 찾기, 질의 인코더 실행 값)를 이번 턴 가린 문장(`USER_TEXT` 실행 값)으로 고치고 tasks 5에 그 일을 더한 뒤 알린다(확인: 판정 표와 근거를 design "결과"에 적음, 기본값을 바꾸면 기존 주제로 찾기 테스트가 통과)
- [x] 1.5 `evals/recommendation/threshold.py` 옆에 키워드 순위가 빈 질의 진단(`keyword-empty.md`)을 만들고 1.3의 최종 실행으로 쓴다(확인: 스펙 "키워드 순위가 빈 질의 진단" 시나리오 둘의 테스트, 표를 design "결과"에 옮김)
- [x] 1.6 `evals/recommendation/README.md`에 새 변형과 진단 명령을 적는다(확인: 적힌 명령이 그대로 돈다)

## 2. 질의 인코더 (design 결정 6, AI 사서 행동은 그대로)

- [x] 2.1 `EmbeddingFailure`에 `TIMEOUT`, `PAUSED`를 더하고 `TeiEmbedder`의 시간 초과를 `TIMEOUT`으로 바꾼다(확인: tei 어댑터 테스트, 적재 CLI 출력 테스트에서 종류 이름만 바뀜)
- [x] 2.2 `app/central/embedding.py`에 `GuardedEmbedder`(질의 시간 제한, 실패 뒤 쉬기, 처음 한 번 모델 확인, 문서 인코딩 막음)를 만들고 설정 `embedding_query_timeout_seconds`(2.0), `embedding_query_pause_seconds`(30), `embedding_query_enabled`(True)를 `app/core/config.py`와 `.env.example`에 더한다(확인: 스펙 topic-recommendation "질의 인코딩 쉬기" 시나리오 셋, "키워드 순위로 내려가기"의 시간 제한·다른 모델 시나리오의 인코더 쪽 테스트, 오류 메시지에 질의 없음)
- [x] 2.3 `app/library/api/librarian.py`에 `get_query_encoder`(`app.state`에 처음 쓸 때 만듦, 꺼진 설정이면 `None`)를 두고 `app/main.py` lifespan 끝에 클라이언트를 닫는다. 아직 대화에 넘기지 않는다(확인: 의존성 테스트, 앱 시작·종료 테스트)
- [x] 2.4 `app/central/README.md`에 `GuardedEmbedder`와 질의 설정을 적는다(확인: 설정 이름이 코드와 같음)

## 3. 평가 표본 벡터와 주제 시나리오 (design 결정 9·10·11, LLM 없음)

- [x] 3.1 `CachedEmbedder`를 문서에도 쓰게 넓히고(질의와 키 구분), `load_catalog`에 인코더를 받아 두 층 적재를 같은 트랜잭션에서 부른다. `evals.librarian`에 `--no-vectors`와 시작 출력(벡터 적재 권수, 캐시 적중 수, 인코더 상태)을 더한다(확인: 가짜 인코더로 표본 적재 테스트, 캐시가 차 있으면 인코더를 부르지 않는 테스트, 데이터 파일이 `.gitignore` 안)
- [x] 3.2 임베딩 서버를 띄워(백그라운드) 표본 87권의 문서 벡터 캐시를 만들고 내린다(확인: 두 번째 적재가 서버 없이 캐시만으로 같은 권수, 걸린 시간을 결과에 적음)
- [x] 3.3 주제 시나리오 다섯(`situation-commute`, `follow-up-lighter`, `topic-retry`, `not-held-near`, `child-topic-vector`)과 기대 종류 `NO_MATCH_OR_ON_TOPIC`을 더한다. 낱말과 주제는 표본을 보고 정한다(확인: `test_scenarios_cover_eval_requirements`가 "주제 요청에 답함"의 시나리오 셋을 찾음, 새 기대 종류 채점 테스트)
- [x] 3.4 `evals/librarian/compare.py`(실행 여러 개를 시나리오별로 나란히: 기대 일치, 규칙 위반, 어린이 판단, 주제 낱말 일치, 검색 호출 수, 턴 걸린 시간, 토큰)를 만든다(확인: 저장된 실행 둘로 비교 테스트, LLM을 부르지 않음)
- [x] 3.5 평가 문서(`evals/librarian` 설명 또는 `evals/recommendation/README.md`의 AI 사서 평가 절)에 벡터 적재, 캐시, `--no-vectors`, 비교 명령을 적는다(확인: 적힌 명령이 그대로 돈다)

## 4. 기준 실행 (실제 LLM, 승인 뒤, 5·6보다 먼저)

- [x] 4.1 시나리오 수, 턴 수, 예상 호출 수·토큰·비용(design 결정 11, 기준 둘 + 바꾼 뒤 둘)을 다시 세어 알리고 승인을 받는다. 승인이 없으면 4.2와 7을 하지 않고 가짜 LLM으로 시나리오 틀만 확인한다(확인: 승인 기록을 design "결과"에 적음)
- [x] 4.2 지금 코드(v5)로 임베딩 서버를 켜고 `uv run python -m evals.librarian` 두 번. 도는 동안 pytest를 돌리지 않는다. 끝나면 임베딩 서버를 내린다(확인: 두 run 이름, 토큰, 규칙 위반, 기대 불일치, 관련 책 시나리오 4개의 tool 결과가 비지 않았는지를 결과에 적음)

## 5. 제품 service와 tool (design 결정 3·4·5·7)

- [x] 5.1 `app/library/services/topic.py`의 `search_by_topic`(낱말 없음 → 둘러보기, 인코더 없음·실패 → 키워드만, 기본 설정 + 결과 10권, 키워드 근거 판정, 로그는 실패 종류만, 쉬는 동안은 debug)을 만든다(확인: 스펙 topic-recommendation "제품 경로의 주제로 찾기" 셋, "키워드 순위로 내려가기" 넷, "키워드 근거 없음 표시" 셋, "제품 경로의 범위" 둘의 테스트, 기관 분리 테스트)
- [x] 5.2 `app/library/tools.py`: `search_tool`이 `search_by_topic`을 부르고 결과를 `{books, note}`로 낸다. 인코더는 실행 값 `QUERY_ENCODER`로 받는다(확인: 스펙 librarian "소장 도서 검색 결과" 다섯, "조회 tool"의 새 시나리오 둘의 테스트, 기존 조회 tool 테스트를 새 모양으로 고침)
- [x] 5.3 `services/chat.py`의 `stream_turn`이 인코더를 받아 `tool_values`에 넘기고, 라우터가 `get_query_encoder`를, 평가 진입점이 평가 인코더를 넘긴다(확인: 스펙 librarian "질의 인코더 실행 값" 둘의 테스트, 기존 대화 테스트 통과)
- [x] 5.4 `BASE_PROMPT`의 검색 줄을 고친다: 주제·분위기·상황은 `search_collection`, 낱말은 요청의 주제·대상·분위기를 담은 1~5개, 이어지는 요청은 이전 주제를 함께 넣음, 결과의 `note`대로 함. 어린이 `PROMPT_NOTE`는 고치지 않는다. `PROFILE_VERSION`을 v6으로 올린다(확인: 프로필 테스트, 어린이 프롬프트 문구가 바뀌지 않았음을 diff로 확인)
- [x] 5.5 `app/library/README.md`(주제로 찾기 절, AI 사서 tool, 구성 표)를 고친다(확인: 주제로 찾기에 "아직 잇지 않았다" 문장이 남지 않음, 구성 표가 코드와 같음)

## 6. 어린이 기능

- [x] 6.1 `search_children_books`가 같은 factory로 주제로 찾기를 어린이 범위로 쓰는지 확인하고 테스트를 더한다(확인: 스펙 children "어린이 도서 검색 tool" 넷의 테스트, 어린이 요청 판단 테스트 통과)
- [x] 6.2 `app/features/README.md`의 어린이 도서 검색 tool 설명을 고친다(확인: 문서가 코드와 같음)

## 7. 바꾼 뒤 실행과 비교 (실제 LLM, 4.1 승인 범위 안)

- [x] 7.1 v6으로 임베딩 서버를 켜고 `uv run python -m evals.librarian` 두 번. 도는 동안 pytest를 돌리지 않는다(확인: 두 run 이름과 4.2와 같은 값)
- [x] 7.2 `compare`로 네 실행을 비교하고 결정 11의 판정을 적는다. 넘지 못하면 멈추고 알린다. 끝나면 임베딩 서버를 내린다(확인: 판정 표, 어린이 판단 따로, 실제 사용량이 추정을 넘었으면 그대로 적음)

## 8. 마지막 점검과 문서

- [x] 8.1 모든 스펙 delta 시나리오가 테스트(docstring에 `[capability] 요구사항 / 시나리오`) 또는 평가 시나리오(`traces`)에 있는지 표로 확인한다(확인: design "결과"의 시나리오 표)
- [x] 8.2 `uv run pytest`(테스트 DB `VACUUM ANALYZE` 뒤), `uv run ruff check . && uv run ruff format --check .`, `evals.catalog_search`와 similar·history 기준 실행이 0.1과 같음(확인: 수치를 결과에 적음)
- [x] 8.3 `CLAUDE.md`(현재 단계, 명령 한 줄), `docs/reports/search-recommendation-strategy.md`(1절, 5.2절, 9절)를 고친다(확인: 주제로 찾기의 "아직 아님"이 남지 않음)

## Workflow follow-up

- 사용자 확인 뒤 `/opsx:archive`. archive 전에 `docs/roadmap.md`(18번 상태, 확정된 기본값: 주제로 찾기 "제품에 이음"·벡터 질의 입력·시리즈 묶기 끔, 미룬 일)를 고친다.
- PR은 제목과 본문 텍스트만 준다.
