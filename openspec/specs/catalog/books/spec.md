# catalog/books Specification

## Purpose

여러 작은도서관이 함께 쓰는 도서의 서지 정보를 보관하고(ISBN이 없는 책 포함), REST API와 이후 에이전트 tool이 같은 규칙으로 조회·관리할 수 있게 한다.

## Requirements

### Requirement: 도서 등록
시스템은 ISBN, 제목, 저자, 출판사, 출간일, 정가, 분류기호, 표지 URL, 소개를 받아 도서를 등록 SHALL 한다. 제목과 저자는 필수이고 나머지는 선택이다. ISBN이나 정가가 없는 책도 등록할 수 있다. 정가가 주어지면 0 이상의 정수(원 단위)여야 한다. 정가는 서지정보의 정가이고, 실제 구입가는 사본에 기록한다 (catalog/holdings "입수 구분"). 도서는 기관 공통 서지정보이고, 등록은 관리자만 할 수 있다. 도서는 시스템이 부여하는 내부 id로 식별한다.

#### Scenario: 정상 등록
- **WHEN** 관리자가 유효한 ISBN과 필수 필드로 `POST /books`를 호출하면
- **THEN** 시스템은 201과 함께 내부 id가 붙은 도서 정보를 반환한다

#### Scenario: ISBN 없이 등록
- **WHEN** 관리자가 ISBN 없이 제목·저자·정가만으로 `POST /books`를 호출하면
- **THEN** 시스템은 201과 함께 ISBN이 비어 있는 도서를 반환한다

#### Scenario: 정가 없이 등록
- **WHEN** 관리자가 정가 없이 ISBN·제목·저자로 `POST /books`를 호출하면
- **THEN** 시스템은 201과 함께 정가가 비어 있는 도서를 반환한다

#### Scenario: 필수 필드 누락
- **WHEN** 제목이 빠진 요청으로 `POST /books`를 호출하면
- **THEN** 시스템은 422를 반환하고 도서를 저장하지 않는다

#### Scenario: 정가가 정수가 아님
- **WHEN** 정가가 음수이거나 소수인 요청으로 `POST /books`를 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 형식 정규화와 검증
ISBN이 주어지면 시스템은 하이픈·공백 없는 13자리 숫자 문자열로 정규화해 저장 MUST 한다. 하이픈이 포함된 입력은 받아서 정규화하고, 정규화 후 13자리 숫자가 아니거나 ISBN-13 체크 디지트가 맞지 않으면 거부한다. ISBN으로 도서를 찾을 때도 같은 정규화를 거친다.

#### Scenario: 하이픈 포함 입력
- **WHEN** ISBN `978-0-306-40615-7`로 도서를 등록하면
- **THEN** 시스템은 `9780306406157`로 저장하고 응답한다

#### Scenario: 하이픈 포함 ISBN으로 조회
- **WHEN** `9780306406157` 도서가 있는 상태에서 `GET /books?isbn=978-0-306-40615-7`을 호출하면
- **THEN** 시스템은 그 도서 하나만 담긴 목록을 반환한다

#### Scenario: 자릿수 오류
- **WHEN** 10자리 ISBN이나 숫자가 아닌 문자가 섞인 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 체크 디지트 오류
- **WHEN** 13자리 숫자이지만 체크 디지트가 틀린 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 중복 금지
시스템은 같은 ISBN의 도서를 두 번 등록할 수 없게 MUST 한다. ISBN이 없는 도서는 여러 권 있을 수 있다.

#### Scenario: 중복 등록
- **WHEN** 이미 등록된 ISBN으로 `POST /books`를 다시 호출하면
- **THEN** 시스템은 409를 반환하고 기존 도서는 바뀌지 않는다

#### Scenario: ISBN 없는 도서 여러 권
- **WHEN** ISBN 없이 도서 두 권을 등록하면
- **THEN** 두 도서가 서로 다른 id로 모두 저장된다

### Requirement: 도서 저장 제약
API를 거치지 않은 쓰기에도 도서 데이터 규칙이 지켜지도록, 저장 계층은 13자리 숫자가 아닌 ISBN, 중복 ISBN, 음수 정가를 MUST 거부한다. ISBN과 정가가 비어 있는 것은 허용한다. 사본이 참조하는 도서 행의 삭제도 저장 계층에서 거부한다.

#### Scenario: 잘못된 ISBN 직접 저장
- **WHEN** books에 ISBN `978-0306406157`(하이픈 포함)을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 중복 ISBN 직접 저장
- **WHEN** 이미 있는 ISBN으로 books에 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 음수 정가 직접 저장
- **WHEN** books에 정가 -1000으로 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 참조된 도서 직접 삭제
- **WHEN** holdings가 참조하는 books 행을 DB에서 직접 삭제하려 하면
- **THEN** 데이터베이스가 삭제를 거부한다

### Requirement: 도서 단건과 목록 조회
시스템은 내부 id로 단건 조회와, 페이지 단위 목록 조회를 SHALL 제공한다.
- 목록은 `limit`(기본 20, 최대 100)과 `offset`을 받고, 전체 건수를 함께 반환한다.
- 목록은 `isbn`으로 거를 수 있다.
- 각 도서에는 로그인한 기관의 소장 권수와 대출 가능 권수를 붙인다. 제적 사본은 세지 않는다.
- `held=true`로 로그인한 기관이 소장한 도서만 거를 수 있다. 제적 사본만 있는 도서는 소장 도서가 아니다.

