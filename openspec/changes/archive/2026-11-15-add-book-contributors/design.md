## Context

- 저자는 원문 한 줄이다. 공식 서지 `books.author`는 YES24 원문(`칼 멜링 글/브라이트 스타 그림/김맑아,김경덕 역`), 기관 도서 `library_books.author`는 파일·입력 값(`김영하 지음` 등 꼴이 정해져 있지 않다)이다. 키워드 검색은 원문을 부분 문자열로, 서명·저자 찾기는 원문의 자모 키(`author_jamo_starts`, DB 생성 열)로 찾는다.
- 정규화는 `app/core/text.py`에 있다. `clean_spaces`(저장용), `compact`·`compact_sql`(비교용: 공백 제거, 소문자), 자모 키(`jamo`, `jamo_starts`와 SQL 함수 `ko_jamo`, `ko_jamo_starts`). 코드와 SQL의 일치는 `tests/core/test_text.py`가 DB에서 본다. NFC, 전각, 문장부호 규칙은 없다.
- `compact`를 쓰는 곳: `importing/normalize.py`·`columns.py`(머리글, 상태 값), `recommendation/search.py`(`compact_sql`), `recommendation/lookup.py`(자모 키), `features/children/rules.py`.
- 기관 도서를 쓰는 경로: `services/library_books.py`(등록 `LibraryBook(**data)`, 수정), `services/holding_imports.py`(`_new_book`, `_fill_book`), `app/seed/catalog.py`(Core `insert(LibraryBook)`), `evals/librarian/catalog.py`(평가 표본 적재, ORM). 공식 서지를 만드는 경로: `central/enrichment.py`(Core `insert(Book)`), `app/seed/catalog.py`(Core), `evals/librarian/catalog.py`(ORM).
- `books.kdc`는 YES24가 주지 않아 채움으로는 비어 있다. KDC는 사실상 기관 도서의 값(파일의 분류기호 열, 입력)이다. `recommendation/kdc.py`의 `kdc_class_name`은 청구기호에서 주류 이름을 읽는 별개 규칙이다.
- YES24 시리즈명은 응답의 목록을 `, `로 이어 한 문자열로 저장한다(`노부미 명랑 그림책, 두고두고 보고 싶은 그림책`).
- 표본 87권의 저자 표기에서 본 꼴(2026-11-12): `저` 48, `글`·`그림` 묶음 20, `글그림` 6, `글,그림` 2, `역` 18, `감수` 6, `원저`·`원작` 2, `기획` 2, `사진` 1, `공저` 2, `공역` 1, `등저` 1, `외 글`·`외 그림` 1, 역할 없음 1, 괄호가 있는 이름(`에반(하상희)`) 1, 로마자 이름 1.
- 개발 DB: 기관 2개, 공식 서지 45권(Faker 저자, 역할 표기 없음), 기관 도서 270권. `book_embeddings`는 비어 있다.

## Goals / Non-Goals

**Goals:**

- 글자 정규화 규칙이 한 곳에 있고, 저장용과 비교용의 경계가 분명하다.
- 저자 원문이 역할별 사람으로 풀려 공식 서지에 저장되고, 공식 서지가 없는 책도 같은 키로 맞춰진다.
- 저자 키를 빠뜨린 쓰기 경로가 생기면 테스트나 DB가 잡는다.
- 다음 change들이 스키마를 다시 바꾸지 않고 "같은 저자" 신호를 쓸 수 있다.

**Non-Goals:**

- 벡터 두 층, YES24 약 500권, 적재 배치 기본값(`add-official-book-embeddings`).
- 추천 점수, 순위, 근거 표시, 실험 틀(`add-recommendation-experiments`).
- 카카오·정보나루 해석기(`add-bibliographic-sources`).
- 기여자의 REST 응답, 화면, tool(`add-related-books`).
- 외국 저자의 다른 음역, 동명이인, 필명·본명 잇기. 사람에게 고유 id를 주는 전거 통제.
- 서명·저자 찾기의 방식 변경. 찾기는 지금처럼 원문의 자모 키다.

