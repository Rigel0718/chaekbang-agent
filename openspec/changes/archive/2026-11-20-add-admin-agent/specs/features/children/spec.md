## ADDED Requirements

### Requirement: 어린이 분석 축
어린이 기능은 분석 축 `audience`를 SHALL 등록한다. 값은 `children`과 `general`이고 기본값은 `general`이다. 그 기관에서 어린이 도서로 구분된 책만 `children`에 배정하고, 구분이 없거나 확실하지 않은 책은 `general`로 센다. 결과의 `general`은 "어린이로 분류되지 않음"으로 표시한다.

#### Scenario: 어린이와 일반의 합
- **WHEN** 어린이 도서 2권과 구분 행이 없는 책 3권이 있을 때 장서 현황을 어린이 축으로 묶으면
- **THEN** `children` 2, `general` 3이고 합이 전체와 같다

#### Scenario: 다른 기관의 어린이 구분
- **WHEN** B 기관에서만 어린이 도서인 책이 A 기관에도 있을 때 A 기관에서 어린이 축으로 묶으면
- **THEN** 그 책은 A 기관에서 `general`이다

#### Scenario: 어린이 대출
- **WHEN** 어린이 도서 대출 2건과 일반 도서 대출 1건이 기간 안에 있을 때 대출 통계를 어린이 축으로 묶으면
- **THEN** `children` 2, `general` 1이다

### Requirement: 운영 에이전트 어린이 문구
어린이 기능은 운영 에이전트 프롬프트에 어린이 축을 쓰는 문구를 SHALL 넘긴다. 아동·어린이·그림책 질문은 `children`, 어른 책·일반 책 질문은 `general`로 거르고, 답에는 그 기관의 어린이 구분 기준임을 밝힌다. 기능을 빼면 문구도 빠진다.

#### Scenario: 기능 없는 프롬프트
- **WHEN** 어린이 기능 없이 운영 에이전트 프로필을 조립하면
- **THEN** 시스템 프롬프트에 어린이 축 문구가 없고 tool 입력 스키마에 `audience`가 없다
