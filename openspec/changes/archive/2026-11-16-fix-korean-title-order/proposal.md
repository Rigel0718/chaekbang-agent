## Why

개발·테스트 DB의 기본 collation이 `en_US.utf8`(glibc)이라 `ORDER BY title`이 가나다순이 아니다. 2026-11-16에 다시 재 보니 `나비 | 하늘 | 가나다`처럼 한글이 섞이고, `10대`가 `가나다 10`과 `가나다 2` 사이에 끼고, 영문이 한글 앞뒤로 갈린다. 서명은 찾기·검색·목록에서 마지막 동점 기준이라 이용자와 담당자 눈에 바로 보인다. `add-recommendation-experiments` 동안에는 키워드 동점 순서가 실험 기준이라 일부러 미뤘고, 그 change가 archive되어 지금 고친다. 다음 change인 `add-related-book-experiments`가 같은 순서 규칙 위에서 돌아가야 한다.

## What Changes

- **서명 정렬 규칙 하나**: 서명으로 순서를 정하는 모든 곳은 한국어 정렬 규칙(PostgreSQL ICU `ko-x-icu`)을 쓴다. 기호·공백 → 숫자 → 한글(가나다) → 영문(대소문자 무시, 같으면 소문자 먼저) 순서다. 숫자는 값이 아니라 글자 순서다(`10대` < `2권`).
- **정렬할 때만 적용**: 컬럼과 DB의 collation은 바꾸지 않는다. 비교·검색(`=`, `LIKE`, 자모 키, 편집 거리 유사도)과 인덱스는 그대로다.
- **적용하는 곳**(지금 코드 기준 8곳)
  - 기관 도서 목록(`library_books.py`)
  - 키워드 검색과 깊은 키워드 순위의 공통 순서(`search.py`의 `ranked_query`)
  - 서명·저자 찾기 2곳, 자동완성 1곳, 문장 속 서명 찾기 2곳(`lookup.py`)
  - 같은 저자 조회(`authors.py`): 지금은 Python 문자열 비교(코드 포인트 순서)라 DB와 영문·숫자 위치가 다르다. 서명 순서는 SQL에서 정하고 Python에서는 겹치는 지은이 수로만 다시 줄 세운다.
- **collation 확인**: `ko-x-icu`가 없는 PostgreSQL(ICU 없이 빌드된 서버)에서는 마이그레이션이 분명한 오류로 멈춘다. 스키마는 바꾸지 않는다.
- **동작 변화**: 같은 점수·같은 단계인 책의 순서만 바뀐다. 점수, 결과에 드는 책, 개수 제한은 그대로다. 단, 개수 제한 경계에서 동점인 책은 어느 책이 잘리는지가 바뀔 수 있다.

범위 밖: 저자·시리즈명 정렬(지금 저자나 시리즈명으로 줄 세우는 곳이 없다. 저자 찾기도 서명으로 동점을 가른다), 숫자를 값으로 정렬하기(`가나다 2` < `가나다 10`, 권차 정렬은 시리즈 묶기와 함께 본다), DB 기본 collation 바꾸기, 운영 배포.

## Capabilities

### New Capabilities

(없음)

### Modified Capabilities

- `platform/text-normalization`: 서명 정렬 순서 규칙 추가(가나다, 문자 종류 순서, 비교에는 쓰지 않음)
- `platform/database-schema`: 한국어 정렬 규칙이 없는 DB에서 마이그레이션이 멈춘다
- `catalog/book-lookup`: 찾기 결과 순서와 자동완성의 동점 순서가 서명 정렬 순서
- `catalog/collection-search`: 결과 순서와 둘러보기의 동점 순서가 서명 정렬 순서
- `catalog/library-books`: 목록 순서(표시 서명 정렬 순서, 같으면 id)를 명시
- `catalog/book-contributors`: 같은 저자 조회의 순서(겹치는 지은이 수, 서명 정렬 순서, id)를 명시

## Impact

- 코드: `app/core/text.py`(정렬 도우미), `app/library/services/library_books.py`, `app/library/recommendation/{search,lookup,authors}.py`, 새 마이그레이션 하나(확인만, 스키마 변화 없음)
- 테스트: 정렬 시나리오 테스트, collation 확인 테스트. 기존 순서 테스트 중 영문·숫자 서명에 기대던 것이 있으면 고친다
- 평가: `evals.catalog_search`의 동점 수치(word·author 1위 등)와 추천 실험 `topic` 수치가 바뀔 수 있다. 바뀌면 전후와 이유만 보고하고 고치지 않는다
- 외부 호출 없음, 의존성 추가 없음. 개발 DB는 확인 마이그레이션만 적용한다(적용 전 백업)