## Decisions

### 1. change를 둘로 나눈다

"저장 구조와 정규화" 전체는 약 9일로 본다(아래 5일 + 벡터 두 층 2일 + 실험 장서와 적재 2일). 1주 규칙에 따라 나눈다.

| change | 내용 | 예상 |
| --- | --- | --- |
| `add-book-contributors` (이번) | 정규화, 역할 표와 해석기, 기여자 표, 저자 키, 같은 저자 조회, 다시 만들기 | 5일 |
| `add-official-book-embeddings` (다음) | 공식 서지 벡터 테이블과 기관 도서 벡터 대상 변경, 두 층 조회, 필드별 벡터 칸, YES24 약 500권과 가상 기관, v1 적재, 배치 기본값, YES24 예외 문구 | 4일 |

이 순서인 이유: 실험 장서의 공식 서지를 만들 때 기여자가 함께 만들어져야 다시 채우지 않는다. 벡터 쪽은 정규화에 기대지 않는다. YES24 표본 예외 문구(CLAUDE.md, `evals/librarian/`)와 `add-book-embeddings` 결정 1을 뒤집는 기록은 500권을 받는 다음 change에서 고친다.

### 2. 정규화의 세 단계

| 단계 | 함수 | 규칙 | 쓰는 곳 | SQL 쪽 |
| --- | --- | --- | --- | --- |
| 저장용 | `clean_spaces` | 보이지 않는 글자 제거, 공백 하나로, 앞뒤 공백 제거, **NFC(추가)** | 가져오기 값, 기여자 이름, 분류기호 | 없음 |
| 비교용 | `compact`, `compact_sql` | **NFC(추가)**, **전각 → 반각(추가)**, 공백·보이지 않는 글자 제거, 소문자 | 찾기 자모 키, 키워드 검색, 머리글, 어린이 규칙 | `compact_sql`, `ko_jamo_starts` |
| 이름 맞춤 | `match_key` (새로) | 비교용 + 글자·숫자가 아닌 것 제거 | 기여자 이름 키, 저자 키, 시리즈명 | 없음(코드가 계산해 저장) |

- 사용자가 정한 두 단계(저장용, 비교용) 가운데 비교용을 둘로 나눈 것이다. **문장부호 제거는 이름 맞춤에만 넣는다.**
  - 이유 1: 서명에서는 문장부호가 뜻을 가른다(`C++`, `3.1 운동`, `1Q84`). 찾기의 편집 거리 기준은 `add-catalog-search` 평가로 맞춘 값이라, 문장부호까지 지우면 키 길이가 달라져 오탐·누락이 함께 움직인다.
  - 이유 2: 문장부호 규칙을 `ko_jamo_starts`에도 넣으면 코드와 SQL 두 벌이 된다. 이름 키는 저장할 때 코드가 계산하므로 한 벌로 끝난다.
  - 찾기에도 문장부호 제거를 원하면 Open Questions 1에서 정한다.
