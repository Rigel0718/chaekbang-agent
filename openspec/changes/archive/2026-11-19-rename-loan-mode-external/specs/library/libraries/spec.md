## MODIFIED Requirements

### Requirement: 기관 정보와 운영 방식
시스템은 기관마다 이름, 유형, 운영 방식, 기본 대출 기간을 SHALL 보관한다.
- 유형: `small_library` 또는 `bookstore`
- 운영 방식(`loan_mode`): `external`(외부 대출) 또는 `internal`(자체 대출)
- 기본 대출 기간: 1 이상의 일수

로그인한 직원은 자기 기관 정보를 조회할 수 있고, 관리자는 이름·운영 방식·기본 대출 기간을 수정할 수 있다.

#### Scenario: 자기 기관 조회
- **WHEN** 로그인한 직원이 `GET /library`를 호출하면
- **THEN** 자기 기관의 이름, 유형, 운영 방식, 기본 대출 기간을 돌려준다

#### Scenario: 기본 대출 기간 수정
- **WHEN** 관리자가 `PATCH /library`로 기본 대출 기간을 21로 바꾸면
- **THEN** 바뀐 값을 돌려주고 이후 대출의 반납 예정일 계산에 쓰인다

#### Scenario: 잘못된 대출 기간
- **WHEN** 관리자가 기본 대출 기간을 0으로 바꾸려 하면
- **THEN** 422를 돌려주고 값은 바뀌지 않는다

#### Scenario: 허용되지 않은 운영 방식
- **WHEN** 관리자가 운영 방식을 `hybrid`로 바꾸려 하면
- **THEN** 422를 돌려준다

#### Scenario: 옛 운영 방식 값
- **WHEN** 관리자가 `PATCH /library`로 운영 방식을 `imported`로 바꾸려 하면
- **THEN** 422를 돌려주고 값은 바뀌지 않는다
