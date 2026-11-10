# agent/recommendation-events Specification

## Purpose

이용자에게 실제로 보인 추천을 기록한다. 추천 품질과 대출 전환을 나중에 측정할 근거가 되고, 누가 봤는지는 남기지 않는다.

## Requirements

### Requirement: 노출 기록
시스템은 답으로 보낸 추천마다 기관, 기관 도서, 실행, 순서, 노출 시점의 대출 가능 여부, 노출 시각을 `recommendation_events`에 SHALL 기록한다.

#### Scenario: 추천 두 권
- **WHEN** 답에 두 권이 나가면
- **THEN** 순서가 1, 2인 행 두 개가 있고 같은 실행을 가리킨다

#### Scenario: 대출 가능 여부
- **WHEN** 대출 중인 책이 나가면
- **THEN** 그 행의 대출 가능 여부는 거짓이다

### Requirement: 보인 추천만 기록
검사를 통과해 나간 추천만 MUST 기록한다.

#### Scenario: 위반한 추천
- **WHEN** 위반한 답 뒤에 고친 답이 나가면
- **THEN** 고친 답의 책만 행이 있다

#### Scenario: 고정 답
- **WHEN** 고정 답이 나가면
- **THEN** 행이 없다

### Requirement: 기록하지 않는 값
노출 기록에 회원, 세션, 이용자 문장, 추천 이유, 어린이 구분을 MUST NOT 둔다.

#### Scenario: 세션과 잇지 않음
- **WHEN** 노출 행의 열을 확인하면
- **THEN** 회원, 세션, 문장, 이유, 어린이 구분 열이 없다

### Requirement: 기관 도서 삭제와의 관계
노출 기록은 기관 도서 삭제를 MUST NOT 막는다. 기관 도서를 지우면 그 노출 기록도 지운다.

#### Scenario: 사본 없는 도서 삭제
- **WHEN** 노출 기록이 있고 사본이 없는 기관 도서를 지우면
- **THEN** 삭제되고 그 노출 행도 없다