- **NFKC를 쓰지 않는다.** NFKC는 한글 호환 자모(`ㄱ` U+3131)를 조합형 자모(`ᄀ` U+1100)로 바꿔 자모 키(`데미ㅇ`)가 깨진다. 전각 → 반각은 U+FF01~U+FF5E를 U+0021~U+007E로 옮기는 표 하나로 한다(전각 공백 U+3000은 이미 공백 목록에 있다). 반각 가타카나·반각 한글 자모는 다루지 않는다.
- SQL: `compact_sql`은 `lower(regexp_replace(translate(normalize(coalesce(x, ''), NFC), <전각>, <반각>), …))`가 된다. `ko_jamo_starts`도 첫 정리 단계에 같은 두 가지를 넣는다. 전각 표 문자열은 `text.py`의 상수 하나에서 코드와 마이그레이션이 함께 쓴다(마이그레이션에는 그때의 값을 글자로 적어 고정한다).
- 순서: NFC → 전각 → 공백 → 소문자. 전각 영문 대문자가 소문자까지 가야 하기 때문이다.
- **확인(2026-11-13, 태스크 1.1)**: PostgreSQL 16.15에서 `normalize`와 `translate`는 모두 IMMUTABLE(`provolatile = i`)이고 DB 인코딩은 UTF8이다. 찾기 키 생성 열은 IMMUTABLE로 선언한 `ko_jamo_starts`를 부르므로 그 함수 안에서 두 함수를 바로 쓴다. 감싸는 함수는 따로 두지 않는다.
- 자모 키 쪽은 `compact`를 거치지 않는다(`jamo_starts`는 `clean_spaces` → 판본 표기 지우기 → 소문자). 그래서 NFC는 `clean_spaces`가, 전각 → 반각은 `jamo_spaced`가 맡는다. SQL `ko_jamo_starts`도 같은 자리(정리 단계의 NFC, 소문자 앞의 `translate`)에 넣는다. 판본 표기 지우기는 반각 괄호만 보므로 전각 괄호(`（개정판）`)는 두 쪽 모두 지우지 않는다.
- `clean_spaces`에 NFC를 넣어도 이미 저장된 행은 다시 쓰지 않는다. 비교용이 NFC를 하므로 찾기에는 영향이 없다.

### 3. KDC 키와 분류기호 저장

- `kdc_key(value) -> str | None`을 `app/core/text.py`에 둔다. 비교용으로 맞춘 뒤(공백·전각·대소문자) 앞의 `kdc`를 떼고, 맨 앞의 `\d{3}(\.\d+)?`를 읽는다. 그 뒤에 숫자가 이어지면(네 자리 숫자) 읽지 않는다. 끝의 `.`은 뗀다. 소수 끝의 0은 그대로 둔다(`813.70`은 드물고, 뗄 근거가 없다).
- 별치기호가 앞에 붙은 값(`아 813`)은 읽지 않는다. 기관마다 규칙이 달라 `kdc.py`의 청구기호 규칙과 같은 입장을 따른다.
- **저장**: 기관 도서의 `kdc`는 쓸 때 `kdc_key`로 맞춘 값을 저장한다. 읽을 수 없으면 `clean_spaces`한 원래 값을 둔다(기관의 입력을 버리지 않는다). 따로 `kdc_key` 열을 두지 않는 이유는 읽을 수 있는 값이면 원래 표기를 남길 가치가 없고, 열 하나로 같은 값·앞자리 비교(세목, 강목)를 SQL에서 바로 할 수 있어서다.
- **기존 행은 고치지 않는다.** 운영자 실행은 기관이 정한 값을 바꾸지 않는다는 규칙 때문이다. 다시 만들기 스크립트의 확인 방식이 맞춰지지 않은 분류기호 건수를 보고만 한다. 개발 DB의 시드 값은 이미 `813` 꼴이다.
- 공식 서지의 `kdc`는 지금 채우는 출처가 없다. 정보나루가 주면 `add-bibliographic-sources`에서 같은 함수로 맞춘다.
- `kdc_class_name`(청구기호 → 주류 이름)은 건드리지 않는다. 임베딩 텍스트가 이 함수를 쓰는데, `KDC 813`처럼 전에는 못 읽던 분류기호가 `813`으로 저장되면 그 책의 텍스트에 `문학`이 더해져 해시가 달라지고 증분 적재가 잡는다. 의도한 결과다.

### 4. 역할: 여섯에 `other`를 더한다

