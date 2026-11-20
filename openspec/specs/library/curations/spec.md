# library/curations Specification

## Purpose
관리 담당자가 소장 도서로 주제 큐레이션을 만들어 승인하면 이용자 쪽(AI 사서, 이용자 화면)에 게시되게 한다. 큐레이션의 책은 항상 그 기관의 추천 가능한 책이다.

## Requirements

### Requirement: 큐레이션 내용
큐레이션은 제목(40자 이내), 소개(200자 이내, 비어도 됨), 책 3~10권을 MUST 가진다. 책마다 기관 도서와 이유 한 줄(60자 이내)을 두고, 순서는 받은 순서다. 같은 책이 두 번 오면 처음 것만 남긴다. 길이나 권수를 어기면 422를 돌려준다.

#### Scenario: 권수 부족
- **WHEN** 책 2권으로 큐레이션을 만들면
- **THEN** 422를 돌려준다

#### Scenario: 이유 길이 초과
- **WHEN** 이유가 61자인 책이 있으면
- **THEN** 422를 돌려준다

#### Scenario: 같은 책 두 번
- **WHEN** 같은 기관 도서를 두 번 넣어 4권으로 만들면
- **THEN** 큐레이션의 책은 3권이고 처음 넣은 이유가 남는다

### Requirement: 큐레이션의 책은 추천 가능한 소장 도서
큐레이션을 만들거나 고칠 때 모든 책은 그 기관의 추천 가능한 책(대출 가능이나 대출 중 사본이 있음)이어야 MUST 한다. 다른 기관의 책이나 없는 책은 404, 분실·훼손·제적 사본만 있는 책은 409이고 큐레이션은 저장되지 않는다. 오류에는 걸린 기관 도서 id를 담는다.

#### Scenario: 제적 사본만 있는 책
- **WHEN** 사본이 모두 제적된 책을 넣어 큐레이션을 만들면
- **THEN** 409와 그 책의 id를 돌려주고 큐레이션은 없다

#### Scenario: 다른 기관의 책
- **WHEN** A 기관 관리자가 B 기관에만 있는 기관 도서 id를 넣으면
- **THEN** 404를 돌려준다

### Requirement: 큐레이션 관리 API
관리자는 자기 기관의 큐레이션을 SHALL 관리할 수 있다. `POST /curations`(만들기, `draft`), `GET /curations`(목록, 상태로 거르기, 최신순), `GET /curations/{id}`, `PATCH /curations/{id}`(`draft`만), `DELETE /curations/{id}`(`draft`만), `POST /curations/{id}/submit`, `/approve`, `/reject`, `/unpublish`. 응답은 상태, 승인자, 시각, 반려 사유, 책 카드를 담는다.

#### Scenario: 만들기
- **WHEN** 관리자가 추천 가능한 책 3권으로 `POST /curations`를 호출하면
- **THEN** 201과 함께 상태 `draft`인 큐레이션을 돌려준다

#### Scenario: 상태로 거르기
- **WHEN** `draft`와 `pending_approval` 큐레이션이 있을 때 `GET /curations?status=pending_approval`을 호출하면
- **THEN** 승인 대기 큐레이션만 돌려준다

#### Scenario: 고친 뒤 제출
- **WHEN** 반려된 큐레이션의 책을 PATCH로 바꾸고 제출하면
- **THEN** 바뀐 책으로 상태 `pending_approval`이다

### Requirement: 승인하면 게시
큐레이션을 승인하면 시스템은 같은 트랜잭션에서 SHALL 게시한다. 상태는 `published`가 되고 게시본 읽기에 바로 나온다. 내리기를 하면 `archived`가 되고 게시본 읽기에서 바로 빠진다.

#### Scenario: 승인 뒤 게시본
- **WHEN** 승인 대기 큐레이션을 승인하고 게시본을 읽으면
- **THEN** 그 큐레이션이 있다

#### Scenario: 내리기
- **WHEN** 게시된 큐레이션을 내리고 게시본을 읽으면
- **THEN** 그 큐레이션이 없고 상태는 `archived`다

### Requirement: 게시본 읽기
`GET /librarian/curations`는 키오스크와 관리자 토큰으로 자기 기관의 게시된 큐레이션을 SHALL 돌려준다. 게시 시각 최신순 5개까지, 큐레이션마다 제목, 소개, 게시 시각, 책 카드(이유 포함, 추천 카드와 같은 서지·대출 상태)를 담는다. 승인자와 반려 사유는 담지 않는다. 다른 상태의 큐레이션과 다른 기관의 큐레이션은 나오지 않는다.

#### Scenario: 게시된 것만
- **WHEN** `draft`, `pending_approval`, `published`, `archived` 큐레이션이 하나씩 있을 때 키오스크 토큰으로 읽으면
- **THEN** `published` 하나만 있다

#### Scenario: 최신 5개
- **WHEN** 게시된 큐레이션이 6개면
- **THEN** 게시 시각이 가장 이른 하나를 뺀 5개가 최신순으로 있다

#### Scenario: 다른 기관의 게시본
- **WHEN** B 기관에만 게시된 큐레이션이 있을 때 A 기관 키오스크가 읽으면
- **THEN** 목록이 비어 있다

### Requirement: 읽을 때 다시 거르기
게시본을 읽을 때 지금 추천할 수 없는 책(분실·훼손·제적 사본만 남음)은 SHALL 빼고 보여 준다. 저장된 큐레이션의 책은 바꾸지 않는다. 남는 책이 없는 큐레이션은 읽기 결과에서 뺀다.

#### Scenario: 게시 뒤 제적
- **WHEN** 3권짜리 게시 큐레이션의 한 책이 게시 뒤 모두 제적되면
- **THEN** 게시본 읽기에는 2권만 있고 관리자 상세에는 3권이 그대로 있다

#### Scenario: 모두 빠짐
- **WHEN** 게시 큐레이션의 모든 책이 추천할 수 없게 되면
- **THEN** 게시본 읽기에 그 큐레이션이 없다

### Requirement: 큐레이션의 개인정보
큐레이션과 그 응답에는 회원 이름, 회원번호, 회원 id, 대출 기록, 기증자가 MUST NOT 있다.

#### Scenario: 응답 필드
- **WHEN** 대출 중인 책이 든 큐레이션을 관리 API와 게시본 읽기로 읽으면
- **THEN** 응답에 회원 값과 기증자 값이 없다
