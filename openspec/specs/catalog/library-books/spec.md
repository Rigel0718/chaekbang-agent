# catalog/library-books Specification

## Purpose

기관이 소장한 책을 기관 범위에서 관리하고, ISBN이 같으면 공식 서지에 연결해 공식 값을 쓰며, 어린이 구분과 ISBN 없는 책은 기관의 값으로 둔다.

## Requirements

### Requirement: 기관 도서 등록
시스템은 ISBN, 제목, 저자, 출판사, 출간일, 정가, 분류기호, 표지 URL, 소개를 받아 기관 도서를 등록 SHALL 한다. 제목과 저자는 필수이고 나머지는 선택이다. ISBN이나 정가가 없는 책도 등록할 수 있다. 정가가 주어지면 0 이상의 정수(원 단위)여야 한다. 정가는 서지정보의 정가이고, 실제 구입가는 사본에 기록한다 (catalog/holdings "입수 구분"). 기관 도서는 로그인한 기관에 속하고, 등록은 관리자만 할 수 있다. 기관 도서는 시스템이 부여하는 내부 id로 식별한다.

#### Scenario: 정상 등록
- **WHEN** 관리자가 유효한 ISBN과 필수 필드로 `POST /library-books`를 호출하면
- **THEN** 시스템은 201과 함께 내부 id가 붙은 도서 정보를 반환한다

#### Scenario: ISBN 없이 등록
- **WHEN** 관리자가 ISBN 없이 제목·저자·정가만으로 `POST /library-books`를 호출하면
- **THEN** 시스템은 201과 함께 ISBN이 비어 있는 도서를 반환한다

#### Scenario: 정가 없이 등록
- **WHEN** 관리자가 정가 없이 ISBN·제목·저자로 `POST /library-books`를 호출하면
- **THEN** 시스템은 201과 함께 정가가 비어 있는 도서를 반환한다

#### Scenario: 필수 필드 누락
- **WHEN** 제목이 빠진 요청으로 `POST /library-books`를 호출하면
- **THEN** 시스템은 422를 반환하고 도서를 저장하지 않는다

#### Scenario: 정가가 정수가 아님
- **WHEN** 정가가 음수이거나 소수인 요청으로 `POST /library-books`를 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 형식 정규화와 검증
ISBN이 주어지면 시스템은 하이픈·공백 없는 13자리 숫자 문자열로 정규화해 저장 MUST 한다. 하이픈이 포함된 입력은 받아서 정규화하고, 정규화 후 13자리 숫자가 아니거나 ISBN-13 체크 디지트가 맞지 않으면 거부한다. ISBN으로 도서를 찾을 때도 같은 정규화를 거친다.

#### Scenario: 하이픈 포함 입력
- **WHEN** ISBN `978-0-306-40615-7`로 도서를 등록하면
- **THEN** 시스템은 `9780306406157`로 저장하고 응답한다

#### Scenario: 하이픈 포함 ISBN으로 조회
- **WHEN** `9780306406157` 도서가 있는 상태에서 `GET /library-books?isbn=978-0-306-40615-7`을 호출하면
- **THEN** 시스템은 그 도서 하나만 담긴 목록을 반환한다

#### Scenario: 자릿수 오류
- **WHEN** 10자리 ISBN이나 숫자가 아닌 문자가 섞인 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 체크 디지트 오류
- **WHEN** 13자리 숫자이지만 체크 디지트가 틀린 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 중복 금지
시스템은 한 기관 안에서 같은 ISBN의 기관 도서를 두 번 등록할 수 없게 MUST 한다. 다른 기관은 같은 ISBN을 등록할 수 있다. ISBN이 없는 기관 도서는 여러 권 있을 수 있다.

#### Scenario: 중복 등록
- **WHEN** 이미 등록된 ISBN으로 `POST /library-books`를 다시 호출하면
- **THEN** 시스템은 409를 반환하고 기존 도서는 바뀌지 않는다

#### Scenario: 다른 기관의 같은 ISBN
- **WHEN** A 기관이 등록한 ISBN으로 B 기관 관리자가 `POST /library-books`를 호출하면
- **THEN** 201로 등록되고 두 기관의 도서는 서로 다른 id다

#### Scenario: ISBN 없는 도서 여러 권
- **WHEN** ISBN 없이 도서 두 권을 등록하면
- **THEN** 두 도서가 서로 다른 id로 모두 저장된다

### Requirement: 기관 도서 저장 제약
API를 거치지 않은 쓰기에도 기관 도서 규칙이 지켜지도록, 저장 계층은 13자리 숫자가 아닌 ISBN, 같은 기관의 중복 ISBN, 음수 정가를 MUST 거부한다. ISBN과 정가가 비어 있는 것은 허용한다. 사본이 참조하는 기관 도서 행의 삭제도 저장 계층에서 거부한다.

