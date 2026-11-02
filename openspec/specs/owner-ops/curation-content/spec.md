# owner-ops/curation-content Specification

## Purpose

사장님 운영 에이전트(B)가 만든 오늘의 추천·추천 카드 초안과 사장님이 등록한 글귀를 승인 상태와 함께 보관해, 승인된 콘텐츠만 매장 화면에 게시될 수 있게 한다.

## Requirements

### Requirement: 추천 콘텐츠의 승인 상태
추천 콘텐츠의 상태는 `draft`, `pending_approval`, `approved`, `published` 중 하나만 MUST 허용하고, 새 레코드의 기본값은 `draft`다. 추천 종류는 `today_pick`(오늘의 추천), `recommendation_card`(추천 카드) 중 하나다.

#### Scenario: 기본 상태
- **WHEN** 상태를 지정하지 않고 curations 레코드를 저장하면
- **THEN** 상태는 `draft`가 된다

#### Scenario: 허용되지 않은 상태
- **WHEN** curations에 상태 `deleted`로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 허용되지 않은 종류
- **WHEN** curations에 종류 `banner`로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

### Requirement: 사장님이 등록한 글귀
시스템은 글귀를 본문, 출처 도서(선택), 출처 메모(선택), 사용 여부와 함께 저장 SHALL 한다. 본문은 비어 있을 수 없고, 사용 여부의 기본값은 사용(true)이다. 출처 도서가 있으면 도서 목록의 도서를 가리켜야 한다.

#### Scenario: 빈 본문
- **WHEN** quotes에 빈 문자열 본문으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 없는 출처 도서
- **WHEN** books에 없는 ISBN을 출처 도서로 quotes에 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
