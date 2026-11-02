# supply/quote-drafts Specification

## Purpose

기관 납품 에이전트(C)가 만든 견적서 초안을 금액과 승인 상태와 함께 보관해, 사장님 승인을 거친 견적서만 기관에 보낼 수 있게 한다.

## Requirements

### Requirement: 견적서 승인 상태
견적서의 상태는 `draft`, `pending_approval`, `approved`, `sent` 중 하나만 MUST 허용하고, 새 레코드의 기본값은 `draft`다. 견적서는 반드시 하나의 기관에 속한다.

#### Scenario: 기본 상태
- **WHEN** 상태를 지정하지 않고 quote_drafts 레코드를 저장하면
- **THEN** 상태는 `draft`가 된다

#### Scenario: 허용되지 않은 상태
- **WHEN** quote_drafts에 상태 `paid`로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

### Requirement: 견적 금액 저장 형식
견적서의 금액(공급가 합계, 할인액, 최종 금액)은 0 이상의 정수(원 단위)로만 MUST 저장한다.

#### Scenario: 음수 할인액
- **WHEN** quote_drafts에 할인액 -500으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
