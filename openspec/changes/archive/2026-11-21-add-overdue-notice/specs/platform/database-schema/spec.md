## MODIFIED Requirements

### Requirement: 마이그레이션으로 스키마 생성
시스템은 빈 PostgreSQL 데이터베이스에 마이그레이션을 적용하면 테이블 25개(libraries, staff_users, staff_sessions, books, book_contributors, official_book_embeddings, library_books, library_book_audiences, holdings, holding_imports, members, loans, agent_runs, agent_steps, chat_sessions, chat_messages, recommendation_events, library_guides, library_opening_hours, library_closures, library_guide_entries, book_embeddings, curations, curation_items, overdue_notice_templates)와 문자열 유사도 확장, 벡터 확장, 한글 자모 분해 SQL 함수, chat_messages의 책 표시 칸과 책 id 칸, books와 library_books의 서명·저자 찾기 키 열, library_books의 저자 키 열, books의 시리즈 키 열을 모두 생성 SHALL 하고, 되돌린 뒤 다시 적용할 수 있어야 한다. 자모 분해 SQL 함수는 코드의 자모 분해 규칙과 같은 결과를 낸다. 찾기 키 열은 DB가 서명·저자에서 계산하는 생성 열이라 코드가 쓰지 않는다. 저자 키 열은 코드가 저장할 때 계산하는 열이고 비워 둘 수 없다(빈 목록은 된다). 시리즈 키 열은 코드가 저장할 때 계산하는 열이고 주지 않으면 빈 목록이다. chat_messages의 책 id 칸은 코드가 저장할 때 정하는 기관 도서 id 목록이고 비워 둘 수 없으며 주지 않으면 빈 목록이다. official_book_embeddings와 book_embeddings의 벡터 열은 1024차원이고 종류 칸은 비어 있을 수 없다. official_book_embeddings는 같은 공식 서지·모델 이름·텍스트 버전·종류의 행을, book_embeddings는 같은 기관 도서·모델 이름·텍스트 버전·종류의 행을 하나만 둘 수 있다. book_contributors는 같은 공식 서지에 같은 순서의 행을 하나만 둘 수 있고 이름과 이름 맞춤 키는 비어 있을 수 없다. curation_items는 같은 기관의 큐레이션과 기관 도서만 가리킨다. members의 전화번호 칸은 비어 있을 수 있다. overdue_notice_templates의 문장은 비어 있을 수 없다.

#### Scenario: 빈 DB에 upgrade
- **WHEN** 빈 데이터베이스에 `alembic upgrade head`를 실행하면
- **THEN** 25개 테이블과 문자열 유사도 확장, 벡터 확장, 자모 분해 함수가 모두 존재한다

#### Scenario: downgrade 후 재적용
- **WHEN** `alembic downgrade base` 후 다시 `alembic upgrade head`를 실행하면
- **THEN** 오류 없이 같은 테이블 구성이 만들어진다

#### Scenario: 모델과 마이그레이션 일치
- **WHEN** 마이그레이션을 적용한 DB와 코드의 모델 정의를 비교하면
- **THEN** 자동 생성할 차이(autogenerate diff)가 없다

#### Scenario: 대화 메시지의 책 표시 칸
- **WHEN** 마이그레이션을 적용한 DB의 chat_messages 열을 확인하면
- **THEN** 비어 있을 수 있는 책 표시 칸이 있고, 기존 행의 값은 비어 있다

#### Scenario: 대화 메시지의 책 id 칸
- **WHEN** 메시지 행이 있는 DB에 마이그레이션을 적용한 뒤 chat_messages 열을 확인하면
- **THEN** 비어 있을 수 없는 책 id 칸이 있고, 기존 행의 값은 빈 목록이다

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
- **WHEN** book_embeddings에 같은 기관 도서·모델 이름·텍스트 버전·종류의 행 두 개를, 1024차원이 아닌 벡터를, 종류가 빈 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 셋 다 거부한다

#### Scenario: 종류가 다른 기관 도서 벡터
- **WHEN** book_embeddings에 같은 기관 도서·모델 이름·텍스트 버전이고 종류만 다른 행 두 개를 직접 저장하면
- **THEN** 둘 다 저장된다

#### Scenario: 공식 서지 임베딩 테이블의 저장 계층 규칙
- **WHEN** official_book_embeddings에 같은 공식 서지·모델 이름·텍스트 버전·종류의 행 두 개를, 1024차원이 아닌 벡터를, 없는 공식 서지를 가리키는 행을, 종류가 빈 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 넷 다 거부한다

#### Scenario: 공식 서지를 지우면 벡터도 지워짐
- **WHEN** 어느 기관 도서도 가리키지 않는 공식 서지를 DB에서 직접 지우면
- **THEN** 그 공식 서지의 벡터 행도 함께 지워진다

#### Scenario: 기여자 테이블의 저장 계층 규칙
- **WHEN** book_contributors에 같은 공식 서지·같은 순서의 행 두 개를, 이름이 빈 행을, 없는 공식 서지를 가리키는 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 셋 다 거부한다

#### Scenario: 저자 키 없는 기관 도서 직접 저장
- **WHEN** library_books에 저자 키를 주지 않고 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 시리즈 키 없는 공식 서지 직접 저장
- **WHEN** books에 시리즈 키를 주지 않고 행을 직접 저장하면
- **THEN** 저장되고 그 행의 시리즈 키가 빈 목록이다

#### Scenario: 찾기 키 열의 전각·분해형 처리
- **WHEN** 기관 도서의 서명을 전각 영문이나 분해형 한글로 저장하면
- **THEN** 그 행의 서명 찾기 키가 반각·완성형으로 적은 같은 서명의 키와 같다

#### Scenario: 큐레이션 포함 도서의 기관
- **WHEN** A 기관 큐레이션의 포함 도서로 B 기관의 기관 도서를 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 회원 전화번호 칸
- **WHEN** 회원 행이 있는 DB에 마이그레이션을 적용한 뒤 members 열을 확인하면
- **THEN** 비어 있을 수 있는 전화번호 칸이 있고, 기존 행의 값은 비어 있다

#### Scenario: 안내문 틀의 저장 계층 규칙
- **WHEN** overdue_notice_templates에 문장이 빈 행을, 상태 `rejected`인 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 둘 다 거부한다
