## MODIFIED Requirements

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 테이블 20개(libraries, staff_users, staff_sessions, books, library_books, library_book_audiences, holdings, holding_imports, members, loans, agent_runs, agent_steps, chat_sessions, chat_messages, recommendation_events, library_guides, library_opening_hours, library_closures, library_guide_entries, book_embeddings)와 문자열 유사도 확장, 벡터 확장, 한글 자모 분해 SQL 함수, chat_messages의 책 표시 칸, books와 library_books의 서명·저자 찾기 키 열을 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다. 자모 분해 SQL 함수는 코드의 자모 분해 규칙과 같은 결과를 낸다. 찾기 키 열은 DB가 서명·저자에서 계산하는 생성 열이라 코드가 쓰지 않는다. book_embeddings의 벡터 열은 1024차원이고, 같은 기관 도서·모델 이름·텍스트 버전의 행은 하나만 둘 수 있다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 20개 테이블과 문자열 유사도 확장, 벡터 확장, 자모 분해 함수가 모두 존재한다

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

#### Scenario: 안내 테이블의 저장 계층 규칙
- **WHEN** library_opening_hours에 닫는 시각이 여는 시각보다 앞인 행을, library_closures에 같은 기관·같은 날짜 행 두 개를 직접 저장하려 하면
- **THEN** 데이터베이스가 둘 다 거부한다

#### Scenario: 임베딩 테이블의 저장 계층 규칙
- **WHEN** book_embeddings에 같은 기관 도서·모델 이름·텍스트 버전의 행 두 개를, 그리고 1024차원이 아닌 벡터를 직접 저장하려 하면
- **THEN** 데이터베이스가 둘 다 거부한다

### Requirement: 기관 간 참조 금지
기관 데이터 테이블 사이의 참조는 같은 기관의 행만 MUST 가리킨다. 사본과 어린이 구분, 임베딩은 같은 기관의 기관 도서만, 대출은 같은 기관의 사본과 회원만, 실행 단계는 같은 기관의 실행만, 대화 메시지는 같은 기관의 세션만, 노출 기록은 같은 기관의 기관 도서와 실행만 가리킬 수 있고, 저장 계층에서도 이를 강제한다.

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

#### Scenario: 다른 기관 도서로 임베딩 직접 저장
- **WHEN** A 기관의 임베딩 행에 B 기관의 기관 도서를 가리키도록 book_embeddings에 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다
