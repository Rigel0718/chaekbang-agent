## Why

추천 요청 세 종류 중 주제로 찾기만 비교를 마쳤다(`add-recommendation-experiments`, 키워드+벡터 RRF 채택). 찾은 책 카드 아래 "비슷한 책"과 조건 없는 "아무거나"는 아직 신호도 합치는 방법도 없어, 제품에 내보내기(`add-related-books`) 전에 같은 틀·같은 라벨 방식으로 비교해 기본 설정을 수치로 정한다. 책→책 유사도에서도 임베딩 텍스트 `full`이 맞는지(이전 Open Question 2)도 여기서 확인한다.

## What Changes

- **먼저 topic 기준 맞추기**: `fix-korean-title-order` 뒤 topic 상위 5권에 새로 든 라벨 없는 책(6건 이상)에 보충 라벨 초안을 달고 topic을 다시 돌려 기준 수치를 새로 적는다. CLAUDE.md "현재 단계"의 `fix-korean-title-order`를 끝난 것으로 고친다.
- **비슷한 책 신호**(제품 패키지 `app/library/recommendation/`, REST·tool에는 잇지 않는다)
  - 같은 시리즈(공식 서지 시리즈 키), 같은 저자(기존 `same_author_books`를 순위로), 같은 KDC 세목(KDC가 소수점 첫째 자리까지 같은 책), 벡터 이웃(기준 책의 **저장된** 벡터로 두 층 조회, 질의 인코딩 없음)
  - 기준 책 자신과 같은 책의 다른 판본(판본 표기를 지운 서명이 같고 지은이가 겹침)은 뺀다
  - 신호별 순위를 RRF로 합치거나 규칙 신호를 먼저 두는 방식, 시리즈 묶기·MMR, 결과마다 신호별 근거
  - 범위(그 기관, 추천 가능, 부르는 쪽이 넘긴 조건)는 순위 전에 건다. 어린이 기준 책에는 어린이 기능이 조건을 넘긴다
- **아무 조건 없음 신호**
  - 최근 기록(책 1권 이상): 기록 책들의 벡터 평균 이웃, 책별 이웃 순위의 RRF, 겹치는 저자·같은 시리즈. 기록 책과 그 다른 판본은 뺀다
  - 우리 도서관 인기: 그 기관의 최근 대출 행 수 순위. 기록 결과가 모자랄 때 채운다. 실험 장서에는 대출 행이 없어 0건으로 보고하고 테스트 DB로 확인한다
  - 정보나루 인기와 빈 기록은 이번에 재지 않는다(`add-bibliographic-sources`)
- **실험 틀 넓히기**(`evals/recommendation/`, LLM·외부 API 호출 없음)
  - `similar`, `history` 실행: 변형, 지표(nDCG@5 주 지표, Hit@5, Recall@10, 겹침, 위반), 짝 비교, 묶음별 표(어린이·일반, 관련 책 있음·없음 / 같은 분야·섞임·어린이)
  - 라벨 초안 넣기(`draft`)와 검수 화면(`review`)을 `similar`·`history`로 넓힌다
  - 텍스트 종류 비교(`full`, `with_author`, `description`, 필드별)를 책→책에서 다시 잰다. 벡터는 이미 적재돼 있어 다시 적재하지 않는다
  - "같은 외부 분류"(상위 분야 18가지)는 세목 대신이 아니라 진단 변형 하나로만 잰다(벡터 이웃을 같은 외부 분류 안으로 좁힘)
- **라벨**(2026-11-16 사용자 결정): 라벨은 Claude가 단다. 기준 책·최근 기록의 눈에 띄는 2권(학습지, 같은 지은이 중복)도 Claude가 규칙으로 바꾸고 내역만 보여 준다. 실행 전 라벨(비슷한 책 821건, 최근 기록 599건)은 어떤 변형도 돌리기 전에, 실행 뒤 보충도 Claude가 단다. 사용자는 전수 검수 대신 결과와 무관하게 해시로 정한 고정 표본 45건만 본다(약 15분). 일치율을 요약에 적고, 30% 이상을 고치면 멈춘다. 라벨 파일은 바꾸기 전에 백업한다
- **결정 기록**: 두 요청의 단계별 결과 표, 채택 설정과 근거, 책→책 텍스트 종류 결론을 design에 남긴다. 기본 종류가 `full`이 아니게 되면 스펙 delta를 먼저 고치고 알린다

범위 밖: REST·AI 사서 tool·카드 아래 비슷한 책(`add-related-books`), 카카오·정보나루 연동과 실제 KDC·함께 대출된 책·정보나루 인기(`add-bibliographic-sources`), 빈 기록의 "아무거나", 어린이 요청 판단과 LLM이 든 평가(`add-recommendation-evals`), 개인화(회원 대출 기록 연결, 2단계).

## Capabilities

### New Capabilities

- `catalog/related-recommendation`: 비슷한 책과 최근 기록 기반 추천의 후보 순위. 신호(같은 시리즈·같은 저자·같은 KDC 세목·벡터 이웃·같은 외부 분류), 기준 책·다른 판본 제외, 합치기와 근거, 최근 기록 합치기, 우리 도서관 인기, 기관 범위·추천 가능·범위 조건

### Modified Capabilities

- `catalog/book-embeddings`: 기준 책의 저장된 벡터로 이웃 조회(질의 인코딩 없음, 두 층, 여러 책의 평균 벡터)
- `platform/recommendation-experiments`: 비슷한 책·최근 기록 세트의 실행, 묶음별 표, 라벨 초안·검수 화면의 세트 넓히기, 고정 표본 검수와 일치율, 실행 전 후보에서 다른 판본 빼기

## Impact

- 코드: 새 `app/library/recommendation/related.py`(신호·합치기·최근 기록·인기), `embeddings.py`(저장된 벡터로 이웃), `authors.py`(재사용), `evals/recommendation/`의 `__main__.py`·`variants.py`·`draft.py`·`review.py`·`label.py`
- DB: 마이그레이션 없음. 개발 DB는 읽기만 한다(벡터 다시 적재 없음). 바꿀 일이 생기면 먼저 백업한다
- 임베딩 서버: 필요 없다(책→책은 저장된 벡터, topic 재실행은 질의 벡터 캐시)
- 외부 호출: 없음. LLM 호출 없음
- 사용자 시간: 바꾼 기준 책 내역 훑기 몇 분, 표본 검수 45건 약 15분
- 기존 동작: `same_author_books`, `similar_books`, `find_by_topic`, AI 사서, `evals.catalog_search`는 그대로다