| 역할 | 표기 |
| --- | --- |
| `author` | 저, 지음, 글, 지은이, 저자, 작가, 공저, 편저, 글쓴이 |
| `illustrator` | 그림, 그린이, 일러스트, 삽화, 만화 |
| `translator` | 역, 옮김, 옮긴이, 번역, 역자, 편역 |
| `editor` | 편, 엮음, 엮은이, 편집, 편자 |
| `supervisor` | 감수 |
| `original` | 원저, 원작 |
| `other` | 기획, 사진, 해설, 구성, 각색, 그리고 표에 없는 모든 표기 |

- 사용자가 정한 여섯에서 `other`를 넓혔다. 표본에 `기획` 2건, `사진` 1건이 있다. 여섯에 억지로 넣으면 `정재승 기획`이 엮은이가 되고, 버리면 `무라카미 요코 사진`이 사라진다. 모르는 표기를 `author`로 읽으면 "같은 저자"가 틀리므로, 표에 없는 것은 `other`로 떨어지게 한다.
- 역할 원문(`role_text`, 예: `기획`)을 함께 저장한다. 화면에 역할을 보여 줄 때 `other`를 "기타"로 뭉개지 않기 위해서다. 역할 표기가 없던 이름은 비워 둔다.
- 한 사람이 두 역할이면(`글그림`, `글,그림`, `글·그림`) 행 둘로 저장한다(같은 이름, `author`와 `illustrator`, 순서는 이어서).
- `공`·`등`은 역할 앞에 붙는 말로 본다(`공저`, `공역`, `등저`, `공편`). `외`는 이름 뒤에 붙는 말로 보고 뺀다(`정재은 외 글`). "외 몇 명"은 저장하지 않는다.
- 역할 표는 `app/core/contributors.py`의 상수 하나다. 비교는 `match_key`로 한다(`(지은이)`, `지은이:`, `지은이`가 같은 표기).

### 5. 해석기의 위치와 규칙

| 위치 | 내용 |
| --- | --- |
| `app/core/contributors.py` | `ContributorRole`, 역할 표, `Contributor(name, role, role_text)`, 공통 조각(끝의 역할 읽기, 이름 나누기), 기관 파일 해석기 `parse_author_text`, `author_keys(author)` |
| `app/central/external/yes24/contributors.py` | `parse_yes24_author` |
| `app/central/contributors.py` | 출처에 맞는 해석기 고르기, 공식 서지의 기여자 저장 `sync_contributors` |

- 역할 표와 기관 파일 해석기를 `core`에 두는 이유: 운영자 층(YES24 해석, 출처 없는 공식 서지)과 기관 공통(저자 키)이 함께 쓰고, 문자열만 다루는 순수 함수라서다. `isbn.py`와 같은 자리다.
- **YES24 해석기**(꼴이 정해져 있다): `/`로 묶음을 나눈다 → 묶음 끝에서 역할 표기를 가장 긴 것부터 맞춘다(`글,그림`을 이름 나누기보다 먼저 읽는다) → 남은 앞부분을 `,`로 나눠 이름으로 삼는다. 역할 표기가 띄어 쓰여 있으면(`글, 그림`) 가장 긴 역할 꼬리를 읽는다 → 이름 끝의 `외`를 뗀다. 역할 표기가 없으면 `author`, 표에 없는 끝 낱말은 역할로 보지 않고 이름의 일부로 둔다(`스와프나 해도우`처럼 이름이 여러 낱말이기 때문). 그래서 "표에 없는 표기는 `other`"는 YES24에서는 표에 `other`로 적어 둔 표기(`기획`, `사진` 등)에만 해당하고, 정말 처음 보는 표기는 이름 끝에 붙은 채 `author`가 된다. 표본 전체 테스트(결정 10)가 이런 이름을 잡아 표에 더하게 한다.
- **기관 파일 해석기**(꼴이 정해져 있지 않다): 묶음은 `/`, `;`, `|`. 역할은 ① 앞의 이름표(`지은이: 한강`) ② 괄호(`한강 (지은이)`) ③ 끝의 낱말(`한강 지음`) 순으로 찾는다. 괄호 안이 역할 표에 없으면 역할로 보지 않고 이름의 일부로 둔다(`에반(하상희)`). 표에 없는 표기를 `other`로 읽는 것은 이름표 꼴뿐이다(구현 때 정함, 2026-11-13). 괄호 꼴은 `,`로 나눈 조각마다 역할을 읽는다(`백희나 (지은이), 김소연 (옮긴이)`). YES24 꼴도 이 규칙으로 읽힌다. 아무 꼴에도 맞지 않으면 원문 전체를 `author` 한 명으로 둔다. 이름 안의 `,`(`홍길동, 김철수`)는 사람을 나누고, `·`은 나누지 않는다(`사회평론 역사연구소`처럼 단체 이름에 흔하다. 틀리는 쪽을 덜 나누는 쪽으로 둔다).
- 카카오(`authors`, `translators` 배열)와 정보나루(`지은이: A; 그림: B; 옮긴이: C`)는 `add-bibliographic-sources`에서 `external/` 아래에 같은 모양으로 더한다. 정보나루 꼴은 기관 파일 해석기의 이름표 꼴과 같아 공통 조각을 다시 쓴다.
- 이름은 `clean_spaces`한 값으로 저장하고, `match_key`가 빈 이름(기호뿐)은 버린다.

