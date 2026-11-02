# Spec Delta

## Purpose

매장 서가에 실제로 있는 도서의 수량과 위치를 관리해, 손님 응대와 추천이 "매장 재고 먼저" 원칙을 따를 수 있는 근거 데이터를 제공한다.

## ADDED Requirements

### Requirement: 재고 등록
시스템은 등록된 도서의 ISBN, 수량, 서가 위치로 매장 재고를 등록 SHALL 한다. 한 ISBN에는 재고 레코드가 하나만 존재한다. 수량은 0 이상의 정수다.

#### Scenario: 정상 등록
- **WHEN** 도서 목록에 있는 ISBN으로 수량 3, 서가 위치 "그림책 A-2"를 담아 `POST /inventory`를 호출하면
- **THEN** 시스템은 201과 함께 재고 정보를 반환한다

#### Scenario: 도서 목록에 없는 ISBN
- **WHEN** books에 없는 ISBN으로 `POST /inventory`를 호출하면
- **THEN** 시스템은 404를 반환하고 재고를 만들지 않는다

#### Scenario: 이미 재고가 있는 ISBN
- **WHEN** 재고 레코드가 이미 있는 ISBN으로 `POST /inventory`를 호출하면
- **THEN** 시스템은 409를 반환한다

#### Scenario: 음수 수량
- **WHEN** 수량 -1로 `POST /inventory`를 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: 재고 조회
시스템은 ISBN으로 재고 단건을 조회하고, 페이지 단위로 재고 목록을 조회할 수 있게 SHALL 한다. 응답에는 도서 제목과 저자가 함께 포함된다. 목록은 `in_stock=true`로 수량 1 이상인 항목만 거를 수 있다.

#### Scenario: 단건 조회
- **WHEN** 재고가 있는 ISBN으로 `GET /inventory/{isbn}`을 호출하면
- **THEN** 시스템은 수량, 서가 위치, 도서 제목, 저자를 반환한다

#### Scenario: 재고 없는 ISBN 조회
- **WHEN** 재고 레코드가 없는 ISBN으로 `GET /inventory/{isbn}`을 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 품절 제외 목록
- **WHEN** 수량 0인 재고와 수량 2인 재고가 있는 상태에서 `GET /inventory?in_stock=true`를 호출하면
- **THEN** 시스템은 수량 2인 재고만 반환한다

### Requirement: 재고 수정
시스템은 재고의 수량과 서가 위치를 부분 수정할 수 있게 SHALL 한다.

#### Scenario: 수량 변경
- **WHEN** `PATCH /inventory/{isbn}`에 수량 0을 담아 호출하면
- **THEN** 시스템은 수량을 0으로 바꾸고 서가 위치는 그대로 둔다

#### Scenario: 음수로 수정
- **WHEN** `PATCH /inventory/{isbn}`에 수량 -1을 담아 호출하면
- **THEN** 시스템은 422를 반환하고 재고를 바꾸지 않는다

### Requirement: 재고 삭제
시스템은 재고 레코드를 삭제할 수 있게 SHALL 한다. 재고를 삭제해도 도서 정보는 남는다.

#### Scenario: 재고 삭제
- **WHEN** `DELETE /inventory/{isbn}`을 호출하면
- **THEN** 시스템은 204를 반환하고, 이후 `GET /inventory/{isbn}`은 404, `GET /books/{isbn}`은 200을 반환한다
