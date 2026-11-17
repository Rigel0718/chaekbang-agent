## Why

추천 실험(`add-recommendation-experiments`, `add-related-book-experiments`, `add-bibliographic-sources`)에서 주제로 찾기는 `hybrid-k60`(키워드 순위와 벡터 순위를 RRF k 60, 1:1로 합침, 텍스트 `full`, 시리즈 묶기·MMR 끔)으로 정했다. 세 출처 장서(A)에서 키워드 검색보다 조정 nDCG@5가 0.451 → 0.525(+0.074, 95% 구간 +0.030 ~ +0.115)로 높고, 남겨 둔 분야에서도 방향이 같다(+0.097). 특히 키워드가 거의 맞지 않는 상황 질의("퇴근 후 30분 읽을 에세이")를 벡터가 받친다(0.168 → 0.31).

그런데 AI 사서는 아직 키워드 검색(`search_collection`)만 쓴다. 비슷한 책과 최근 기록은 `add-related-books`로 제품에 나갔지만, 주제로 찾기는 두 가지 이유로 따로 나눴다. 요청마다 질의를 인코딩하므로 서비스 중에 임베딩 서버가 있어야 하고, `search_collection`의 속을 바꾸면 AI 사서 행동이 바뀌어 LLM 평가로 전후를 비교해야 한다. 이 change가 그 둘을 맡는다.

## What Changes

- **소장 도서 검색 tool의 속을 주제로 찾기로 바꾼다**(tool 이름과 입력은 그대로)
  - `search_collection`과 어린이 `search_children_books`는 낱말이 있으면 주제로 찾기(`find_by_topic`, 기본 설정)로 순위를 만든다. 낱말이 없는 둘러보기는 지금 동작 그대로다.
  - 결과는 최대 10권이고 순서만 바뀐다. 결과 모양은 관련 책 tool과 같은 `{books, note}`로 맞춘다.
  - 낱말이 하나도 맞지 않아 벡터 순위로만 나온 결과에는 "낱말이 맞는 책이 없다. 소개로 요청과 맞는지 보고 맞지 않으면 없다고 말한다"는 표시를 준다. 결과를 비우는 유사도 문턱은 두지 않는다.
- **벡터 질의는 LLM이 넘긴 낱말을 이은 것**(바꾸기 전 확인 실험으로 정함)
  - 실험의 기본값은 이용자 문장이지만, 문장은 여러 턴("더 가벼운 거"), 안내가 섞인 문장, 다른 낱말로 다시 찾기에서 주제를 잃는다. 낱말은 LLM이 대화 맥락을 담아 고른다.
  - 실험 틀에서 합친 순위의 벡터 질의만 낱말로 바꾼 변형(`hybrid-vkw`)을 문장과 짝 비교하고, 미리 정한 규칙(design 결정 2)으로 제품 입력과 기본값을 정한다. 이용자 문장은 tool에 넘기지 않는다.
- **서비스 중 질의 인코딩과 내려가기**
  - 앱이 임베딩 서버 클라이언트를 하나 두고 대화 실행에 실행 값으로 넘긴다. 질의 인코딩에는 짧은 시간 제한(기본 2초)을 따로 둔다.
  - 서버가 꺼졌거나, 느리거나, 다른 모델이면 키워드 순위만으로 내려간다. 결과 모양은 같고 이용자 답에는 드러내지 않는다. 로그에는 실패 종류만 남기고, 실패 뒤 30초 동안은 서버를 다시 부르지 않는다.
  - 임베딩 서버는 지금처럼 Compose 프로필(`embedding`)로 띄운다.
- **AI 사서 평가 전후 비교**
  - 평가 표본(87권)을 적재할 때 벡터도 넣는다. 문서 벡터는 저장소 밖 캐시 파일에 두어 두 번째부터는 임베딩 서버 없이 적재한다.
  - 주제 시나리오를 더한다(상황 질의, 여러 턴, 다시 찾기, 소장하지 않은 주제, 어린이 주제).
  - 바꾸기 전 기준 실행과 바꾼 뒤 실행을 같은 시나리오로 두 번씩 돌려 비교한다. 규칙 위반, 기대 불일치, 주제 낱말 일치, 어린이 판단, tool 호출 수, 걸린 시간을 본다. 관련 책 시나리오 4개도 벡터가 있는 표본에서 다시 본다. LLM 실행은 호출 수와 비용을 알리고 승인을 받은 뒤에만 한다.
- **Open Questions 정리**
  - 소장 도서가 없는 주제 요청: 유사도 문턱 대신 "키워드 근거 없음" 표시로 답한다. 있는 라벨로 키워드 순위가 빈 질의의 벡터 결과 품질을 진단해 근거를 남긴다.
  - 시리즈 묶기·MMR은 끈 채로 둔다(품질 같음, 겹침만 줄어듦. LLM이 10권 중 고른다).
- **범위 밖**: 주제로 찾기 REST API, 결과에 신호별 근거 문구, 대화 추천 품질 라벨(어울림 라벨, Hit Rate)과 LLM 채점(`add-recommendation-evals`), 임베딩 서버 상시 운영 배포(`add-observability-deploy`).

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `catalog/topic-recommendation`: 제품 경로(기본 설정, 결과 수), 질의 인코딩 시간 제한과 키워드 순위로 내려가기, 키워드 근거 없음 표시
- `agent/librarian`: 조회 tool의 소장 도서 검색이 주제로 찾기를 쓰고 결과 모양이 바뀜, 질의 인코더 실행 값, 주제 요청에 답하는 에이전트 동작(평가)
- `features/children`: 어린이 도서 검색 tool이 같은 주제로 찾기를 어린이 범위로 씀
- `platform/recommendation-experiments`: 벡터 질의 입력을 낱말로 바꾼 합친 순위 변형

## Impact

- 코드: `app/library/recommendation/topic.py`(제품 진입 함수, 내려가기), 새 `app/library/services/topic.py`, `app/central/external/tei.py`·`app/central/embedding.py`(질의 시간 제한), `app/core/config.py`(질의 시간 제한 설정), `app/library/tools.py`(검색 tool), `app/library/librarian.py`(프롬프트, 프로필 버전 v6), `app/library/services/chat.py`·`app/library/api/librarian.py`(인코더 실행 값), `app/features/children/tools.py`, `app/main.py`(인코더 조립), `evals/librarian/`(벡터 적재, 시나리오, 비교), `evals/recommendation/variants.py`
- DB: 마이그레이션 없음. 개발 DB는 바꾸지 않는다(실험은 읽기만). 평가 표본은 테스트 DB에서 되돌린다.
- API: 바뀌는 엔드포인트 없음. SSE 사건 순서와 내용도 그대로다.
- 외부 호출: 없음. 정보나루·카카오·YES24를 부르지 않는다.
- 임베딩 서버: 평가 표본 문서 벡터 첫 적재(87권, CPU 약 2분), 확인 실험의 새 질의 인코딩, LLM 평가 실행 동안만 띄우고 내린다.
- LLM: 평가 실행만. 승인 뒤에 한다(design 결정 9의 추정).
- 문서: `CLAUDE.md`(현재 단계, 명령), `docs/roadmap.md`, `app/library/README.md`, `app/features/README.md`, `evals/librarian`·`evals/recommendation/README.md`, `docs/reports/search-recommendation-strategy.md`(1절, 5.2절, 9절)
