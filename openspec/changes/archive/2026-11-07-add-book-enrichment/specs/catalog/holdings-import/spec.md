# Spec Delta

## MODIFIED Requirements

### Requirement: 어린이 도서 분류 근거
시스템은 별치기호의 아동 표시, 자료실 이름의 어린이·아동·유아 표시, 부가기호 첫 자리 6(초등 학습참고서)과 7(아동)을 어린이 도서 근거로 MUST 인식한다. 별치기호의 아동 표시는 `아`, `아동`, `어린이`, `유`, `유아`, `j`다. 근거가 있고 기관 도서의 근거가 `default`나 `external_category`이면 대상 구분을 `children`, 근거를 `import_label`로 정한다. 관리자가 지정한 값은 바꾸지 않는다. 근거가 없는 행은 대상 구분을 바꾸지 않는다.

#### Scenario: 별치기호로 분류
- **WHEN** 별치기호가 `아`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 자료실로 분류
- **WHEN** 자료실이 `어린이자료실`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 부가기호로 분류
- **WHEN** 부가기호가 `77810`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 다른 기관에 영향 없음
- **WHEN** A 기관 파일의 별치기호 `아`인 행이 B 기관도 가진 ISBN이면
- **THEN** A 기관 도서만 `children`이 되고 B 기관 도서는 바뀌지 않는다

#### Scenario: 초등 학습참고서 부가기호
- **WHEN** 부가기호가 `63710`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 중·고등 부가기호
- **WHEN** 부가기호가 `43810`이나 `53710`인 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 출처가 없는 별치기호
- **WHEN** 별치기호가 `어`나 `c`인 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 외부 분류 근거보다 우선
- **WHEN** 근거가 `external_category`인 기관 도서의 행에 별치기호 `아`가 있으면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 관리자 지정 우선
- **WHEN** 관리자가 `general`로 지정한 도서의 행에 별치기호 `아`가 있으면
- **THEN** 대상 구분은 `general`, 근거는 `manual`로 남는다

#### Scenario: 근거가 없는 행
- **WHEN** 별치기호·자료실·부가기호에 어린이 표시가 없는 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다
