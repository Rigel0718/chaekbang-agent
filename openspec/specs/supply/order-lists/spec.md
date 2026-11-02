# supply/order-lists Specification

## Purpose

기관 납품 에이전트(C)가 기관에서 받은 도서 목록을 행 단위 원문 그대로 보관하고, 각 행의 ISBN 매칭 결과와 사람 확인 상태를 기록할 수 있게 한다.

## Requirements

### Requirement: 납품 목록과 기관 연결
납품 목록은 반드시 하나의 기관에 MUST 속한다. 목록의 진행 상태는 `uploaded`, `matching`, `reviewing`, `quoted` 중 하나이고 기본값은 `uploaded`다.

#### Scenario: 기관 없는 목록
- **WHEN** institutions에 없는 기관 id로 institution_orders를 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 기본 진행 상태
- **WHEN** 상태를 지정하지 않고 institution_orders 레코드를 저장하면
- **THEN** 상태는 `uploaded`가 된다

### Requirement: 목록 행 원문 보존과 매칭 상태
목록의 각 행은 업로드 원문(제목, 저자, 출판사, ISBN, 권차 표기)과 수량을 매칭 결과와 별도로 SHALL 보관한다. 수량은 1 이상이다. 매칭 확인 상태는 `unmatched`, `auto_matched`, `needs_confirmation`, `confirmed`, `rejected` 중 하나이고 기본값은 `unmatched`다. 신뢰도는 0 이상 1 이하다. 매칭 ISBN이 있으면 도서 목록의 도서를 가리켜야 한다.

#### Scenario: 매칭 전 행
- **WHEN** 원문 제목과 수량만으로 order_items 레코드를 저장하면
- **THEN** 매칭 ISBN은 비어 있고 확인 상태는 `unmatched`가 된다

#### Scenario: 허용되지 않은 확인 상태
- **WHEN** order_items에 확인 상태 `maybe`로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 범위를 벗어난 신뢰도
- **WHEN** order_items에 신뢰도 1.5로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 수량 0
- **WHEN** order_items에 수량 0으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