### 6. 테이블 `book_contributors`

| 열 | 타입 | 비고 |
| --- | --- | --- |
| `id` | PK | |
| `book_id` | FK → books, NOT NULL, `ON DELETE CASCADE` | 공식 서지에서 다시 만들 수 있는 값이다 |
| `position` | smallint, NOT NULL | 원문 순서, 0부터 |
| `name` | varchar(200), NOT NULL, 빈 값 금지 | 저장용 이름 |
| `name_key` | varchar(200), NOT NULL, 빈 값 금지, 인덱스 | `match_key(name)` |
| `role` | varchar(32) + CHECK `contributor_role` (`str_enum`) | 일곱 값 |
| `role_text` | varchar(50), NULL | 역할 원문 |
| `created_at`, `updated_at` | timestamptz | `TimestampMixin` |

- 유니크: (`book_id`, `position`).
- 기관 공통 테이블이다(`SHARED_TABLES`). `library_id`가 없고 운영자 층 `app/central/models.py`에 둔다. 기관 API에는 쓰기 경로가 없다.
- 사람 테이블(`persons`)을 따로 두지 않는다. 동명이인과 음역을 풀 근거가 없어 사람 id를 줄 수 없고, 맞춤은 `name_key` 값 비교로 충분하다.
- `Book.contributors` 관계는 두지 않는다(구현 때 정함). `LibraryBook.book`이 joined 로딩이라 관계를 두면 실수로 따라 읽기 쉽고, 쓰는 곳(`sync_contributors`, 같은 저자 조회)은 모두 쿼리로 읽는다.
- `sync_contributors(session, book)`: `book.external_source`에 맞는 해석기로 `book.author`를 풀어, 지금 행과 다르면 지우고 다시 넣는다. 같으면 아무것도 쓰지 않는다(다시 만들기의 "고친 건수 0"). 공식 서지를 만드는 세 경로(채움의 `_create_official`, 시드, 평가 표본 적재)가 부른다. "이미 있는 공식 서지는 고치지 않는다" 규칙은 서지 값에 대한 것이고, 기여자는 그 값에서 나온 파생 값이다.

### 7. 기관 도서 저자 키 `library_books.author_keys`

