## MODIFIED Requirements

### Requirement: 도서 저장 제약
API를 거치지 않은 쓰기에도 공식 서지 규칙이 지켜지도록, 저장 계층은 비어 있거나 13자리 숫자가 아닌 ISBN, 중복 ISBN, 음수 정가, 5자리 숫자가 아닌 부가기호를 MUST 거부한다. 정가와 부가기호가 비어 있는 것은 허용한다. 기관 도서가 참조하는 공식 서지 행의 삭제도 저장 계층에서 거부한다.

#### Scenario: 잘못된 ISBN 직접 저장
- **WHEN** books에 ISBN `978-0306406157`(하이픈 포함)을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 중복 ISBN 직접 저장
- **WHEN** 이미 있는 ISBN으로 books에 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 음수 정가 직접 저장
- **WHEN** books에 정가 -1000으로 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 잘못된 부가기호 직접 저장
- **WHEN** books에 부가기호 `7485A`를 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: ISBN 없는 행 직접 저장
- **WHEN** books에 ISBN 없이 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 참조된 도서 직접 삭제
- **WHEN** library_books가 참조하는 books 행을 DB에서 직접 삭제하려 하면
- **THEN** 데이터베이스가 삭제를 거부한다
