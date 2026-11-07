# catalog/books Specification

## Purpose

ISBN이 있는 책의 공식 서지를 서비스 운영자 층에서 보관해, 기관 도서가 같은 ISBN으로 연결해 쓰게 하고 기관의 입력이 공식 값을 바꾸지 못하게 한다.

## Requirements

### Requirement: 도서 저장 제약
API를 거치지 않은 쓰기에도 공식 서지 규칙이 지켜지도록, 저장 계층은 비어 있거나 13자리 숫자가 아닌 ISBN, 중복 ISBN, 음수 정가를 MUST 거부한다. 정가가 비어 있는 것은 허용한다. 기관 도서가 참조하는 공식 서지 행의 삭제도 저장 계층에서 거부한다.

#### Scenario: 잘못된 ISBN 직접 저장
- **WHEN** books에 ISBN `978-0306406157`(하이픈 포함)을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 중복 ISBN 직접 저장
- **WHEN** 이미 있는 ISBN으로 books에 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 음수 정가 직접 저장
- **WHEN** books에 정가 -1000으로 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: ISBN 없는 행 직접 저장
- **WHEN** books에 ISBN 없이 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 참조된 도서 직접 삭제
- **WHEN** library_books가 참조하는 books 행을 DB에서 직접 삭제하려 하면
- **THEN** 데이터베이스가 삭제를 거부한다

### Requirement: 공식 서지 쓰기 제한
공식 서지(`books`)는 ISBN이 있는 책의 서지정보만 SHALL 보관한다. 기관 관리자와 키오스크가 쓰는 API에는 공식 서지를 만들거나 고치거나 지우는 경로를 MUST NOT 둔다. 기관의 파일 값과 입력 값은 공식 서지에 들어가지 않는다.

#### Scenario: 도서 API 경로 없음
- **WHEN** 관리자가 `POST /books`, `PATCH /books/{id}`, `DELETE /books/{id}`를 호출하면
- **THEN** 404를 돌려주고 공식 서지는 바뀌지 않는다

#### Scenario: 기관 도서 등록은 공식 서지를 만들지 않음
- **WHEN** 관리자가 공식 서지에 없는 ISBN으로 기관 도서를 등록하면
- **THEN** books 행은 늘어나지 않는다
