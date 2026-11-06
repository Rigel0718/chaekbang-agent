# Spec Delta

## MODIFIED Requirements

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
