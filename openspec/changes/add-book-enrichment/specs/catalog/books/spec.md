# Spec Delta

## MODIFIED Requirements

### Requirement: 어린이/일반 도서 구분
시스템은 도서마다 대상 구분(`audience`)과 그 근거(`audience_source`)를 SHALL 보관한다.
- 대상 구분: `children`(어린이 도서) 또는 `general`(일반 도서). 기본값은 `general`이다.
- 근거: `default`(근거 없음, 기본값), `manual`(관리자 지정), `import_label`(가져온 파일의 별치기호·자료실·부가기호), `external_category`(외부 도서 API 분류)
- 근거의 우선순위는 `manual`, `import_label`, `external_category`, `default` 순이다. 낮은 근거는 높은 근거의 값을 바꾸지 않는다.
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

#### Scenario: 근거 우선순위
- **WHEN** 근거가 `import_label`인 도서의 외부 분류가 어린이 근거이면
- **THEN** 근거는 `import_label`로 남는다
