# platform/database-schema Specification

## Purpose

테이블을 기관 공통 테이블과 기관 데이터 테이블로 나누고, 기관 사이의 참조를 저장 계층에서 막으며, 마이그레이션으로 스키마를 만들고 되돌릴 수 있게 한다.

## Requirements

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 테이블 15개(libraries, staff_users, staff_sessions, books, library_books, library_book_audiences, holdings, holding_imports, members, loans, agent_runs, agent_steps, chat_sessions, chat_messages, recommendation_events)를 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 15개 테이블이 모두 존재한다

#### Scenario: downgrade 후 재적용
- **WHEN** `alembic downgrade base` 후 다시 `alembic upgrade head`를 실행하면
- **THEN** 오류 없이 같은 테이블 구성이 만들어진다

#### Scenario: 모델과 마이그레이션 일치
- **WHEN** 마이그레이션을 적용한 DB와 코드의 모델 정의를 비교하면
- **THEN** 자동 생성할 차이(autogenerate diff)가 없다

### Requirement: 기관 데이터 테이블 구분
모든 테이블은 기관 공통 테이블과 기관 데이터 테이블 중 정확히 하나에 MUST 속한다.
- 기관 공통 테이블: libraries, books
- 기관 데이터 테이블: 그 밖의 모든 테이블. NULL이 될 수 없는 `library_id` 컬럼과 libraries를 가리키는 외래 키를 가진다.

#### Scenario: 구분되지 않은 테이블
- **WHEN** 마이그레이션을 적용한 DB의 테이블 목록을 두 구분과 비교하면
- **THEN** 어디에도 속하지 않거나 둘 다에 속한 테이블이 없다

#### Scenario: library_id 누락
- **WHEN** 기관 데이터 테이블의 컬럼을 확인하면
- **THEN** 모두 NULL이 될 수 없는 `library_id`와 libraries 외래 키를 가진다

### Requirement: 기관 간 참조 금지
기관 데이터 테이블 사이의 참조는 같은 기관의 행만 MUST 가리킨다. 사본과 어린이 구분은 같은 기관의 기관 도서만, 대출은 같은 기관의 사본과 회원만, 실행 단계는 같은 기관의 실행만, 대화 메시지는 같은 기관의 세션만, 노출 기록은 같은 기관의 기관 도서와 실행만 가리킬 수 있고, 저장 계층에서도 이를 강제한다.

#### Scenario: 다른 기관 도서로 사본 직접 저장
- **WHEN** A 기관의 사본 행에 B 기관의 기관 도서를 가리키도록 holdings에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 도서로 어린이 구분 직접 저장
- **WHEN** A 기관의 어린이 구분 행에 B 기관의 기관 도서를 가리키도록 library_book_audiences에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 사본으로 대출 직접 저장
- **WHEN** A 기관의 대출 행에 B 기관 사본을 가리키도록 loans에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 회원으로 대출 직접 저장
- **WHEN** A 기관의 대출 행에 B 기관 회원을 가리키도록 loans에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 실행으로 단계 직접 저장
- **WHEN** A 기관의 실행 단계 행에 B 기관의 실행을 가리키도록 agent_steps에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 세션으로 메시지 직접 저장
- **WHEN** A 기관의 메시지 행에 B 기관의 세션을 가리키도록 chat_messages에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 도서로 노출 기록 직접 저장
- **WHEN** A 기관의 노출 행에 B 기관의 기관 도서를 가리키도록 recommendation_events에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 실행으로 노출 기록 직접 저장
- **WHEN** A 기관의 노출 행에 B 기관의 실행을 가리키도록 recommendation_events에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
