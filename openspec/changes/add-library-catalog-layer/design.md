# Design

## Context

**지금 코드에 있는 것**
- `books`는 기관 공통이고 `isbn`, `audience`, `audience_source`, 서지 필드를 가진다. ISBN은 비어 있어도 된다.
- `update_book`, `delete_book`은 `library_id`를 받지 않는다. 어떤 기관 관리자든 공용 도서를 고칠 수 있다.
- `holding_imports._snapshot`은 모든 기관의 ISBN 없는 도서를 읽어 서명·저자로 찾는다. `_fill_book`은 공용 도서의 빈 필드와 대상 구분을 쓴다.
- `create_holding`은 `get_book`으로 어느 기관과도 상관없이 도서를 찾는다.
- `holdings.book_id`가 `books`를 직접 가리키고, 사본·대출 응답이 `holding.book`에서 서명을 읽는다.
- 실제 기관 데이터는 없다. 개발 DB와 시드뿐이다.

**제약**
- YES24 FAQ는 전체 도서 정보를 자체 DB로 축적하는 것을 금지한다. 공식 서지는 소장 도서의 ISBN만 채워야 한다.
- 기관의 파일이 공식 서지에 의존하면 가져오기가 외부 호출을 기다리게 된다. 가져오기는 공식 서지 없이 끝나야 한다.

## Goals / Non-Goals

**Goals:**
- 기관의 쓰기가 다른 기관의 값에 닿는 경로를 없앤다.
- 기관 도서 하나로 서지·어린이 구분·복본을 다뤄서, 사본끼리 값이 어긋나지 않게 한다.
- 사본·대출·이후 에이전트가 같은 표시 규칙을 쓰게 한다.

**Non-Goals:**
- 공식 서지를 채우는 실행. `add-book-enrichment`에서 한다.
- 운영자 계정과 화면. 예외 처리가 실제로 필요해질 때 만든다.
- 서명 표기 차이를 맞추는 정규화.

## Decisions

### 1. 세 층과 소유권

```
books (운영자)  ◀── library_books (기관)  ◀── holdings (기관, 사본)
 ISBN 필수           book_id 비어도 됨          library_book_id 필수
```

- `books`: 서지 사실만 둔다. 기관 API에서 쓸 수 없다.
- `library_books`: "이 도서관의 그 책"이다. 파일에서 온 값, 어린이 구분, ISBN 없는 책이 여기 있다.
- `holdings`: 사본 정보만 둔다. 지금과 같다.
- **대안: `holdings`에 어린이 구분과 기관 값을 직접 둠** → 복본마다 값이 반복된다. 사본끼리 값이 어긋날 수 있고, 관리자 지정을 사본 전체에 쓰고 새 사본이 이어받는 규칙이 필요하다. ISBN 없는 책은 "같은 책"을 묶을 행이 없어서 추천을 책 단위로 할 수 없다.
- **대안: 공용 `books`에 소유 기관 열과 기관 설정 테이블 추가** → 공식 값과 기관 값이 계속 한 테이블에 섞이고, ISBN 없는 책의 수정 권한을 따로 판단해야 한다.
- **대안: `books`를 기관별로 완전 분리** → 격리는 가장 깔끔하지만 같은 ISBN을 기관마다 외부 조회해서 일일 한도와 임베딩 비용이 기관 수만큼 늘어난다.

### 2. 테이블

| 대상 | 변경 |
| --- | --- |
| library_books (새, 기관) | id, library_id, book_id?, isbn?, title, author, publisher?, published_date?, list_price?, kdc?, audience, audience_source, cover_url?, description?, 시각 열 |
| library_books 제약 | UNIQUE(library_id, id), UNIQUE(library_id, isbn), CHECK isbn 형식, CHECK list_price >= 0, book_id FK RESTRICT, book_id 인덱스 |
| holdings | book_id 삭제, library_book_id 추가, 복합 FK (library_id, library_book_id) → library_books (library_id, id) RESTRICT, library_book_id 인덱스 |
| books | isbn NOT NULL, audience·audience_source 삭제 |

`AudienceSource`와 `Audience`는 값 그대로 쓴다. 복합 FK는 `loans`가 쓰는 방식과 같다.

### 3. 표시 값은 모델에서 계산

`LibraryBook`에 `display_title` 같은 속성을 두고 `official.title or self.title` 규칙을 한곳에 둔다. `book` 관계는 joined로 읽는다. 스키마가 이 속성을 읽어서 `LibraryBookRead`, `HoldingRead`, 대출 응답이 같은 값을 낸다. 정렬은 SQL의 `coalesce(books.title, library_books.title)`을 쓴다.
- **대안: DB 뷰** → 자연어 SQL에는 뷰가 필요하지만 그 change의 안전장치 설계와 함께 만든다. 이번에는 ORM 모델이 필요해서 속성이 더 단순하다. 앞서 논의한 뷰는 `add-admin-agent`로 넘긴다.

### 4. 연결과 잠금

