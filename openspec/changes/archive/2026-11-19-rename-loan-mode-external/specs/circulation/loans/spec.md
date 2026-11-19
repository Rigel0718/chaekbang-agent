## MODIFIED Requirements

### Requirement: 운영 방식에 따른 대출 차단
운영 방식이 `external`인 기관에서는 대출과 반납을 MUST NOT 처리한다. 대출은 기존 대출 프로그램에서 하기 때문이다. 이런 요청에는 409와 함께 "대출은 데스크에서" 안내 메시지를 돌려준다.

#### Scenario: 외부 대출 기관에서 대출
- **WHEN** 운영 방식이 `external`인 기관의 키오스크가 `POST /loans`를 호출하면
- **THEN** 409와 안내 메시지를 돌려주고 대출은 만들어지지 않는다

#### Scenario: 외부 대출 기관에서 반납
- **WHEN** 운영 방식이 `external`인 기관의 키오스크가 `POST /loans/return`을 호출하면
- **THEN** 409와 안내 메시지를 돌려준다
