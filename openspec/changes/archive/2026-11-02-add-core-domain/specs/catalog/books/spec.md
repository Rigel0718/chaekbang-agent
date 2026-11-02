# Spec Delta

## Purpose

책방이 다루는 도서의 서지 정보를 ISBN 기준으로 보관하고, REST API와 이후 에이전트 tool이 같은 규칙으로 조회·관리할 수 있게 한다.

## ADDED Requirements

### Requirement: 도서 등록
시스템은 ISBN, 제목, 저자, 출판사, 출간일, 정가, 표지 URL, 소개를 받아 도서를 등록 SHALL 한다. ISBN, 제목, 저자, 정가는 필수이고 나머지는 선택이다. 정가는 0 이상의 정수(원 단위)여야 한다.

#### Scenario: 정상 등록
- **WHEN** 클라이언트가 유효한 ISBN과 필수 필드로 `POST /books`를 호출하면
- **THEN** 시스템은 201과 함께 저장된 도서 정보를 반환한다

#### Scenario: 필수 필드 누락
- **WHEN** 제목이 빠진 요청으로 `POST /books`를 호출하면
- **THEN** 시스템은 422를 반환하고 도서를 저장하지 않는다

#### Scenario: 정가가 정수가 아님
- **WHEN** 정가가 음수이거나 소수인 요청으로 `POST /books`를 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 형식 정규화와 검증
시스템은 ISBN을 하이픈·공백 없는 13자리 숫자 문자열로 정규화해 저장 MUST 한다. 하이픈이 포함된 입력은 받아서 정규화하고, 정규화 후 13자리 숫자가 아니거나 ISBN-13 체크 디지트가 맞지 않으면 거부한다.

#### Scenario: 하이픈 포함 입력
- **WHEN** ISBN `978-0-306-40615-7`로 도서를 등록하면
- **THEN** 시스템은 `9780306406157`로 저장하고 응답한다

#### Scenario: 하이픈 포함 ISBN으로 조회
- **WHEN** `9780306406157` 도서가 있는 상태에서 `GET /books/978-0-306-40615-7`을 호출하면
- **THEN** 시스템은 같은 도서를 반환한다

#### Scenario: 자릿수 오류
- **WHEN** 10자리 ISBN이나 숫자가 아닌 문자가 섞인 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 체크 디지트 오류
- **WHEN** 13자리 숫자이지만 체크 디지트가 틀린 ISBN으로 등록하면
- **THEN** 시스템은 422를 반환한다

### Requirement: ISBN 중복 금지
시스템은 같은 ISBN의 도서를 두 번 등록할 수 없게 MUST 한다.

#### Scenario: 중복 등록
- **WHEN** 이미 등록된 ISBN으로 `POST /books`를 다시 호출하면
- **THEN** 시스템은 409를 반환하고 기존 도서는 바뀌지 않는다

### Requirement: 도서 조회
시스템은 ISBN으로 단건 조회와, 페이지 단위 목록 조회를 SHALL 제공한다. 목록은 `limit`(기본 20, 최대 100)과 `offset`을 받고, 전체 건수를 함께 반환한다.

#### Scenario: 단건 조회
- **WHEN** 등록된 ISBN으로 `GET /books/{isbn}`을 호출하면
- **THEN** 시스템은 200과 도서 정보를 반환한다

#### Scenario: 없는 도서 조회
- **WHEN** 등록되지 않은 ISBN으로 `GET /books/{isbn}`을 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 목록 페이지네이션
- **WHEN** 도서 25권이 있는 상태에서 `GET /books?limit=10&offset=20`을 호출하면
- **THEN** 시스템은 5건의 항목과 전체 건수 25를 반환한다

#### Scenario: limit 상한 초과
- **WHEN** `GET /books?limit=101`을 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: 도서 수정
시스템은 ISBN을 제외한 도서 필드를 부분 수정할 수 있게 SHALL 한다. 요청에 포함된 필드만 바뀐다.

#### Scenario: 정가 수정
- **WHEN** `PATCH /books/{isbn}`에 정가만 담아 호출하면
- **THEN** 시스템은 정가만 바꾸고 나머지 필드는 그대로 둔 도서 정보를 반환한다

#### Scenario: 없는 도서 수정
- **WHEN** 등록되지 않은 ISBN으로 `PATCH /books/{isbn}`을 호출하면
- **THEN** 시스템은 404를 반환한다

### Requirement: 도서 삭제
시스템은 도서를 삭제할 수 있게 SHALL 한다. 단, 매장 재고나 다른 데이터가 참조하는 도서는 삭제를 거부 MUST 한다.

#### Scenario: 참조 없는 도서 삭제
- **WHEN** 재고가 없는 도서에 `DELETE /books/{isbn}`을 호출하면
- **THEN** 시스템은 204를 반환하고 이후 조회 시 404가 된다

#### Scenario: 재고가 있는 도서 삭제
- **WHEN** 매장 재고가 등록된 도서에 `DELETE /books/{isbn}`을 호출하면
- **THEN** 시스템은 409를 반환하고 도서를 삭제하지 않는다

#### Scenario: 다른 컨텍스트가 참조하는 도서 삭제
- **WHEN** 추천(curations)이나 납품 목록 행(order_items)이 매칭 ISBN으로 참조하는 도서에 `DELETE /books/{isbn}`을 호출하면
- **THEN** 시스템은 409를 반환하고 도서를 삭제하지 않는다

### Requirement: 도서 저장 제약
API를 거치지 않은 쓰기에도 도서 데이터 규칙이 지켜지도록, 저장 계층은 13자리 숫자가 아닌 ISBN과 음수 정가를 MUST 거부한다. 다른 테이블이 참조하는 도서 행의 삭제도 저장 계층에서 거부한다.

#### Scenario: 잘못된 ISBN 직접 저장
- **WHEN** books에 ISBN `978-0306406157`(하이픈 포함)을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 음수 정가 직접 저장
- **WHEN** books에 정가 -1000으로 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 참조된 도서 직접 삭제
- **WHEN** store_inventory가 참조하는 books 행을 DB에서 직접 삭제하려 하면
- **THEN** 데이터베이스가 삭제를 거부한다
