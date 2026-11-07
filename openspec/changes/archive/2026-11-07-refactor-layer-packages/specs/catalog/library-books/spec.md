# Spec Delta

## MODIFIED Requirements

### Requirement: 기관 도서 단건과 목록 조회
시스템은 내부 id로 단건 조회와 페이지 단위 목록 조회를 SHALL 제공하고, 로그인한 기관의 기관 도서만 돌려준다.
- 목록은 `limit`(기본 20, 최대 100)과 `offset`을 받고, 전체 건수를 함께 반환한다.
- 목록은 `isbn`으로 거를 수 있다.
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

### Requirement: 기관 도서 부분 수정
관리자는 자기 기관의 기관 도서를 부분 수정할 수 있어야 SHALL 한다. 요청에 포함된 필드만 바뀐다. 공식 서지에 연결된 도서는 ISBN만 고칠 수 있고, 그 밖의 서지 필드를 보내면 409를 돌려준다. ISBN을 고치면 등록과 같은 정규화·검증·중복 규칙을 따르고 공식 서지 연결을 다시 정한다. 매입·납품 사본이 있는 도서는 ISBN을 비울 수 없다.

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

## REMOVED Requirements

### Requirement: 어린이/일반 도서 구분
**Reason**: 어린이 구분은 기관 개별 기능이다
**Migration**: features/children의 어린이 구분과 `PUT /children/books/{id}`, `GET /children/books`를 쓴다

### Requirement: 외부 분류 근거
**Reason**: 어린이 구분은 기관 개별 기능이다
**Migration**: features/children의 외부 분류 근거를 따른다

### Requirement: 어린이 구분 갱신
**Reason**: 어린이 구분은 기관 개별 기능이다
**Migration**: `POST /children/refresh`를 쓴다
