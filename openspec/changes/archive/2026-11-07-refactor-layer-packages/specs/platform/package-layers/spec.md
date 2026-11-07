# Spec Delta

## Purpose

운영자 층, 기관 공통, 기관 개별 기능의 경계를 패키지와 테스트로 지켜, 한 층의 변경이 다른 층의 값을 조용히 바꾸지 못하게 한다.

## ADDED Requirements

### Requirement: 패키지 의존 방향
앱 코드는 `app/features`, `app/library`, `app/central`, `app/core` 순서로만 MUST 의존한다. 아래 층은 위 층을 import하지 않는다. 층을 조립하는 `app/main.py`, `app/models.py`, `app/seed/`, `scripts/`, `evals/`는 어느 층이든 import할 수 있다.

#### Scenario: 거꾸로 된 import 금지
- **WHEN** 앱 코드의 import를 검사하면
- **THEN** `core`는 `central`·`library`·`features`를, `central`은 `library`·`features`를, `library`는 `features`를 import하지 않는다

### Requirement: 기관 개별 기능 없는 공통 동작
기관 공통 기능은 기관 개별 기능을 등록하지 않아도 MUST 동작한다. 공통 코드는 기능을 이름으로 부르지 않고, 연결 변경과 파일 행 적용을 등록된 기능에 알린다.

#### Scenario: 기능 없이 등록과 가져오기
- **WHEN** 등록된 기관 개별 기능이 없는 상태에서 기관 도서를 등록하고 파일을 적용하면
- **THEN** 기관 도서와 사본이 만들어지고 library_book_audiences에는 행이 없다

#### Scenario: 공통 응답에 어린이 값 없음
- **WHEN** `GET /library-books/{id}`를 호출하면
- **THEN** 응답에 `audience`와 `audience_source`가 없다

### Requirement: 운영자 층의 경계
운영자 층은 기관 모델을 MUST NOT 쓴다. 채움 실행의 대상 조회와 연결 처리는 운영자 층이 정의한 접점을 기관 공통이 구현하고, 실행 스크립트가 둘을 잇는다.

#### Scenario: 운영자 코드의 기관 모델 참조 없음
- **WHEN** `app/central/`의 코드를 검사하면
- **THEN** `LibraryBook`, `Holding`을 참조하지 않는다
