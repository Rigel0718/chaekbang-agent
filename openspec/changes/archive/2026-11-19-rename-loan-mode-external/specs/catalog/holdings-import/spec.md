## MODIFIED Requirements

### Requirement: 가져오기 대상과 권한
관리자는 자기 기관에 장서 파일을 SHALL 올릴 수 있다. 운영 방식이 `external`인 기관만 쓸 수 있고, `internal` 기관의 요청은 409로 거부한다. 키오스크는 쓸 수 없다.

#### Scenario: 자체 대출 기관의 가져오기
- **WHEN** 운영 방식이 `internal`인 기관의 관리자가 `POST /holding-imports`를 호출하면
- **THEN** 409를 돌려주고 가져오기 기록을 만들지 않는다

#### Scenario: 키오스크의 가져오기
- **WHEN** 키오스크 토큰으로 `POST /holding-imports`를 호출하면
- **THEN** 403을 돌려준다