- `text[]`, NOT NULL, 기본값 없음. 값은 `author_keys(author)`: 기관 파일 해석기로 푼 사람 가운데 `author`·`original`의 `name_key`를 순서대로, 중복 없이.
- **연결 여부와 상관없이 항상 채운다.** "연결되지 않은 책에서만 쓴다"는 읽는 쪽 규칙이다(`LibraryBook.shown`과 같은 모양). 항상 채우면 불변식이 `author_keys == author_keys(author)` 하나라 검사하기 쉽고, 연결이 풀리거나(ISBN 수정) 나중에 생겨도 다시 계산할 일이 없다.
- **쓰는 방법**: 모델의 `@validates("author")`가 `author_keys`를 함께 정한다. 등록(`LibraryBook(**data)`), 수정(`setattr`), 가져오기(`_new_book`), 평가 표본 적재가 모두 ORM이라 따로 부르지 않아도 채워진다. 사용자가 정한 "모든 경로가 같은 함수를 부른다"를 한 곳에서 지키는 방법이다.

| 안 | 내용 |
| --- | --- |
| **A. 모델 validator + NOT NULL (선택)** | ORM 경로는 빠뜨릴 수 없다. Core 경로(시드)는 직접 계산해 넣어야 하고, 빠뜨리면 DB가 거부한다 |
| B. service마다 함수 호출 | 새 쓰기 경로가 생길 때마다 기억해야 한다. 테스트 픽스처가 만든 행은 키가 빈다 |
| C. DB 생성 열 | 역할 해석을 SQL로 한 벌 더 만들어야 한다(사용자가 피하기로 한 것) |

- Core `insert(LibraryBook)`는 `app/seed/catalog.py` 한 곳이다. 같은 `author_keys` 함수로 값을 넣는다. Core `update(LibraryBook)`(`enrichment_targets.py`)는 저자를 건드리지 않는다.
- **지키는 테스트**: ① 저자 키 없는 직접 저장을 DB가 거부한다 ② 등록, 수정, 가져오기 적용, 시드를 실제로 돌린 뒤 모든 행에서 불변식이 성립한다 ③ `app/`에서 `update(LibraryBook)`가 `author`를 값으로 주는 곳이 없다(소스 검사. 지금은 0곳).
- 인덱스는 두지 않는다. 같은 저자 조회는 한 기관 범위(수천 권)의 배열 겹침 비교다. 느려지면 GIN을 더한다.
- 마이그레이션은 기본값 `'{}'`로 열을 더한 뒤 기본값을 뗀다. 기존 행은 다시 만들기 스크립트가 채운다(결정 9).

### 8. 같은 저자 조회

```python
async def same_author_books(session, library_id, library_book_id, *, limit=20) -> list[LibraryBook]
```

- `app/library/recommendation/authors.py`. 책의 지은이 키를 한 식으로 읽는다: 연결된 책은 `book_contributors`에서 `role in (author, original)`인 `name_key`, 아니면 `library_books.author_keys`. 기준 책의 키와 하나라도 겹치고 `recommendable_ids(library_id)`에 있는 책을 돌려준다. 기준 책은 `get_owned`로 확인한다(다른 기관이면 `NotFoundError`).
- 순서는 겹치는 키 수, 서명, id다. 점수와 다른 신호와 합치기는 실험 change의 일이다. 여기서는 저장 구조가 두 층에서 만나는지를 고정하는 것이 목적이다.
- **`illustrator`는 기본에 넣지 않는다.** 사용자가 정한 기본(`author`·`original`)대로다. 표본의 그림책 20여 권 중 `글그림` 한 사람인 책은 이미 `author`로 잡힌다. 글과 그림이 다른 책에서 그린이까지 넣으면 `브라이트 스타`(제작 스튜디오)처럼 한 그린이가 수십 권을 묶는다. 역할은 저장돼 있으므로 `add-recommendation-experiments`에서 "어린이 도서일 때 그린이 포함" 변형을 비교해 정한다. 다만 연결되지 않은 책은 저자 키에 그린이가 없어 그 변형에 못 들어간다. 그 책들의 비중을 실험에서 함께 본다.
- REST와 tool에 잇지 않는다.

