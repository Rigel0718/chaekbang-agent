# Spec Delta

## MODIFIED Requirements

### Requirement: 공식 서지 쓰기 제한
공식 서지(`books`)는 ISBN이 있는 책의 서지정보만 SHALL 보관하고, 운영자가 실행하는 서지정보 채움만 만든다. 기관 관리자와 키오스크가 쓰는 API에는 공식 서지를 만들거나 고치거나 지우는 경로를 MUST NOT 둔다. 기관의 파일 값과 입력 값은 공식 서지에 들어가지 않는다.

#### Scenario: 도서 API 경로 없음
- **WHEN** 관리자가 `POST /books`, `PATCH /books/{id}`, `DELETE /books/{id}`를 호출하면
- **THEN** 404를 돌려주고 공식 서지는 바뀌지 않는다

#### Scenario: 기관 도서 등록은 공식 서지를 만들지 않음
- **WHEN** 관리자가 공식 서지에 없는 ISBN으로 기관 도서를 등록하면
- **THEN** books 행은 늘어나지 않는다
