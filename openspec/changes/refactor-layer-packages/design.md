# Design

## Context

**지금 코드에 있는 것**
- `app/`은 `api`, `services`, `models`, `schemas`, `importing`, `external`, `seed`, `core`로 나뉜다.
- `core/deps.py`가 `models.library`를 import한다. 공용 기반이 기관 모델에 의존한다.
- `services/book_enrichment.py`(운영자)가 `LibraryBook`, `Holding`을 직접 읽고 쓰고, `connect_official`을 부른다.
- 어린이 구분이 공통 코드 8개 파일에 있다: `library_books.audience` 열, `importing/rows.py`의 `children`, `holding_imports._fill_book`, `apply_official`, 목록의 `audience` 필터, 등록·수정 스키마, 시드, API.
- 평가 `evals/holdings_import/`는 `ParsedRow.children`을 읽는다.

**제약**
- 판단 결과는 바뀌면 안 된다. 기존 어린이 시나리오는 경로와 저장 위치만 바뀌어 그대로 지켜야 한다.
- 실제 기관 데이터는 없고 API를 쓰는 화면도 아직 없다.

## Goals / Non-Goals

**Goals:**
- 층 경계를 패키지로 드러내고 테스트로 강제한다.
- 어린이 기능을 등록하지 않아도 공통이 동작하게 한다.
- 파일 이동과 동작 변경을 나눠서, 이동 단계에서는 기존 테스트가 그대로 안전망이 되게 한다.

**Non-Goals:**
- 기관별 기능 켜기·끄기 설정. 등록 여부는 지금 앱 전체 단위다.
- 범용 플러그인 구조. 훅은 지금 필요한 두 가지만 둔다.

## Decisions

### 1. 패키지 구조

```
app/
├── main.py            # 조립: 라우터 포함, 기능 등록
├── models.py          # 조립: 모든 모델 등록, Base, 테이블 구분 (Alembic·테스트용)
├── core/              # 설정, DB, 시각, ISBN, 보안, Base, 공용 오류, 페이지 스키마
├── central/           # 운영자 층
│   ├── models.py      # Book, ExternalSource
│   ├── enrichment.py  # 채움 실행, 접점(EnrichmentTargets)
│   └── external/yes24/
├── library/           # 기관 공통
│   ├── models/        # library(기관·직원·세션), catalog(기관 도서·사본·가져오기), circulation
│   ├── api/  services/  schemas/  importing/
│   ├── deps.py        # 현재 직원·기관, 역할
│   ├── hooks.py       # 기관 개별 기능 접점
│   └── enrichment_targets.py  # central 접점 구현, 처리 현황
├── features/
│   └── children/      # models, rules, service, schemas, api, hook
└── seed/              # 조립: 시드
```

`app/api`처럼 기술별 폴더는 `library` 안에 그대로 두어 이동량을 줄인다. "라우터는 얇게, 로직은 service에" 원칙은 각 패키지 안에서 그대로 지킨다.

`core`로 옮기는 것: `models/base.py`, `services/errors.py`, `services/tenancy.py`, `schemas/common.py`. 어느 층이든 쓰기 때문이다. `core/deps.py`는 기관 모델이 필요해서 `library/deps.py`로 옮긴다.

**대안: 층마다 얇은 패키지 없이 지금 구조 유지하고 import 규칙만 검사** → 경계가 폴더에 보이지 않아서 같은 실수가 반복된다.

### 2. 의존 방향 강제

`tests/platform/test_package_layers.py`가 `ast`로 `app/` 전체의 import를 읽어 표와 대조한다. 외부 도구를 더하지 않는다.

| 패키지 | 금지 |
| --- | --- |
| `app/core` | `central`, `library`, `features` |
| `app/central` | `library`, `features` |
| `app/library` | `features` |

조립하는 곳(`main.py`, `models.py`, `seed/`, `scripts/`, `evals/`)은 검사하지 않는다.

### 3. 운영자 실행의 접점

`central`은 기관 모델 없이 동작해야 한다. `central/enrichment.py`에 `Protocol`을 둔다.

```python
class EnrichmentTargets(Protocol):
    async def isbns(self, limit: int, retry_failed: bool) -> list[str]: ...
    async def remaining(self) -> int: ...
    async def link(self, isbn: str, book: Book) -> None: ...
    async def mark(self, isbn: str, outcome: LookupOutcome) -> None: ...
```

`library/enrichment_targets.py`가 이것을 구현하고 `scripts/enrich_books.py`가 넘긴다. `Book`은 `central` 소유이고 `library`가 참조하므로 방향이 맞다. `LibraryBook.book_id → books.id` FK도 같은 방향이다.

**대안: 채움 실행을 `library`로 옮김** → `central`의 역할이 비고, 운영자 실행이 기관 층 코드가 된다.

### 4. 어린이 구분 저장

`library_book_audiences` (기관 데이터):