### 9. 기존 데이터 채우기와 다시 만들기

- `scripts/rebuild_contributors.py`(운영자 실행). 한 번 쓰고 버리는 스크립트가 아니다. 저자 키와 기여자는 코드가 저장할 때 계산하므로, 역할 표나 `match_key`를 고치면 기존 행이 옛 규칙으로 남는다. 그때 다시 돌린다.
  - 기본: 모든 공식 서지에 `sync_contributors`, 모든 기관 도서의 `author_keys`를 다시 계산해 다른 행만 고친다. 고친 건수를 출력한다.
  - `--check`: 쓰지 않고 다른 건수만 출력한다(기여자, 저자 키, 맞춰지지 않은 분류기호). 종료 코드는 0이다(차이는 오류가 아니다).
  - 종료 코드 0 완료, 1 전제 조건(DB 연결, 마이그레이션). `enrich_books.py`의 엔진 생성, `check_migrations` 구조를 따른다. 외부 호출이 없어 2는 없다.
- 층: 공식 서지 쪽은 `app/central/contributors.py`, 기관 도서 쪽은 `app/library/services/`의 함수가 맡고 스크립트가 잇는다. 운영자 실행이 기관 테이블에 쓰지만 파생 값만 쓴다(`embed_books.py`와 같은 입장). 훅을 부르지 않는다.
- 마이그레이션 안에서 채우지 않는 이유: 해석 규칙을 마이그레이션에 복사하면 규칙이 바뀔 때 두 벌이 된다. 적용 순서는 `alembic upgrade head && rebuild_contributors.py`다.

### 10. 테스트 고정

- **저장소에 넣는 사례**(`tests/core/test_contributors.py`, `tests/external/test_yes24_contributors.py`): Context에 적은 꼴마다 대표 표기 하나 이상(약 25개)과 기대 결과. 저자 표기 한 줄은 서지 사실이고 소개글이 아니라 저장소에 둔다(이미 스펙에 `앤디 위어 저/박아람 역`이 있다).
- **표본 전체**(`tests/samples/`, 표본이 없으면 건너뜀): 87권 모두에서 ① 기여자가 1명 이상 ② 이름 끝 낱말이 역할 표에 있는 표기와 한 글자 차이로 닮은 꼴(`저`, `역`으로 끝나는 이름 등)이 없다 ③ 역할별 건수가 고정한 값과 같다. 표본을 다시 받으면 ③은 고쳐야 한다.
- 코드와 SQL 일치 테스트의 표본 문자열에 전각, NFD를 더한다.
- 에이전트 동작 시나리오는 없다. `evals/`에 더할 시나리오가 없다.

### 11. 시리즈명

- 규칙만 정한다: 시리즈명끼리는 `match_key`로 맞춘다(스펙 "이름 맞춤 키").
- 저장은 하지 않는다. 지금 `series_name`은 여러 시리즈를 `, `로 이은 문자열이라 다시 나누면 쉼표가 든 시리즈명이 깨진다. 다음 change가 YES24 원본을 파일로 남기면 시리즈가 목록 그대로 있으므로, 시리즈 키 저장은 거기서 정한다(Open Questions 2).

### 12. 풀지 못하는 것

| 문제 | 예 | 지금 결과 | 다룰 곳 |
| --- | --- | --- | --- |
| 다른 음역 | `조앤 K. 롤링` / `J.K. 롤링` / `J.K. Rowling` | 다른 사람 | `add-bibliographic-sources`에서 같은 ISBN의 출처별 기여자를 비교해 얼마나 어긋나는지 잰다 |
| 동명이인 | `김영수` 두 사람 | 같은 사람 | 같은 저자 결과의 오탐으로 잰다 |
| 필명과 본명 | `에반(하상희)` | 키 `에반하상희` 하나 | 건수가 적어 둔다 |
| 단체와 "외" | `편집부`, `EBS`, `정재은 외` | 단체도 한 사람처럼, 나머지 사람은 모름 | `편집부`·`EBS` 같은 키가 책을 과하게 묶는지 실험에서 본다 |
| 쉼표가 든 이름 | `Inc., ABC` | 둘로 나뉨 | 둔다 |

