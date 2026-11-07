# Spec Delta

## MODIFIED Requirements

### Requirement: 기관 데이터 분리
시스템은 모든 기관 데이터(기관 도서, 사본, 회원, 대출, 직원 계정)의 조회와 쓰기를 로그인한 계정의 기관 범위로 MUST 제한한다.
- 기관은 요청 값이 아니라 인증 토큰으로 정한다.
- 다른 기관의 데이터를 가리키는 요청은 그 데이터가 없는 것처럼 404로 응답한다.
- 목록 조회에는 다른 기관의 데이터가 들어가지 않는다.

#### Scenario: 다른 기관의 사본 조회
- **WHEN** A 기관 직원이 B 기관 사본의 id로 `GET /holdings/{id}`를 호출하면
- **THEN** 404를 돌려준다

#### Scenario: 목록에 다른 기관 데이터 없음
- **WHEN** A, B 두 기관에 회원이 있을 때 A 기관 관리자가 `GET /members`를 호출하면
- **THEN** A 기관 회원만 돌려준다

#### Scenario: 요청 본문의 library_id 무시
- **WHEN** A 기관 관리자가 본문에 B 기관의 `library_id`를 넣어 `POST /members`를 호출하면
- **THEN** 회원은 A 기관에 만들어진다

#### Scenario: 다른 기관 데이터 수정
- **WHEN** A 기관 관리자가 B 기관 회원의 id로 `PATCH /members/{id}`를 호출하면
- **THEN** 404를 돌려주고 B 기관 회원은 바뀌지 않는다