- 연결은 ISBN이 정확히 같을 때만 코드로 한다. `link_official(session, library_book)`이 등록, 가져오기, ISBN 수정에서 쓰이고, `add-book-enrichment`도 쓴다.
- 공식 서지에 연결된 도서는 ISBN과 대상 구분만 수정할 수 있다. 서지를 고쳐도 표시 값이 안 바뀌어서, 저장만 되고 안 보이는 혼란을 막기 위해 409로 거부한다.
- ISBN 수정은 항상 허용한다. 잘못 입력된 ISBN으로 다른 책에 연결된 경우의 유일한 탈출구이기 때문이다.
- 기관 값은 연결돼도 지우지 않는다. 연결이 풀리면 다시 쓰인다.

### 5. API 이름

`/books`를 그대로 두지 않고 `/library-books`로 바꾼다. id의 의미가 바뀌므로 같은 경로를 두면 `books` 테이블과 헷갈리고, 예전 id를 쓰는 호출이 다른 행을 조용히 가리킨다. 공식 서지를 읽는 별도 API는 두지 않는다. 기관은 표시 값으로 보면 된다.

### 6. 가져오기

`_snapshot`은 로그인한 기관의 `library_books`만 읽고, 행의 ISBN에 맞는 `books`를 함께 읽는다.
- 도서 찾기, 만들기, 빈 필드 채우기, 어린이 분류 모두 기관 도서에 쓴다.
- 적용은 `books`를 쓰지 않고 외부를 호출하지 않는다.
- 미리 보기의 행별 결과와 제적 처리는 바뀌지 않는다.

### 7. 시드

- `generate_books`의 ISBN 있는 45권을 `books`에 넣는다.
- 기관마다 고른 도서로 `library_books`를 만든다. ISBN이 있으면 공식 서지에 연결하고, ISBN 없는 도서는 기관마다 자기 행을 가진다.
- 어린이 구분은 `library_books`에 둔다. 사본은 `library_book_id`로 잇는다. 반복 실행 안전성은 `(library_id, isbn)`과 서명·저자로 지킨다.

## Risks / Trade-offs

- [변경 범위가 넓음. 테스트에서 `/books`와 `book_id`를 쓰는 곳이 약 100곳] → 대부분 이름 변경이다. 태스크를 층별로 나눠 각 단계에서 해당 테스트를 통과시키고, 일주일을 넘길 것 같으면 알린다.
- [공식 서지가 틀려도 기관이 고칠 수 없음] → 기관은 ISBN을 고쳐 연결을 바꿀 수 있다. YES24 자체가 틀린 경우는 운영자 도구가 생길 때까지 남는다.
- [공식 서지가 없으면 소개·표지가 없음] → 기관 값으로 동작하고, 채움 실행으로 나아진다.
- [공식 서지가 어느 기관도 소장하지 않게 된 뒤 남음] → FAQ의 "필요한 범위" 안에 두려면 정리가 필요하다. 채움 change에서 정한다.
- [기관 값과 공식 값의 서명이 달라 사람이 혼란스러울 수 있음] → 기관 파일의 표기는 대조용으로 남고 화면에는 공식 값이 나온다. 일치시키는 일은 범위 밖이다.

## Migration Plan

리비전 하나로 처리하고, 명령은 `set -eo pipefail`로 실행해 앞 단계가 실패하면 멈춘다.

**upgrade**
1. `library_books`를 만든다.
2. 사본이 있는 (기관, 도서)마다 기존 `books` 값과 어린이 구분을 복사한다. `book_id`는 비워 둔다. 기존 값은 공식 서지가 아니기 때문이다.
3. `holdings.library_book_id`를 채우고 NOT NULL, 복합 FK를 건 뒤 `book_id`를 지운다.
4. `books` 행을 모두 지우고, `isbn` NOT NULL로 바꾸고, 어린이 구분 열을 지운다. 사본이 없던 도서는 여기서 사라진다.

**downgrade**
1. `books`에 어린이 구분 열을 되돌리고 `isbn`을 NULL 허용으로 바꾼다.
2. 기관 도서마다 `books` 행을 찾거나 만든다. ISBN이 있으면 ISBN으로 합치고, ISBN이 없으면 기관 도서마다 새 행을 만든다.
3. `holdings.book_id`를 되살려 채우고 `library_book_id`와 `library_books`를 지운다.

기관별로 달랐던 어린이 구분은 downgrade에서 하나로 합쳐진다. 개발 데이터만 있어서 허용한다.

## 다음 change에 주는 영향

`add-book-enrichment`는 이 구조에 맞춰 다시 쓴다. 호출 코드, 오류 구분, 분류 판단, 이용 조건은 그대로 쓸 수 있다.
- 처리 상태는 `library_books`로 옮긴다. `books` 행은 YES24 조회에 성공해야 생기므로 `not_found`를 둘 곳이 없다.
- `books`의 서지 필드를 YES24 값으로 만든다. "빈 필드만 채움"은 공식 서지를 만들 때는 필요 없어진다.
- `books.author`가 YES24 원문이 되므로 `external_author`는 필요 없다. 파일 값은 `library_books.author`에 남는다.
- 어린이 판단 순서는 기관 도서의 `manual`, `import_label`, 공식 서지의 외부 분류, `default`가 된다.
