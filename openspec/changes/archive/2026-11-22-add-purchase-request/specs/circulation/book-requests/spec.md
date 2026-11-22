## MODIFIED Requirements

### Requirement: 희망도서 목록과 닫기
관리자는 자기 기관의 희망도서 신청을 SHALL 조회하고 닫을 수 있다.
- `GET /book-requests`: 상태(`requested`, `closed`)로 거르고 페이지로 나눈다. 최신 신청이 먼저다. 줄마다 신청 응답의 값에 회원번호와 닫은 구매 요청서 id를 더한다. 회원이 지워진 신청은 회원번호가 비어 있다. 관리자가 닫았거나 아직 처리 전인 신청은 구매 요청서 id가 비어 있다.
- `PATCH /book-requests/{id}`: 상태를 `closed`로 바꾼다. 이미 `closed`면 그대로 돌려준다. `requested`로 되돌리지 않는다.
- 구매 요청서를 확정하면 같은 ISBN의 처리 전 신청이 코드로 닫히고 그 요청서 id가 남는다.
- 키오스크는 목록과 닫기를 쓸 수 없다(403).

#### Scenario: 상태로 거르기
- **WHEN** `requested`와 `closed` 신청이 있을 때 `GET /book-requests?status=requested`를 호출하면
- **THEN** `requested` 신청만 최신순으로 회원번호와 함께 돌려준다

#### Scenario: 닫기
- **WHEN** 관리자가 `requested` 신청을 `PATCH /book-requests/{id}`로 닫으면
- **THEN** 상태가 `closed`가 되고 구매 요청서 id는 비어 있다

#### Scenario: 요청서로 닫힌 신청
- **WHEN** 신청의 ISBN이 든 구매 요청서가 확정된 뒤 관리자가 목록을 조회하면
- **THEN** 그 신청은 `closed`이고 줄에 그 구매 요청서 id가 있다

#### Scenario: 되돌리기 거부
- **WHEN** 관리자가 상태 `requested`로 PATCH를 보내면
- **THEN** 422를 돌려준다

#### Scenario: 키오스크의 목록과 닫기
- **WHEN** 키오스크가 `GET /book-requests`나 `PATCH /book-requests/{id}`를 호출하면
- **THEN** 403이다
