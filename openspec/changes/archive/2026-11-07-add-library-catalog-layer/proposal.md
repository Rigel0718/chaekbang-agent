# Proposal

## Why

지금 `books`는 공식 서지와 기관이 올린 값을 한 테이블에 함께 담고 있다. 그래서 어떤 기관 관리자든 공용 도서의 서명이나 어린이 구분을 바꿀 수 있고, 한 기관 파일의 분류가 다른 기관 추천에 영향을 주며, ISBN 없는 기증 도서는 서명·저자가 같으면 기관을 넘어 한 행으로 합쳐진다. 실제 기관 데이터가 없는 지금, YES24 연동과 AI 사서가 이 구조 위에 올라가기 전에 층을 나눈다.

## What Changes

세 층으로 나눈다.

| 층 | 주인 | 내용 |
| --- | --- | --- |
| `books` | 서비스 운영자 | 공식 서지. ISBN이 있는 책만. 기관은 쓸 수 없다 |
| `library_books` (새) | 기관 | 우리 도서관의 책. 기관 값, 어린이 구분, ISBN 없는 책. 공식 서지 연결은 없어도 된다 |
| `holdings` | 기관 | 사본. 기관 도서를 가리킨다 |

- **BREAKING 기관 도서 API**: `/books`를 `/library-books`로 바꾼다. 모두 로그인한 기관 범위이고, 다른 기관의 도서는 404다.
- **BREAKING 사본·대출**: `book_id`를 `library_book_id`로 바꾼다. 사본은 자기 기관의 기관 도서만 가리킬 수 있다.
- **공식 서지 보호**: 기관 API로는 `books`를 쓸 수 없다. `books`는 ISBN이 필수가 되고, 어린이 구분 열이 빠진다.
- **공식 서지 연결**: 기관 도서의 ISBN이 `books`에 있으면 연결한다. 연결된 도서는 공식 값을 먼저 보여 주고, 기관은 서지 필드를 고칠 수 없다. 없으면 기관 값으로 그대로 동작한다.
- **어린이 구분**: 기관 도서로 옮긴다. 기관마다 값이 다를 수 있다.
- **가져오기**: 공식 서지가 없어도 끝나고, 도서 찾기는 기관 안에서만 한다. ISBN 없는 책은 기관을 넘어 합쳐지지 않는다.

**범위 밖 (이번 change에서 하지 않음)**

- 공식 서지를 채우는 일 → `add-book-enrichment`를 이 구조에 맞춰 고친 뒤 진행한다
- 외부 분류 근거 `external_category` → 같은 change
- 운영자 계정, 운영자 화면, 공식 서지 수정 API. 지금은 시드와 이후 채움 실행만 `books`를 쓴다
- 공식 서지 연결을 기관이 끊는 기능
- 자연어 SQL용 DB 뷰 → `add-admin-agent`

## Capabilities

### New Capabilities

- `catalog/library-books`: 기관 도서의 등록·조회·수정·삭제, 공식 서지 연결과 표시 값, 기관별 어린이 구분

### Modified Capabilities

- `catalog/books`: 공식 서지만 남기고 기관이 쓰던 요구사항을 `catalog/library-books`로 옮김
- `catalog/holdings`: 사본이 기관 도서를 가리킴
- `catalog/holdings-import`: 기관 안에서 도서 찾기, 공식 서지 연결, 기관별 분류
- `library/libraries`: 기관 데이터에 기관 도서 추가
- `library/staff-auth`: 키오스크 권한의 도서 경로 변경
- `platform/database-schema`: 테이블 9개, 기관 간 참조 금지에 사본과 기관 도서 추가
- `platform/dev-seed-data`: 공식 서지와 기관 도서 시드

## Impact

- **새 코드**: `app/services/library_books.py`, `app/api/library_books.py`
- **바뀌는 코드**: `app/models/catalog.py`, `app/models/__init__.py`, `app/schemas/catalog.py`, `app/schemas/circulation.py`, `app/services/holdings.py`, `app/services/holding_imports.py`, `app/api/holdings.py`, `app/api/loans.py`, `app/main.py`, `app/seed/catalog.py`
- **지우는 코드**: `app/services/books.py`, `app/api/books.py`
- **API**: `/books` 제거, `/library-books` 추가, 사본·대출의 `book_id`가 `library_book_id`로 바뀜
- **마이그레이션**: `library_books` 생성, 기존 도서 값을 기관 도서로 옮김, `holdings` 참조 교체, `books` 제약 변경. 사본이 없는 기존 도서는 사라진다. 개발 데이터뿐이고 시드로 다시 만들 수 있다.
- **테스트**: 도서·사본·가져오기·시드·스키마 테스트 수정
- **문서**: `CLAUDE.md`(change 순서, 설계 원칙, 용어), `README.md`, `docs/design.md`
- **다음 change**: 이번 change가 끝난 뒤 `add-book-enrichment`를 다시 쓴다
