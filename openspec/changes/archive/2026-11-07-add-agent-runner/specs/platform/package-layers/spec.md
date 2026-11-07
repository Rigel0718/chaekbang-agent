# Spec Delta

## MODIFIED Requirements

### Requirement: 패키지 의존 방향
앱 코드는 `app/features`, `app/library`, `app/central`, `app/core` 순서로만 MUST 의존한다. 아래 층은 위 층을 import하지 않는다. `app/agent`는 `app/core`만 의존하고, `central`, `library`, `features`는 `app/agent`를 import할 수 있다. `app/core`는 `app/agent`를 import하지 않는다. 층을 조립하는 `app/main.py`, `app/models.py`, `app/seed/`, `scripts/`, `evals/`는 어느 층이든 import할 수 있다.

#### Scenario: 거꾸로 된 import 금지
- **WHEN** 앱 코드의 import를 검사하면
- **THEN** `core`는 `agent`·`central`·`library`·`features`를, `central`은 `library`·`features`를, `library`는 `features`를 import하지 않는다

#### Scenario: 실행기의 import 제한
- **WHEN** `app/agent/`의 코드를 검사하면
- **THEN** `central`·`library`·`features`를 import하지 않는다

## ADDED Requirements

### Requirement: 공통 실행기의 경계
공통 실행기는 기관 코드와 특정 tool을 MUST NOT 알아야 한다. 기관 패키지를 불러오지 않고, 가짜 tool과 가짜 LLM만으로 동작한다.

#### Scenario: 실행기만 불러오기
- **WHEN** 새 프로세스에서 실행기만 import하면
- **THEN** `app.central`, `app.library`, `app.features`의 모듈이 불려 있지 않다

#### Scenario: 가짜 tool로 실행
- **WHEN** 가짜 tool과 가짜 LLM으로 프로필을 만들어 실행하면
- **THEN** 기관 패키지의 service 없이 최종 답까지 끝난다