#### Scenario: 잘못된 ISBN 직접 저장
- **WHEN** library_books에 ISBN `978-0306406157`(하이픈 포함)을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 같은 기관의 중복 ISBN 직접 저장
- **WHEN** 같은 기관에 이미 있는 ISBN으로 library_books에 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 음수 정가 직접 저장
- **WHEN** library_books에 정가 -1000으로 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 참조된 기관 도서 직접 삭제
- **WHEN** holdings가 참조하는 library_books 행을 DB에서 직접 삭제하려 하면
- **THEN** 데이터베이스가 삭제를 거부한다

### Requirement: 기관 도서 단건과 목록 조회
시스템은 내부 id로 단건 조회와 페이지 단위 목록 조회를 SHALL 제공하고, 로그인한 기관의 기관 도서만 돌려준다.
- 목록은 `limit`(기본 20, 최대 100)과 `offset`을 받고, 전체 건수를 함께 반환한다.
- 목록은 `isbn`과 대상 구분으로 거를 수 있다.
- 각 도서에는 소장 권수와 대출 가능 권수를 붙인다. 제적 사본은 세지 않는다.
- `held=true`로 제적이 아닌 사본이 있는 도서만 거를 수 있다.

#### Scenario: 단건 조회
- **WHEN** 등록된 기관 도서의 id로 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 200과 도서 정보를 반환한다

#### Scenario: 없는 도서 조회
- **WHEN** 없는 id로 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 다른 기관 도서 조회
- **WHEN** B 기관의 기관 도서 id로 A 기관 직원이 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 목록에 다른 기관 도서 없음
- **WHEN** 두 기관에 기관 도서가 있고 A 기관 직원이 `GET /library-books`를 호출하면
- **THEN** A 기관의 도서만 돌려준다

#### Scenario: 목록 페이지네이션
- **WHEN** 기관 도서 25권이 있는 상태에서 `GET /library-books?limit=10&offset=20`을 호출하면
- **THEN** 시스템은 5건의 항목과 전체 건수 25를 반환한다

#### Scenario: limit 상한 초과
- **WHEN** `GET /library-books?limit=101`을 호출하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 없는 ISBN으로 거르기
- **WHEN** 등록되지 않은 ISBN으로 `GET /library-books?isbn={isbn}`을 호출하면
- **THEN** 시스템은 200과 빈 목록, 전체 건수 0을 반환한다

#### Scenario: 소장 권수
- **WHEN** 사본 2권(그중 1권 대출 중)이 있는 기관 도서를 조회하면
- **THEN** 소장 권수 2, 대출 가능 권수 1을 돌려준다

#### Scenario: 소장 도서만 거르기
- **WHEN** `GET /library-books?held=true`를 호출하면
- **THEN** 제적이 아닌 사본이 하나 이상 있는 기관 도서만 돌려준다

#### Scenario: 제적 사본은 소장이 아님
- **WHEN** 제적 사본만 있는 기관 도서를 `GET /library-books?held=true`로 조회하면
- **THEN** 그 도서는 들어 있지 않고, 단건 조회의 소장 권수는 0이다

### Requirement: 공식 서지 연결
시스템은 기관 도서를 만들거나 ISBN이 바뀔 때 같은 ISBN의 공식 서지가 있으면 MUST 연결한다. 없으면 연결 없이 저장하고, 기관 도서는 기관 값으로 그대로 동작한다. 응답의 `book_id`로 연결 여부를 알 수 있다.

#### Scenario: 공식 서지가 있는 ISBN
- **WHEN** 공식 서지에 있는 ISBN으로 기관 도서를 등록하면
- **THEN** 응답의 `book_id`가 그 공식 서지를 가리킨다

#### Scenario: 공식 서지가 없는 ISBN
- **WHEN** 공식 서지에 없는 ISBN으로 기관 도서를 등록하면
- **THEN** `book_id`는 비어 있고 입력한 값으로 조회된다

#### Scenario: ISBN 없는 도서
- **WHEN** ISBN 없이 기관 도서를 등록하면
- **THEN** `book_id`는 비어 있다

### Requirement: 표시 값
시스템은 조회 응답의 서지 필드에 연결된 공식 서지의 값을 먼저 MUST 쓴다. 공식 값이 비어 있는 필드와 연결이 없는 도서는 기관 값을 쓴다. 사본과 대출 응답의 서명·저자도 같은 규칙을 따른다.

#### Scenario: 공식 값 우선
- **WHEN** 기관 값 서명 `클린코드`인 기관 도서가 서명 `클린 코드`인 공식 서지에 연결돼 있으면
- **THEN** 조회 응답의 서명은 `클린 코드`다

#### Scenario: 공식 값이 빈 필드
- **WHEN** 공식 서지의 출판사가 비어 있고 기관 값 출판사가 있으면
- **THEN** 조회 응답의 출판사는 기관 값이다

#### Scenario: 사본 응답의 서명
- **WHEN** 연결된 기관 도서의 사본을 조회하면
- **THEN** 사본 응답의 서명은 공식 서지의 값이다

