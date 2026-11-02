# storefront/customer-interactions Specification

## Purpose

매장 큐레이터 에이전트(A)가 손님과 주고받은 기록, 사장님께 넘긴 문의, 매장에 없는 책의 주문 요청을 보관해, 응대 공백을 사장님이 나중에 이어받을 수 있게 한다.

## Requirements

### Requirement: 손님 대화 기록
시스템은 손님 대화를 대화 세션 단위로, 발화 주체와 내용을 함께 저장 SHALL 한다. 발화 주체는 `customer`, `assistant` 중 하나다.

#### Scenario: 허용되지 않은 발화 주체
- **WHEN** chat_logs에 발화 주체 `owner`로 레코드를 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

### Requirement: 사장님께 전달한 문의
시스템은 에이전트가 답하기 어려워 사장님께 넘긴 문의를 내용, 손님 연락처(선택), 처리 상태와 함께 저장 SHALL 한다. 처리 상태는 `unread`, `read`, `resolved` 중 하나이고 기본값은 `unread`다.

#### Scenario: 기본 상태
- **WHEN** 상태를 지정하지 않고 owner_messages 레코드를 저장하면
- **THEN** 상태는 `unread`가 된다

#### Scenario: 허용되지 않은 상태
- **WHEN** owner_messages에 상태 `deleted`로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

### Requirement: 매장에 없는 책 주문 요청
시스템은 손님의 주문 요청을 제목, 저자(선택), ISBN(선택), 연락처, 처리 상태와 함께 저장 SHALL 한다. 연락처는 필수다. 처리 상태는 `received`, `ordered`, `notified`, `closed` 중 하나이고 기본값은 `received`다. ISBN이 있으면 도서 목록의 도서를 가리켜야 한다.

#### Scenario: 기본 상태
- **WHEN** 상태를 지정하지 않고 book_requests 레코드를 저장하면
- **THEN** 상태는 `received`가 된다

#### Scenario: 연락처 누락
- **WHEN** 연락처 없이 book_requests 레코드를 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: ISBN을 확정하지 못한 요청
- **WHEN** 검색으로 ISBN을 확정하지 못해 제목(과 알 수 있는 저자)만으로 주문 요청을 남기면
- **THEN** ISBN이 비어 있는 상태로 저장되고, 제목과 연락처는 보존된다