## Risks / Trade-offs

- **[`compact` 변경이 찾기 결과를 바꿀 수 있다]** NFC와 전각만 더하므로 한글·반각 입력의 키는 그대로일 것으로 본다 → 변경 전후로 `uv run python -m evals.catalog_search`를 돌려 1위·5위 안·MRR·오탐을 비교해 보고한다. 표본 87권의 찾기 키가 변경 전후로 같은지도 센다. 달라지면 멈추고 이유를 알린다.
- **[찾기 키 생성 열을 다시 계산한다]** 함수가 바뀌면 `books`·`library_books`의 생성 열 넷을 다시 만들어야 한다(`2026_11_11_0100` 마이그레이션과 같은 방식) → 수백 행이라 금방 끝난다. 적용 전에 개발 DB를 백업한다.
- **[PostgreSQL `normalize()`를 생성 열에 쓸 수 있는가]** 생성 열은 IMMUTABLE 식만 받는다 → 구현 첫 태스크에서 확인한다. 안 되면 `ko_jamo_starts`처럼 IMMUTABLE로 선언한 SQL 함수로 감싼다. DB 인코딩이 UTF8이어야 한다(지금 UTF8).
- **[모델 validator에 규칙이 들어간다]** "로직은 service에" 원칙과 닿는다 → 파생 값 하나를 원문과 묶는 것에 한정한다. 해석 규칙 자체는 `core`의 순수 함수다.
- **[역할 표가 완전하지 않다]** 표본 87권에서 본 표기 위주다 → 표에 없는 끝 낱말은 이름에 붙은 채 남고 표본 전체 테스트와 `--check`가 드러낸다. 500권을 받는 다음 change에서 표를 넓히고 다시 만들기를 돌린다.
- **[기관 파일 해석이 틀릴 수 있다]** 꼴이 자유라 잘못 나눌 수 있다 → 틀려도 원문 `author`는 그대로이고 표시·찾기는 원문을 쓴다. 영향은 "같은 저자" 신호에 그친다.
- **[분류기호 값이 바뀌어 보인다]** `KDC 813.7`로 등록하면 응답이 `813.7`이다 → 스펙에 적는다. 기존 행은 바꾸지 않는다.

## Migration Plan

1. 변경 전 기준 수치: `uv run python -m evals.catalog_search` 결과와 표본의 찾기 키를 남긴다.
2. 개발 DB 백업(`pg_dump`)을 만들고 경로를 알린다.
3. `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`
4. `uv run python scripts/rebuild_contributors.py && uv run python scripts/rebuild_contributors.py --check`(두 번째는 차이 0)
5. 되돌리기: `uv run alembic downgrade -1`(테이블·열 제거, SQL 함수와 생성 열을 이전 정의로). 다른 데이터는 그대로다.

## Open Questions

1. **서명·저자 찾기에도 문장부호 제거를 넣을지.** 추천은 넣지 않는 것(결정 2). 넣으려면 `ko_jamo_starts`와 일치 테스트, 찾기 평가 전후 비교가 이 change에 더해진다(약 반나절).
2. **시리즈 키 저장**(`books.series_keys` 배열)을 `add-official-book-embeddings`에 넣을지 `add-recommendation-experiments`에 넣을지. 추천은 앞쪽(원본 파일을 받는 change에서 목록 그대로 저장).
3. **`editor`를 지은이에 넣을지.** `편저`는 `author`로 읽지만 `엮음`만 있는 책(민담집, 선집)은 저자 키가 빈다. 추천은 그대로 두고 실험에서 빈 키의 비중을 본다.
