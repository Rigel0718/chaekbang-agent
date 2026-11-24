## ADDED Requirements

### Requirement: 주제로 찾기 API
직원 토큰으로 `GET /catalog/topic?q=`를 SHALL 쓸 수 있다. 키오스크 계정도 쓸 수 있고 기관은 토큰으로 정한다. 질의는 1자 이상 100자 이하다. 시스템은 질의를 공백으로 나눈 낱말로 제품 경로의 주제로 찾기를 부르고(순위, 내려가기, 범위 규칙은 제품 경로와 같다), 결과 항목은 서명·저자 찾기 결과와 같은 값이며 최대 10권이다. 비교용으로 정리한 뒤 남는 낱말이 없으면 둘러보기 대신 빈 목록이고 인코더를 부르지 않는다. LLM을 부르지 않는다.

#### Scenario: 제품 경로와 같은 결과
- **WHEN** 키오스크 토큰으로 `GET /catalog/topic?q=채식 소설`을 호출하면
- **THEN** 200이고, 결과가 같은 기관·같은 인코더로 낱말 `채식`, `소설`의 제품 경로 주제로 찾기를 부른 결과와 같은 책, 같은 순서다

#### Scenario: 인코더가 실패함
- **WHEN** 질의 인코딩이 실패하는 상태에서 호출하면
- **THEN** 200이고, 결과가 같은 낱말의 키워드 순위와 같은 책, 같은 순서다

#### Scenario: 낱말 없음
- **WHEN** 공백과 문장부호만 있는 질의로 호출하면
- **THEN** 200과 빈 목록을 돌려주고 인코더를 부르지 않는다

#### Scenario: 토큰 없음
- **WHEN** 토큰 없이 `GET /catalog/topic?q=채식`을 호출하면
- **THEN** 401을 돌려준다

#### Scenario: 잘못된 질의
- **WHEN** `q`가 비어 있거나 100자를 넘으면
- **THEN** 422를 돌려준다

#### Scenario: 요청의 기관 값 무시
- **WHEN** A 기관 토큰으로, B 기관에만 있는 책의 낱말과 `library_id`에 B 기관 id를 붙여 호출하면
- **THEN** B 기관의 책이 나오지 않는다

### Requirement: 주제로 찾기 API는 기록을 남기지 않음
주제로 찾기 API는 질의를 MUST NOT 저장한다. 실행 기록, 대화 기록, 노출 기록을 만들지 않는다.

#### Scenario: 호출 후 기록
- **WHEN** `GET /catalog/topic`을 호출하면
- **THEN** agent_runs, chat_messages, recommendation_events 행 수가 바뀌지 않는다
