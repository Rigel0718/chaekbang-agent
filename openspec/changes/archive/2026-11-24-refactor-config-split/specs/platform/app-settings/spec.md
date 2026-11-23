# Spec Delta

## Purpose

서버와 스크립트가 설정을 읽는 규칙을 정한다. 비밀과 설치마다 다른 값은 `.env`에서, 제품 정책값은 코드에서 읽어, 환경 파일이 정책을 몰래 바꾸지 못하게 한다.

## ADDED Requirements

### Requirement: 환경 값과 코드값 분리
`.env`와 환경변수에서는 환경 필드(DB 접속, 외부 API 키, 시드 비밀번호, 임베딩 서버 주소, 질의 인코딩 켜기)만 SHALL 읽는다. 그 밖의 필드는 코드 기본값을 쓰고, 같은 이름의 환경변수나 `.env` 키가 있어도 MUST NOT 반영하며 오류도 내지 않는다. 설정을 만들 때 직접 준 값은 모든 필드에 반영한다(테스트·평가용).

#### Scenario: 정책 필드는 환경변수를 무시한다
- **WHEN** 환경 필드가 아닌 모든 필드마다 같은 이름의 환경변수에 기본값과 다른 값을 두고 설정을 읽으면
- **THEN** 그 필드들은 모두 코드 기본값이다

#### Scenario: 옛 키가 든 `.env`
- **WHEN** `.env`에 정책 키와 없어진 키(`EMBEDDING_DIM`)가 들어 있는 채 설정을 읽으면
- **THEN** 오류 없이 읽고 그 값들은 반영하지 않는다

#### Scenario: 환경 필드는 환경변수를 읽는다
- **WHEN** `DATABASE_URL`과 `EMBEDDING_QUERY_ENABLED`를 환경변수로 두고 설정을 읽으면
- **THEN** 그 값이 설정에 반영된다

#### Scenario: 직접 준 값
- **WHEN** 설정을 만들면서 `llm_model`을 직접 주면
- **THEN** 그 값이 반영된다

### Requirement: `.env.example`과 환경 필드의 일치
`.env.example`에 적힌 키는 환경 필드 전부와, 앱이 읽지 않고 `docker-compose.yml`만 읽는 키(`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `EMBEDDING_PORT`)로 MUST 이루어진다. 정책 필드의 키는 적지 않는다.

#### Scenario: 키 집합 비교
- **WHEN** `.env.example`의 키를 모으면
- **THEN** 환경 필드 전부가 들어 있고, 그 밖의 키는 compose가 읽는 키뿐이다

### Requirement: 임베딩 서버와 같은 모델·입력 한도
임베딩 모델 이름과 입력 한도는 앱 설정과 `docker-compose.yml`의 임베딩 서버가 MUST 같은 값을 쓰고, compose는 값을 환경변수 치환이 아닌 리터럴로 적는다. 벡터 차원은 벡터 열을 정의하는 스키마 상수 하나만 쓴다.

#### Scenario: compose와 설정이 같다
- **WHEN** `docker-compose.yml`의 임베딩 서버 환경을 읽으면
- **THEN** 모델 이름과 입력 한도가 치환 없는 값이고 설정의 기본값과 같다

#### Scenario: 인코더 차원
- **WHEN** 임베딩 인코더를 만들면
- **THEN** 차원은 벡터 열의 스키마 상수와 같다
