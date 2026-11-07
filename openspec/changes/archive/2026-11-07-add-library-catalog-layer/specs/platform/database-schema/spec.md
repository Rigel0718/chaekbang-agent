# Spec Delta

## MODIFIED Requirements

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 테이블 9개(libraries, staff_users, staff_sessions, books, library_books, holdings, holding_imports, members, loans)를 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 9개 테이블이 모두 존재한다

#### Scenario: downgrade 후 재적용
- **WHEN** `alembic downgrade base` 후 다시 `alembic upgrade head`를 실행하면
- **THEN** 오류 없이 같은 테이블 구성이 만들어진다

#### Scenario: 모델과 마이그레이션 일치
- **WHEN** 마이그레이션을 적용한 DB와 코드의 모델 정의를 비교하면
- **THEN** 자동 생성할 차이(autogenerate diff)가 없다

### Requirement: 기관 간 참조 금지
기관 데이터 테이블 사이의 참조는 같은 기관의 행만 MUST 가리킨다. 사본은 같은 기관의 기관 도서만, 대출은 같은 기관의 사본과 회원만 가리킬 수 있고, 저장 계층에서도 이를 강제한다.

#### Scenario: 다른 기관 도서로 사본 직접 저장
- **WHEN** A 기관의 사본 행에 B 기관의 기관 도서를 가리키도록 holdings에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 사본으로 대출 직접 저장
- **WHEN** A 기관의 대출 행에 B 기관 사본을 가리키도록 loans에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 다른 기관 회원으로 대출 직접 저장
- **WHEN** A 기관의 대출 행에 B 기관 회원을 가리키도록 loans에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