#### Scenario: 단건 조회
- **WHEN** 등록된 도서의 id로 `GET /books/{id}`를 호출하면
- **THEN** 시스템은 200과 도서 정보를 반환한다

#### Scenario: 없는 도서 조회
- **WHEN** 없는 id로 `GET /books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 목록 페이지네이션
- **WHEN** 도서 25권이 있는 상태에서 `GET /books?limit=10&offset=20`을 호출하면
- **THEN** 시스템은 5건의 항목과 전체 건수 25를 반환한다

#### Scenario: limit 상한 초과
- **WHEN** `GET /books?limit=101`을 호출하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 없는 ISBN으로 거르기
- **WHEN** 등록되지 않은 ISBN으로 `GET /books?isbn={isbn}`을 호출하면
- **THEN** 시스템은 200과 빈 목록, 전체 건수 0을 반환한다

#### Scenario: 기관별 소장 권수
- **WHEN** A 기관에 사본 2권(그중 1권 대출 중), B 기관에 사본 3권인 도서를 A 기관 직원이 조회하면
- **THEN** 소장 권수 2, 대출 가능 권수 1을 돌려준다

#### Scenario: 소장 도서만 거르기
- **WHEN** A 기관 직원이 `GET /books?held=true`를 호출하면
- **THEN** A 기관에 사본이 하나 이상 있는 도서만 돌려준다

#### Scenario: 제적 사본은 소장이 아님
- **WHEN** A 기관에 제적 사본만 있는 도서를 A 기관 직원이 `GET /books?held=true`로 조회하면
- **THEN** 그 도서는 들어 있지 않고, 단건 조회의 소장 권수는 0이다

### Requirement: 도서 부분 수정
관리자는 도서 필드를 부분 수정할 수 있어야 SHALL 한다. 요청에 포함된 필드만 바뀐다. ISBN도 수정할 수 있고, 이때 등록과 같은 정규화·검증·중복 규칙을 따른다. 어느 기관이든 매입·납품 사본이 있는 도서는 ISBN을 비울 수 없다.

#### Scenario: 정가 수정
- **WHEN** `PATCH /books/{id}`에 정가만 담아 호출하면
- **THEN** 시스템은 정가만 바꾸고 나머지 필드는 그대로 둔 도서 정보를 반환한다

#### Scenario: ISBN 나중에 채우기
- **WHEN** ISBN이 없는 도서에 `PATCH /books/{id}`로 유효한 ISBN을 보내면
- **THEN** 정규화된 ISBN이 저장된다

#### Scenario: 다른 도서의 ISBN으로 수정
- **WHEN** 다른 도서가 이미 쓰는 ISBN으로 `PATCH /books/{id}`를 호출하면
- **THEN** 시스템은 409를 반환하고 도서는 바뀌지 않는다

#### Scenario: 매입 사본이 있는 도서의 ISBN 비우기
- **WHEN** 매입·납품 사본이 있는 도서에 `PATCH /books/{id}`로 ISBN을 비우려 하면
- **THEN** 시스템은 409를 반환하고 ISBN은 그대로 남는다

#### Scenario: 없는 도서 수정
- **WHEN** 없는 id로 `PATCH /books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

### Requirement: 소장 사본이 있는 도서의 삭제 금지
관리자는 도서를 삭제할 수 있어야 SHALL 한다. 단, 어느 기관이든 사본이 있는 도서는 삭제를 거부 MUST 한다.

#### Scenario: 참조 없는 도서 삭제
- **WHEN** 사본이 없는 도서에 `DELETE /books/{id}`를 호출하면
- **THEN** 시스템은 204를 반환하고 이후 조회 시 404가 된다

#### Scenario: 사본이 있는 도서 삭제
- **WHEN** 다른 기관에만 사본이 있는 도서에 `DELETE /books/{id}`를 호출하면
- **THEN** 시스템은 409를 반환하고 도서를 삭제하지 않는다

### Requirement: 어린이/일반 도서 구분
시스템은 도서마다 대상 구분(`audience`)과 그 근거(`audience_source`)를 SHALL 보관한다.
- 대상 구분: `children`(어린이 도서) 또는 `general`(일반 도서). 기본값은 `general`이다.
- 근거: `default`(근거 없음, 기본값), `manual`(관리자 지정), `import_label`(가져온 파일의 별치기호·자료실·부가기호)
- 근거의 우선순위는 `manual`, `import_label`, `default` 순이다. 낮은 근거는 높은 근거의 값을 바꾸지 않는다.
- 관리자가 대상 구분을 지정하면 근거는 `manual`이 된다.
- 목록 조회는 대상 구분으로 거를 수 있다.

#### Scenario: 기본값
- **WHEN** 대상 구분 없이 도서를 등록하면
- **THEN** 대상 구분 `general`, 근거 `default`로 저장된다

#### Scenario: 관리자 지정
- **WHEN** 관리자가 `PATCH /books/{id}`로 대상 구분을 `children`으로 바꾸면
- **THEN** 대상 구분은 `children`, 근거는 `manual`이 된다

#### Scenario: 어린이 도서만 거르기
- **WHEN** `GET /books?audience=children`을 호출하면
- **THEN** 대상 구분이 `children`인 도서만 돌려준다

#### Scenario: 허용되지 않은 구분
- **WHEN** books에 대상 구분 `teen`으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