### Requirement: 기관 도서 부분 수정
관리자는 자기 기관의 기관 도서를 부분 수정할 수 있어야 SHALL 한다. 요청에 포함된 필드만 바뀐다. 공식 서지에 연결된 도서는 ISBN과 대상 구분만 고칠 수 있고, 그 밖의 서지 필드를 보내면 409를 돌려준다. ISBN을 고치면 등록과 같은 정규화·검증·중복 규칙을 따르고 공식 서지 연결을 다시 정한다. 매입·납품 사본이 있는 도서는 ISBN을 비울 수 없다.

#### Scenario: 정가 수정
- **WHEN** 연결이 없는 기관 도서에 `PATCH /library-books/{id}`로 정가만 담아 호출하면
- **THEN** 시스템은 정가만 바꾸고 나머지 필드는 그대로 둔 도서 정보를 반환한다

#### Scenario: 연결된 도서의 서지 수정
- **WHEN** 공식 서지에 연결된 기관 도서에 `PATCH /library-books/{id}`로 서명을 보내면
- **THEN** 시스템은 409를 반환하고 값은 바뀌지 않는다

#### Scenario: ISBN 나중에 채우기
- **WHEN** ISBN이 없는 기관 도서에 `PATCH /library-books/{id}`로 공식 서지에 있는 ISBN을 보내면
- **THEN** 정규화된 ISBN이 저장되고 그 공식 서지에 연결된다

#### Scenario: 잘못 연결된 ISBN 고치기
- **WHEN** 연결된 기관 도서의 ISBN을 공식 서지에 없는 값으로 고치면
- **THEN** ISBN이 바뀌고 연결이 비워진다

#### Scenario: 다른 도서의 ISBN으로 수정
- **WHEN** 같은 기관의 다른 도서가 쓰는 ISBN으로 `PATCH /library-books/{id}`를 호출하면
- **THEN** 시스템은 409를 반환하고 도서는 바뀌지 않는다

#### Scenario: 매입 사본이 있는 도서의 ISBN 비우기
- **WHEN** 매입·납품 사본이 있는 기관 도서에 `PATCH /library-books/{id}`로 ISBN을 비우려 하면
- **THEN** 시스템은 409를 반환하고 ISBN은 그대로 남는다

#### Scenario: 없는 도서 수정
- **WHEN** 없는 id로 `PATCH /library-books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 다른 기관 도서 수정
- **WHEN** B 기관의 기관 도서를 A 기관 관리자가 `PATCH /library-books/{id}`로 고치려 하면
- **THEN** 시스템은 404를 반환하고 도서는 바뀌지 않는다

### Requirement: 소장 사본이 있는 도서의 삭제 금지
관리자는 자기 기관의 기관 도서를 삭제할 수 있어야 SHALL 한다. 단, 제적 사본을 포함해 사본이 있는 도서는 삭제를 거부 MUST 한다. 공식 서지는 함께 지워지지 않는다.

#### Scenario: 참조 없는 도서 삭제
- **WHEN** 사본이 없는 기관 도서에 `DELETE /library-books/{id}`를 호출하면
- **THEN** 시스템은 204를 반환하고 이후 조회 시 404가 된다

#### Scenario: 사본이 있는 도서 삭제
- **WHEN** 사본이 있는 기관 도서에 `DELETE /library-books/{id}`를 호출하면
- **THEN** 시스템은 409를 반환하고 도서를 삭제하지 않는다

#### Scenario: 다른 기관 도서 삭제
- **WHEN** B 기관의 기관 도서를 A 기관 관리자가 삭제하려 하면
- **THEN** 시스템은 404를 반환한다

### Requirement: 어린이/일반 도서 구분
시스템은 기관 도서마다 대상 구분(`audience`)과 그 근거(`audience_source`)를 SHALL 보관한다. 같은 ISBN이라도 기관마다 값이 다를 수 있다.
- 대상 구분: `children`(어린이 도서) 또는 `general`(일반 도서). 기본값은 `general`이다.
- 근거: `default`(근거 없음, 기본값), `manual`(관리자 지정), `import_label`(가져온 파일의 별치기호·자료실·부가기호)
- 근거의 우선순위는 `manual`, `import_label`, `default` 순이다. 낮은 근거는 높은 근거의 값을 바꾸지 않는다.
- 관리자가 대상 구분을 지정하면 근거는 `manual`이 된다.
- 목록 조회는 대상 구분으로 거를 수 있다.

#### Scenario: 기본값
- **WHEN** 대상 구분 없이 도서를 등록하면
- **THEN** 대상 구분 `general`, 근거 `default`로 저장된다

#### Scenario: 관리자 지정
- **WHEN** 관리자가 `PATCH /library-books/{id}`로 대상 구분을 `children`으로 바꾸면
- **THEN** 대상 구분은 `children`, 근거는 `manual`이 된다

#### Scenario: 어린이 도서만 거르기
- **WHEN** `GET /library-books?audience=children`을 호출하면
- **THEN** 대상 구분이 `children`인 도서만 돌려준다

#### Scenario: 기관별 구분
- **WHEN** 같은 ISBN의 기관 도서를 A 기관 관리자가 `children`으로 지정하면
- **THEN** B 기관 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 허용되지 않은 구분
- **WHEN** library_books에 대상 구분 `teen`으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
