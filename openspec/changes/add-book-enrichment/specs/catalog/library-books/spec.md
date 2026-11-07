# Spec Delta

## MODIFIED Requirements

### Requirement: 공식 서지 연결
시스템은 기관 도서를 만들거나 ISBN이 바뀔 때 같은 ISBN의 공식 서지가 있으면 MUST 연결한다. 없으면 연결 없이 저장하고, 기관 도서는 기관 값으로 그대로 동작한다. 응답의 `book_id`로 연결 여부를 알 수 있다. 처리 상태(`enrichment_status`)는 연결되면 `enriched`, 연결이 없으면 `pending`이다. ISBN을 고치면 연결과 처리 상태를 다시 정하고, 기관 값은 지우지 않는다.

#### Scenario: 공식 서지가 있는 ISBN
- **WHEN** 공식 서지에 있는 ISBN으로 기관 도서를 등록하면
- **THEN** 응답의 `book_id`가 그 공식 서지를 가리킨다

#### Scenario: 공식 서지가 없는 ISBN
- **WHEN** 공식 서지에 없는 ISBN으로 기관 도서를 등록하면
- **THEN** `book_id`는 비어 있고 입력한 값으로 조회된다

#### Scenario: 연결되면 처리 완료
- **WHEN** 공식 서지에 있는 ISBN으로 기관 도서를 등록하면
- **THEN** 처리 상태는 `enriched`다

#### Scenario: 연결이 없으면 처리 대기
- **WHEN** 공식 서지에 없는 ISBN으로 기관 도서를 등록하면
- **THEN** 처리 상태는 `pending`이다

#### Scenario: ISBN 수정 시 다시 대기
- **WHEN** `not_found` 도서의 ISBN을 공식 서지에 없는 값으로 `PATCH /library-books/{id}`로 고치면
- **THEN** 처리 상태가 `pending`이 된다

#### Scenario: ISBN 없는 도서
- **WHEN** ISBN 없이 기관 도서를 등록하면
- **THEN** `book_id`는 비어 있다

### Requirement: 어린이/일반 도서 구분
시스템은 기관 도서마다 대상 구분(`audience`)과 그 근거(`audience_source`)를 SHALL 보관한다. 같은 ISBN이라도 기관마다 값이 다를 수 있다. 어린이 구분은 기관의 판단이고 공식 서지에는 두지 않는다.
- 어린이 도서는 영유아·초등학생 대상 도서다.
- 대상 구분: `children`(어린이 도서) 또는 `general`(일반 도서). 기본값은 `general`이다.
- 근거: `default`(근거 없음, 기본값), `manual`(관리자 지정), `import_label`(가져온 파일의 별치기호·자료실·부가기호), `external_category`(연결된 공식 서지의 분류 원문)
- 근거의 우선순위는 `manual`, `import_label`, `external_category`, `default` 순이다. 낮은 근거는 높은 근거의 값을 바꾸지 않는다.
- 관리자가 대상 구분을 지정하면 근거는 `manual`이 된다.
- 목록 조회는 대상 구분으로 거를 수 있다.

#### Scenario: 기본값
- **WHEN** 대상 구분 없이 도서를 등록하면
- **THEN** 대상 구분 `general`, 근거 `default`로 저장된다

#### Scenario: 관리자 지정
- **WHEN** 관리자가 `PATCH /library-books/{id}`로 대상 구분을 `children`으로 바꾸면
- **THEN** 대상 구분은 `children`, 근거는 `manual`이 된다

#### Scenario: 높은 근거 유지
- **WHEN** 근거가 `manual`이고 대상 구분이 `general`인 기관 도서가 분류 원문이 `국내도서-유아`인 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `manual`로 남는다

#### Scenario: 파일 근거 유지
- **WHEN** 근거가 `import_label`인 기관 도서가 분류 원문이 `국내도서-유아`인 공식 서지에 연결되면
- **THEN** 근거는 `import_label`로 남는다

#### Scenario: 어린이 도서만 거르기
- **WHEN** `GET /library-books?audience=children`을 호출하면
- **THEN** 대상 구분이 `children`인 도서만 돌려준다

#### Scenario: 기관별 구분
- **WHEN** 같은 ISBN의 기관 도서를 A 기관 관리자가 `children`으로 지정하면
- **THEN** B 기관 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 허용되지 않은 구분
- **WHEN** library_books에 대상 구분 `teen`으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

## ADDED Requirements

### Requirement: 외부 분류 근거
어린이 구분은 기관의 요청(등록, 가져오기, ISBN 수정, 어린이 구분 갱신)에서만 MUST 바뀐다. 이때 연결된 공식 서지의 분류 원문이 정확히 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나이고 기관 도서의 근거가 `default`이면 대상 구분을 `children`, 근거를 `external_category`로 정한다. 연결이 풀리거나 근거가 아닌 분류의 공식 서지로 바뀌면 근거가 `external_category`인 값은 `general`, `default`로 되돌린다.

#### Scenario: 어린이 근거인 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나인 공식 서지에 연결되면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 된다

#### Scenario: 어린이 근거가 아닌 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-청소년`, `국내도서-전집`, `국내도서-중고등학습서-중학교`, `국내도서-소설/시/희곡`이거나 비어 있는 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 새로 등록하는 도서
- **WHEN** 분류 원문이 `국내도서-어린이`인 공식 서지가 있는 ISBN으로 대상 구분 없이 기관 도서를 등록하면
- **THEN** 응답의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 새로 가져오는 도서
- **WHEN** 분류 원문이 `국내도서-어린이`인 공식 서지가 있는 ISBN의 행을 파일 근거 없이 적용하면
- **THEN** 새 기관 도서의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 운영자 실행은 바꾸지 않음
- **WHEN** 운영자의 채움 실행이 근거가 `default`인 기관 도서를 분류 원문이 `국내도서-어린이`인 공식 서지에 연결하면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 연결이 풀리면 되돌림
- **WHEN** 근거가 `external_category`인 기관 도서의 ISBN을 공식 서지에 없는 값으로 고치면
- **THEN** 대상 구분은 `general`, 근거는 `default`가 된다

### Requirement: 어린이 구분 갱신
관리자는 `POST /library-books/audience/refresh`로 자기 기관 도서의 어린이 구분을 공식 서지의 분류 원문에 맞춰 SHALL 갱신할 수 있다. 근거가 `default`나 `external_category`인 도서만 다시 판단하고, 바뀐 건수를 돌려준다. 다른 기관의 도서는 바뀌지 않는다.

#### Scenario: 채움 뒤 갱신
- **WHEN** 운영자의 채움 실행으로 분류 원문이 `국내도서-어린이`인 공식 서지에 연결된 기관 도서가 있고 관리자가 갱신하면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 되고 바뀐 건수 1을 돌려준다

#### Scenario: 높은 근거는 갱신하지 않음
- **WHEN** 근거가 `manual`이나 `import_label`인 도서가 있고 관리자가 갱신하면
- **THEN** 그 도서의 값은 바뀌지 않는다

#### Scenario: 다른 기관에 영향 없음
- **WHEN** 같은 ISBN의 도서를 가진 두 기관 중 A 기관 관리자만 갱신하면
- **THEN** B 기관 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 다시 갱신
- **WHEN** 갱신한 뒤 바뀐 것 없이 다시 갱신하면
- **THEN** 바뀐 건수 0을 돌려준다

#### Scenario: 키오스크 계정 거부
- **WHEN** 키오스크 계정이 `POST /library-books/audience/refresh`를 호출하면
- **THEN** 403을 돌려준다