| 열 | 내용 |
| --- | --- |
| library_id, library_book_id | 복합 PK. 복합 FK → library_books (library_id, id), ON DELETE CASCADE |
| audience | `children`, `general` |
| audience_source | `manual`, `import_label`, `external_category` |
| 시각 열 | |

- 행이 없으면 `general`, `default`다. `default`는 저장하지 않아서 어린이 기능을 쓰지 않는 기관은 행이 0건이다.
- CASCADE라서 공통의 삭제 코드가 이 테이블을 몰라도 된다.
- 저장 전 `None` 근거 문제가 사라진다. 기관 도서를 먼저 flush하고 훅을 부르기 때문이다.

### 5. 훅

`library/hooks.py`에 공통이 알리는 두 사건만 둔다.

```python
class LibraryBookHook(Protocol):
    async def official_changed(self, session, library_book) -> None: ...
    async def row_applied(self, session, library_book, row) -> None: ...
```

- `official_changed`: 기관의 요청으로 연결이 정해질 때. 등록, ISBN 수정, 가져오기의 새 도서.
- `row_applied`: 가져오기 행을 적용한 뒤. 행에는 파일 값이 들어 있다.
- `register_hook()`은 `app/main.py`의 조립에서 부른다. 테스트는 등록을 비울 수 있다.
- 운영자 실행의 연결(`EnrichmentTargets.link`)은 훅을 부르지 않는다. 그래서 운영자 실행이 어린이 구분을 바꿀 수 없다.
- 가져오기 적용은 지금 동기 흐름이라, 행을 반영한 뒤 flush하고 새 도서의 `official_changed`, 행마다 `row_applied` 순서로 부른다. 파일 근거가 외부 근거 위에 놓이는 순서를 유지한다.

**대안: SQLAlchemy 이벤트** → 운영자 실행의 연결까지 잡히고, 비동기 세션 안에서 쓰기 어렵다.

### 6. 파일 값

`ParsedRow.children`을 없애고 `separate_mark`, `addition_code`를 파일 값으로 둔다. 판단은 `features/children/rules.py`로 옮긴다. `app/importing/classify.py`의 규칙이 여기로 온다. 행은 `holding_imports.rows`에 저장되므로 이미 만든 미리 보기에는 이 키가 없을 수 있어 `.get`으로 읽는다.

머리글 인식 표(`columns.py`)의 별치기호·부가기호 열은 공통에 남는다. 파일 열의 인식은 공통의 일이고, 뜻을 해석하는 것만 기능의 일이다.

### 7. API

| 지금 | 바뀐 뒤 |
| --- | --- |
| `POST·PATCH /library-books`의 `audience` | 제거. `PUT /children/books/{id}` |
| 조회 응답의 `audience`, `audience_source` | 제거. `GET /children/books/{id}` |
| `GET /library-books?audience=children` | 제거. `GET /children/books` |
| `POST /library-books/audience/refresh` | `POST /children/refresh` |

- 기능을 빼도 공통 API가 그대로이려면 응답에도 어린이 값이 없어야 한다.
- 어린이 목록은 `list_library_books`에 기관 도서 id 조건을 받는 일반 인자를 더해서 응답 모양을 같게 한다.
- AI 사서의 어린이 필터는 `features/children`의 함수를 쓰게 된다.

### 8. 진행 순서

한 change지만 두 단계로 나눈다. 1단계는 파일 이동뿐이라 기존 테스트 489개가 그대로 안전망이 된다. 이동이 끝나 통과한 뒤에 2단계에서 동작을 바꾼다.

## Risks / Trade-offs

- [change가 큼. 파일 이동과 어린이 분리를 함께 함] → 단계를 나눠 각 단계에서 전체 테스트를 통과시킨다. 일주일을 넘길 것 같으면 2단계를 별도 change로 나눈다.
- [훅 구조가 기능 하나에 비해 큼] → 사건 두 개만 둔다. 사용자가 정한 방향이고, 크면 나중에 줄인다.
- [공통 응답에 어린이 값이 없어 화면이 호출을 더 해야 함] → `GET /children/books`로 어린이 도서를 한 번에 받는다. 한 권씩 필요하면 그때 묶음 조회를 더한다.
- [훅 등록을 잊으면 어린이 구분이 조용히 멈춤] → `app/main.py` 조립을 기준으로 어린이 테스트가 앱을 통해 돈다. 등록이 빠지면 테스트가 실패한다.
- [`app/seed`가 어린이 저장소를 직접 씀] → 시드는 조립하는 곳이라 허용한다.

## Migration Plan

1. 리비전을 손으로 작성한다. `library_book_audiences`를 만든다.
2. 근거가 `default`가 아닌 행을 옮긴다.
3. `library_books.audience`, `audience_source`를 지운다.
4. downgrade는 열을 되살리고 값을 되돌린 뒤 테이블을 지운다.
5. 작업 전에 개발 DB를 백업하고, 각 단계를 `&&`로 잇고 사이에 파이프를 넣지 않는다.
