# Spec Delta

## MODIFIED Requirements

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 테이블 15개(libraries, staff_users, staff_sessions, books, library_books, library_book_audiences, holdings, holding_imports, members, loans, agent_runs, agent_steps, chat_sessions, chat_messages, recommendation_events)와 문자열 유사도 확장, 한글 자모 분해 SQL 함수, chat_messages의 책 표시 칸, books와 library_books의 서명·저자 찾기 키 열을 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다. 자모 분해 SQL 함수는 코드의 자모 분해 규칙과 같은 결과를 낸다. 찾기 키 열은 DB가 서명·저자에서 계산하는 생성 열이라 코드가 쓰지 않는다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 15개 테이블과 문자열 유사도 확장, 자모 분해 함수가 모두 존재한다

#### Scenario: downgrade 후 재적용
- **WHEN** `alembic downgrade base` 후 다시 `alembic upgrade head`를 실행하면
- **THEN** 오류 없이 같은 테이블 구성이 만들어진다

#### Scenario: 모델과 마이그레이션 일치
- **WHEN** 마이그레이션을 적용한 DB와 코드의 모델 정의를 비교하면
- **THEN** 자동 생성할 차이(autogenerate diff)가 없다

#### Scenario: 대화 메시지의 책 표시 칸
- **WHEN** 마이그레이션을 적용한 DB의 chat_messages 열을 확인하면
- **THEN** 비어 있을 수 있는 책 표시 칸이 있고, 기존 행의 값은 비어 있다

#### Scenario: 찾기 키 열의 자동 계산
- **WHEN** 기관 도서의 서명을 고치면
- **THEN** 그 행의 서명 찾기 키가 코드 규칙으로 계산한 새 서명의 키와 같다

#### Scenario: 자모 분해 규칙 일치
- **WHEN** 겹받침, 이중 모음, 조합 중인 자모, 영문, 숫자가 섞인 문자열들을 코드 규칙과 SQL 함수로 각각 분해하면
- **THEN** 모든 문자열에서 결과가 같다
