## MODIFIED Requirements

### Requirement: 외부 분류 근거
어린이 구분은 기관의 요청(등록, 가져오기, ISBN 수정, 어린이 구분 갱신)에서만 MUST 바뀐다. 이때 연결된 공식 서지에 외부 근거가 있고 기관 도서의 근거가 `default`이면 대상 구분을 `children`, 근거를 `external_category`로 정한다. 외부 근거는 둘이다. 하나는 분류 원문이 정확히 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나인 것이고, 다른 하나는 부가기호 첫 자리가 6(초등 학습참고서)이나 7(아동)인 것이다. 연결이 풀리거나 외부 근거가 없는 공식 서지로 바뀌면 근거가 `external_category`인 값은 `general`, `default`로 되돌린다.

#### Scenario: 어린이 근거인 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나인 공식 서지에 연결되면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 된다

#### Scenario: 어린이 근거인 부가기호
- **WHEN** 근거가 `default`인 기관 도서가 부가기호가 `74850`이나 `63710`인 공식 서지에 연결되면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 된다

#### Scenario: 어린이 근거가 아닌 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-청소년`, `국내도서-전집`, `국내도서-중고등학습서-중학교`, `국내도서-소설/시/희곡`, `문학 > 한국문학 > 소설`이거나 비어 있고 부가기호가 없는 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 어린이 근거가 아닌 부가기호
- **WHEN** 근거가 `default`인 기관 도서가 부가기호가 `03810`이나 `43810`인 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 새로 등록하는 도서
- **WHEN** 부가기호가 `77810`인 공식 서지가 있는 ISBN으로 기관 도서를 등록하면
- **THEN** 그 도서의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 새로 가져오는 도서
- **WHEN** 분류 원문이 `국내도서-어린이`인 공식 서지가 있는 ISBN의 행을 파일 근거 없이 적용하면
- **THEN** 새 기관 도서의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 높은 근거 유지
- **WHEN** 근거가 `manual`이고 대상 구분이 `general`인 기관 도서가 부가기호가 `74850`인 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `manual`로 남는다

#### Scenario: 파일 근거 유지
- **WHEN** 근거가 `import_label`인 기관 도서가 분류 원문이 `국내도서-유아`인 공식 서지에 연결되면
- **THEN** 근거는 `import_label`로 남는다

#### Scenario: 운영자 실행은 바꾸지 않음
- **WHEN** 운영자의 채움 실행이 기관 도서를 부가기호가 `74850`인 공식 서지에 연결하면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 연결이 풀리면 되돌림
- **WHEN** 근거가 `external_category`인 기관 도서의 ISBN을 공식 서지에 없는 값으로 고치면
- **THEN** 대상 구분은 `general`, 근거는 `default`가 된다

### Requirement: 어린이 구분 갱신
관리자는 `POST /children/refresh`로 자기 기관 도서의 어린이 구분을 공식 서지의 외부 근거(분류 원문, 부가기호)에 맞춰 SHALL 갱신할 수 있다. 근거가 `default`나 `external_category`인 도서만 다시 판단하고, 바뀐 건수를 돌려준다. 다른 기관의 도서는 바뀌지 않는다.

#### Scenario: 채움 뒤 갱신
- **WHEN** 운영자의 채움 실행으로 부가기호가 `74850`인 공식 서지에 연결된 기관 도서가 있고 관리자가 갱신하면
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
- **WHEN** 키오스크 계정이 `POST /children/refresh`를 호출하면
- **THEN** 403을 돌려준다
