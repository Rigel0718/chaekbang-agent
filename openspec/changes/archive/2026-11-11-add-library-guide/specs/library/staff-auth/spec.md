## MODIFIED Requirements

### Requirement: 역할별 접근 제한
키오스크 계정은 다음만 할 수 있어야 MUST 한다.
- 기관 정보 조회
- 도서관 안내와 임시 휴관일 조회
- 도서·사본 조회
- 어린이 구분과 어린이 도서 조회
- 대출하기와 반납하기
- AI 사서와 대화하기

그 밖의 쓰기(도서·사본·회원·직원 관리, 기관 수정, 안내 수정)와 회원·대출 목록 조회는 관리자만 할 수 있다. 키오스크가 관리자 전용 API를 호출하면 403을 돌려준다.

#### Scenario: 키오스크의 도서 조회
- **WHEN** 키오스크 토큰으로 `GET /library-books`를 호출하면
- **THEN** 200을 돌려준다

#### Scenario: 키오스크의 관리 작업
- **WHEN** 키오스크 토큰으로 `POST /library-books`, `GET /members`, `PATCH /library`를 각각 호출하면
- **THEN** 모두 403을 돌려주고 데이터는 바뀌지 않는다

#### Scenario: 키오스크의 AI 사서 대화
- **WHEN** 키오스크 토큰으로 `POST /librarian/messages`를 호출하면
- **THEN** 200으로 응답한다

#### Scenario: 키오스크의 안내 조회
- **WHEN** 키오스크 토큰으로 `GET /library/guide`, `GET /library/closures`를 호출하면
- **THEN** 둘 다 200을 돌려준다

#### Scenario: 키오스크의 휴관일 관리
- **WHEN** 키오스크 토큰으로 `POST /library/closures`, `DELETE /library/closures/{id}`를 각각 호출하면
- **THEN** 모두 403을 돌려주고 휴관일은 바뀌지 않는다
