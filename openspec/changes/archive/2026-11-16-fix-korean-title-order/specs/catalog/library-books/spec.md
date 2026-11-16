## MODIFIED Requirements

### Requirement: 기관 도서 단건과 목록 조회
시스템은 내부 id로 단건 조회와 페이지 단위 목록 조회를 SHALL 제공하고, 로그인한 기관의 기관 도서만 돌려준다.
- 목록은 `limit`(기본 20, 최대 100)과 `offset`을 받고, 전체 건수를 함께 반환한다.
- 목록은 `isbn`으로 거를 수 있다.
- 각 도서에는 소장 권수와 대출 가능 권수를 붙인다. 제적 사본은 세지 않는다.
- `held=true`로 제적이 아닌 사본이 있는 도서만 거를 수 있다.
- 목록은 표시 서명의 서명 정렬 순서, 같으면 내부 id 순이다.

#### Scenario: 단건 조회
- **WHEN** 등록된 기관 도서의 id로 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 200과 도서 정보를 반환한다

#### Scenario: 없는 도서 조회
- **WHEN** 없는 id로 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 다른 기관 도서 조회
- **WHEN** B 기관의 기관 도서 id로 A 기관 직원이 `GET /library-books/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 목록에 다른 기관 도서 없음
- **WHEN** 두 기관에 기관 도서가 있고 A 기관 직원이 `GET /library-books`를 호출하면
- **THEN** A 기관의 도서만 돌려준다

#### Scenario: 목록 페이지네이션
- **WHEN** 기관 도서 25권이 있는 상태에서 `GET /library-books?limit=10&offset=20`을 호출하면
- **THEN** 시스템은 5건의 항목과 전체 건수 25를 반환한다

#### Scenario: limit 상한 초과
- **WHEN** `GET /library-books?limit=101`을 호출하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 없는 ISBN으로 거르기
- **WHEN** 등록되지 않은 ISBN으로 `GET /library-books?isbn={isbn}`을 호출하면
- **THEN** 시스템은 200과 빈 목록, 전체 건수 0을 반환한다

#### Scenario: 소장 권수
- **WHEN** 사본 2권(그중 1권 대출 중)이 있는 기관 도서를 조회하면
- **THEN** 소장 권수 2, 대출 가능 권수 1을 돌려준다

#### Scenario: 소장 도서만 거르기
- **WHEN** `GET /library-books?held=true`를 호출하면
- **THEN** 제적이 아닌 사본이 하나 이상 있는 기관 도서만 돌려준다

#### Scenario: 제적 사본은 소장이 아님
- **WHEN** 제적 사본만 있는 기관 도서를 `GET /library-books?held=true`로 조회하면
- **THEN** 그 도서는 들어 있지 않고, 단건 조회의 소장 권수는 0이다

#### Scenario: 목록은 가나다순
- **WHEN** 서명이 `하늘`, `가나다`, `나비`인 기관 도서가 있는 상태에서 `GET /library-books`를 호출하면
- **THEN** `가나다`, `나비`, `하늘` 순서로 돌려준다

#### Scenario: 목록에 숫자·한글·영문
- **WHEN** 서명이 `ABC 동화`, `하늘`, `10대`인 기관 도서가 있는 상태에서 `GET /library-books`를 호출하면
- **THEN** `10대`, `하늘`, `ABC 동화` 순서로 돌려준다

#### Scenario: 목록은 표시 서명 기준
- **WHEN** 기관 값 서명이 `가나다`이고 연결된 공식 서지의 서명이 `하늘`인 도서와, 서명이 `나비`인 도서가 있으면
- **THEN** 목록은 `나비` 도서, `하늘` 도서 순서다
