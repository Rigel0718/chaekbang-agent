## Why

추천 품질이 이 프로젝트의 핵심 지표인데, 지금은 추천 방식을 비교할 틀도 평가 세트도 없다. 벡터 두 층과 실험 장서 525권(`add-official-book-embeddings`)이 생겼으므로, 제품에 내보내기(`add-related-books`) 전에 같은 평가 세트에서 변형을 나란히 재고 기본 설정을 수치로 정한다. 임베딩 텍스트도 지금은 "저자 없음(v2)"을 판단으로 정해 두었을 뿐이라 비교로 확정해야 한다.

## What Changes

1주를 넘어 요청 종류로 둘로 나눈다(2026-11-15 사용자 결정). 범위는 줄이지 않았다.

- **이번 `add-recommendation-experiments`**: 실험 틀, 요청 세 종류의 평가 세트(질의·기준 책·최근 기록)와 주제 질의의 라벨, 주제로 찾기의 단계별 변형 비교, 임베딩 텍스트 종류 비교와 기본 확정
- **다음 `add-related-book-experiments`**(새 이름): 비슷한 책(같은 저자·같은 시리즈·같은 KDC 세목·벡터 이웃)과 아무 조건 없음(최근 기록 → 우리 도서관 인기 → 정보나루 인기)의 신호와 변형 비교. 이번에 만든 평가 세트·라벨 도구와 확정한 텍스트 종류를 쓰고, 비슷한 책·최근 기록의 라벨은 그때 단다(2026-11-16 결정)

이번 change의 내용:

- **임베딩 텍스트 종류 더하기**(텍스트 버전 2 그대로, 종류 `kind`만 더함. 마이그레이션 없음)
  - `with_author`(v1과 같은 필드: 서명·저자·분류·소개), `description`(소개만), `title`·`category`(필드별 벡터. `description`과 함께 합친다)
  - 적재 CLI에 `--kind`. 텍스트가 비는 책(소개 없는 책의 `description`)은 벡터를 만들지 않는다
  - 유사도 조회가 범위 조건(`within`, 어린이 필터를 먼저 건다), 조회 깊이, 여러 종류의 가중 합을 받는다. 기본 동작(`full` 하나, 5권)은 그대로다
- **주제로 찾기 순위 함수**(제품 패키지 `app/library/recommendation/`, REST·tool에는 잇지 않는다)
  - 깊이를 정할 수 있는 키워드 순위, 벡터 순위, RRF 합치기, 시리즈 묶기, MMR. 기관 범위·추천 가능·범위 조건을 코드로 강제한다. 매개변수는 실험이 정하고 제품 연결은 `add-related-books`가 한다
- **실험 틀 `evals/recommendation/`**(LLM·외부 API 호출 없음)
  - 평가 세트: 주제 질의 30개(초안은 Claude가 장서를 보지 않고 쓰고 사용자가 고친다, 저장소에 둔다), 비슷한 책 기준 책 20권과 최근 기록 10개(규칙으로 고르고 저장소 밖에 둔다)
  - 어울림 라벨 0·1·2: Claude가 초안을 달고 사용자가 검수 화면에서 확인·고친다(2026-11-16 결정. 사람이 다 달기에는 1,384건이라 바꿨다. 이번에는 주제 질의만). 결과를 돌리기 전에 분야로 좁힌 목록에서 먼저, 돌린 뒤에는 변형들의 상위 결과 중 라벨 없는 책만 더한다. 라벨은 저장소 밖에 둔다
  - 변형 정의, 지표(nDCG@5, Hit@5, Recall@10, 다양성, 규칙 위반 0건), 짝 비교와 고정 시드 부트스트랩, 조정·확인 세트 나눔
  - 결과 기록(`data/runs/<시각>/`)과 지문(평가 세트·라벨 해시, 벡터 건수, 커밋). 질의 벡터를 캐시해 같은 명령이면 같은 수치가 나온다
  - 남겨 둔 분야(holdout 50권)는 질의·기준 책으로 쓰지 않는다(후보로는 남는다)
- **결정 기록**: 주제로 찾기의 단계별 결과 표, 임베딩 텍스트 종류 비교와 기본 결정(추천과 이유)을 design에 남긴다. 기본이 `full`이 아니게 되면 스펙 delta를 먼저 고치고 알린다
- **문서**: CLAUDE.md·`docs/design.md`의 change 순서에 `add-related-book-experiments`를 넣는다

범위 밖: 비슷한 책·아무 조건 없음의 신호와 비교(`add-related-book-experiments`). 카카오·정보나루 연동, 실제 KDC, 함께 대출된 책, 인기 대출, holdout 비교(`add-bibliographic-sources`). REST·AI 사서 tool·찾은 책 카드 아래 비슷한 책(`add-related-books`). LLM이 든 대화 추천 평가, 어린이 지표 둘(`add-recommendation-evals`). 결과를 비울 유사도 문턱, 벡터 인덱스.

## Capabilities

### New Capabilities

- `catalog/topic-recommendation`: 주제로 찾기의 후보 순위. 키워드·벡터 순위, RRF, 시리즈 묶기, MMR과 그 기관 범위·추천 가능·범위 조건
- `platform/recommendation-experiments`: 추천 실험 틀. 평가 세트와 라벨의 형식·위치, 라벨 도구, 변형 실행, 지표, 결과 기록과 재현

### Modified Capabilities

- `catalog/book-embeddings`: 임베딩 텍스트 구성(종류별 필드), 벡터 종류(비교용 종류, `--kind`, 빈 텍스트), 기관 범위 유사도 조회(범위 조건, 깊이, 여러 종류 합치기)

## Impact

- 코드: `app/core/embedding_text.py`, `app/central/embedding_text.py`, `app/central/embedding.py`(빈 텍스트 건너뛰기), `app/library/recommendation/embedding_text.py`, `embeddings.py`, 새 `topic.py`·`ranking.py`, `scripts/embed_books.py`, 새 `evals/recommendation/`
- DB: 마이그레이션 없음. 개발 DB의 실험 기관에 벡터 4종류 × 약 470건을 더 적재한다(약 20분, 적재 전 백업)
- 의존성: 더하지 않는다(MMR은 순수 Python)
- 외부 호출: 없음. LLM 호출 없음. 로컬 임베딩 서버만(질의 인코딩, 적재)
- 사용자 시간: 질의 초안 검토, 라벨 약 3,000건(약 2~3시간)
- 기존 동작: `similar_books`의 기본 호출, `search_collection`, AI 사서, `evals.catalog_search`는 그대로다
