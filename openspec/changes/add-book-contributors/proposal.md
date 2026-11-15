## Why

추천 실험(`add-recommendation-experiments`)의 "같은 저자" 신호와 출처 일반화(`add-bibliographic-sources`)는 사람과 분류를 글자가 아니라 같은 값으로 맞춰 볼 수 있어야 시작할 수 있다. 지금 저자는 `칼 멜링 글/브라이트 스타 그림/김맑아,김경덕 역` 같은 원문 한 줄이라, 역자가 같은 책이 "같은 저자"로 잡히고 `김 영 하`와 `김영하`가 다른 사람이 된다. 출처가 YES24, 카카오, 도서관 정보나루 셋이 되면 같은 사람·같은 분류가 다른 글자로 들어오므로, 정규화 규칙을 한 곳에 두고 저자를 역할별로 구조화하는 일을 먼저 한다.

2026-11-12에 정한 "저장 구조와 정규화"는 1주를 넘어 둘로 나눈다. 이번은 앞쪽(정규화, 기여자 표, 저자 키)이고, 벡터 두 층과 YES24 약 500권 실험 장서, 적재 배치 기본값은 다음 change `add-official-book-embeddings`에서 한다. 범위는 줄이지 않았다.

## What Changes

- **정규화 통일**: `app/core/text.py`를 글자 정규화의 한 곳 기준으로 넓힌다.
  - 저장용(`clean_spaces`)에 유니코드 NFC를 더한다.
  - 비교용(`compact`)에 NFC와 전각 → 반각을 더한다. 서명·저자 찾기의 SQL 함수와 찾기 키 생성 열이 함께 바뀐다(마이그레이션). 코드와 SQL의 결과가 같다는 테스트를 넓힌다.
  - 이름 맞춤 키(`match_key`)를 새로 둔다. 비교용에 문장부호 제거를 더한 것으로, 사람 이름과 시리즈명에 쓴다. 코드로만 계산해 저장하므로 SQL 쪽 규칙은 없다.
  - KDC 키(`kdc_key`): 표기가 달라도 같은 숫자 문자열(`813.7`)이 되게 한다. 기관 도서의 분류기호는 저장할 때 이 값으로 맞춘다.
- **역할 표와 저자 해석기**: 역할 표기(`저`, `지음`, `글`, `(지은이)` 등)를 한 역할로 읽는 표를 `app/core/`에 두고, 해석기는 출처마다 둔다. 이번에는 YES24(`app/central/external/yes24/`)와 기관 파일의 원문 저자(여러 꼴을 관대하게 읽는다). 표본 87권의 저자 표기로 테스트를 고정한다.
- **공식 서지 기여자 표** `book_contributors`(운영자 층, 기관 공통 테이블): 이름, 이름 맞춤 키, 역할, 역할 원문, 순서. 공식 서지를 만드는 모든 경로(채움, 시드, 평가 표본 적재)가 같은 함수로 채운다. 원문 `author`는 그대로 두고 표시는 원문으로 한다.
- **기관 도서 저자 키** `library_books.author_keys`(배열): 역자·감수자를 뺀 지은이들의 이름 맞춤 키. 코드가 저장할 때 계산하고, 모든 쓰기 경로(등록, 수정, 가져오기, 시드)가 채우는지 테스트로 지킨다. 공식 서지에 연결된 책은 기여자 표를 읽고, 연결되지 않은 책만 이 키를 쓴다.
- **같은 저자 조회**: 한 기관의 추천 가능한 책 중 기준 책과 지은이가 겹치는 책을 돌려주는 service 함수. 연결된 책과 연결되지 않은 책이 같은 키로 만난다. REST와 tool에는 잇지 않는다(실험과 `add-related-books`가 쓴다).
- **다시 만들기 스크립트** `scripts/rebuild_contributors.py`(운영자): 기존 공식 서지의 기여자와 기존 기관 도서의 저자 키를 채우고, 역할 표나 규칙을 고친 뒤 다시 맞춘다. `--check`는 차이만 센다.
- **문서**: CLAUDE.md와 `docs/design.md`의 MVP 순서에 `add-related-books` 앞으로 change 넷을 넣고 `add-related-books`, `add-recommendation-evals`의 설명을 고친다(제안과 함께 반영함).

사용자가 정한 것에서 넓힌 곳이 하나 있다. 역할을 여섯(`author`, `illustrator`, `translator`, `editor`, `supervisor`, `original`)에 `other`를 더해 일곱으로 한다. 표본에 `기획`, `사진`이 있고, 모르는 역할을 지은이로 읽으면 "같은 저자"가 틀리기 때문이다(design 결정 4).

범위 밖: 벡터 두 층, YES24 약 500권과 가상 기관, 적재 배치 기본값(`add-official-book-embeddings`). 추천 실험 틀과 전략 비교(`add-recommendation-experiments`). 카카오·정보나루 해석기(`add-bibliographic-sources`). 기여자의 REST 응답·화면 표시와 tool(`add-related-books`). 외국 저자의 다른 음역과 동명이인 풀기.

## Capabilities

### New Capabilities

- `platform/text-normalization`: 저장용·비교용 정규화, 이름 맞춤 키, KDC 키, 코드와 SQL의 일치.
- `catalog/book-contributors`: 저자 원문 해석(역할, 이름 나누기), 공식 서지 기여자 저장, 기관 도서 저자 키, 같은 저자 조회, 다시 만들기 실행.

### Modified Capabilities

- `platform/database-schema`: 테이블이 21개가 되고 `book_contributors`가 기관 공통 테이블에 더해진다. `library_books`에 저자 키 열이 생긴다.
- `catalog/library-books`: 분류기호를 저장할 때 KDC 숫자 문자열로 맞춘다.
- `catalog/book-lookup`: 전각 글자와 분해형 한글(NFD)로 적힌 서명·질의도 찾는다.
- `platform/dev-seed-data`: 시드가 공식 서지의 기여자와 기관 도서의 저자 키를 함께 만든다.

## Impact

- **코드**: `app/core/text.py`, `app/core/contributors.py`(새로), `app/central/models.py`·`app/central/contributors.py`(새로)·`app/central/enrichment.py`·`app/central/external/yes24/`, `app/library/models/catalog.py`, `app/library/services/`(등록, 수정, 가져오기), `app/library/recommendation/authors.py`(새로), `app/seed/catalog.py`, `evals/librarian/catalog.py`, `app/models.py`, `scripts/rebuild_contributors.py`(새로), `migrations/`.
- **DB**: 마이그레이션 하나. 테이블 `book_contributors`, 열 `library_books.author_keys`, SQL 함수 `ko_jamo`·`ko_jamo_starts` 교체와 찾기 키 생성 열 다시 계산. 개발 DB는 적용 전에 백업한다. 적용 뒤 다시 만들기 스크립트를 한 번 돌린다.
- **API**: 경로와 응답 구조는 그대로다. 등록·수정 응답의 분류기호가 정규화된 값으로 나온다.
- **검색**: `compact`가 바뀌어 서명·저자 찾기, 키워드 검색, 가져오기 머리글 인식, 어린이 규칙이 전각·NFD 입력을 같은 글자로 본다. `evals/catalog_search` 점수를 전후로 비교해 보고한다.
- **외부 호출**: 없다. YES24, LLM, 임베딩 서버를 부르지 않는다.
- **의존성**: 더하지 않는다(`unicodedata`는 표준 라이브러리, PostgreSQL `normalize()`는 13부터 있다).
