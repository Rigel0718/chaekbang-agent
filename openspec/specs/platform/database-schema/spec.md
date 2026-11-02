# platform/database-schema Specification

## Purpose

세 에이전트(매장 큐레이터, 사장님 운영, 기관 납품)가 쓰는 테이블을 도메인 컨텍스트별로 나누고, 컨텍스트 사이의 참조 방향과 마이그레이션 규칙을 정해 한 컨텍스트의 변경이 다른 컨텍스트로 번지지 않게 한다.

## Requirements

### Requirement: 컨텍스트별 테이블 소유
모든 테이블은 정확히 하나의 컨텍스트에 MUST 속한다. catalog: books, store_inventory / storefront(A): chat_logs, owner_messages, book_requests / owner-ops(B): curations, quotes / supply(C): institutions, institution_orders, order_items, quote_drafts.

#### Scenario: 소유 컨텍스트가 없는 테이블
- **WHEN** 마이그레이션을 적용한 DB의 테이블 목록을 컨텍스트별 소유 목록과 비교하면
- **THEN** 어느 컨텍스트에도 속하지 않거나 둘 이상에 속한 테이블이 없다

### Requirement: 컨텍스트 간 참조 방향
storefront, owner-ops, supply 테이블은 catalog 테이블만 외래 키로 참조할 수 있고, 서로를 직접 참조하지 MUST 않는다. catalog 테이블은 다른 컨텍스트의 테이블을 참조하지 않는다.

#### Scenario: 외래 키 방향 점검
- **WHEN** DB의 모든 외래 키를 컨텍스트별로 분류하면
- **THEN** 서로 다른 컨텍스트 사이의 외래 키는 모두 catalog 테이블을 가리킨다

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 네 컨텍스트의 테이블 11개를 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 11개 테이블이 모두 존재한다

#### Scenario: downgrade 후 재적용
- **WHEN** `alembic downgrade base` 후 다시 `alembic upgrade head`를 실행하면
- **THEN** 오류 없이 같은 테이블 구성이 만들어진다

#### Scenario: 모델과 마이그레이션 일치
- **WHEN** 마이그레이션을 적용한 DB와 코드의 모델 정의를 비교하면
- **THEN** 자동 생성할 차이(autogenerate diff)가 없다
