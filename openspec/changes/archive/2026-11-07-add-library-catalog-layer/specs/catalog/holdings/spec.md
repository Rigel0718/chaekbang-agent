# Spec Delta

## MODIFIED Requirements

### Requirement: 사본 등록
관리자는 자기 기관의 기관 도서(`library_book_id`)로 사본을 SHALL 등록할 수 있다.
- 사본 정보: 등록번호(필수), 입수 구분(필수), 청구기호(선택), 서가 위치(선택), 상태
- 입수 구분별 정보는 "입수 구분" 요구사항을 따른다.
- 등록번호는 사본을 식별하는 번호이고, 청구기호(예: `813.7-한232ㅊ`)는 서가에서 책을 찾는 주소다. 같은 책의 복본은 청구기호가 같을 수 있다.
- 상태의 기본값은 `available`(대출 가능)이다.
- 출처는 `manual`(직접 등록)로 기록한다.
- 같은 책을 여러 권 등록할 수 있다.

#### Scenario: 정상 등록
- **WHEN** 관리자가 ISBN이 있는 기관 도서의 id, 등록번호 `EM0001`, 청구기호 `813.7-한232ㅊ`, 입수 구분 `purchased`, 구입가 15000으로 `POST /holdings`를 호출하면
- **THEN** 201과 함께 입력한 값이 저장된 상태 `available`, 출처 `manual`인 사본을 돌려준다

#### Scenario: 같은 책 두 권
- **WHEN** 같은 도서로 등록번호가 다르고 청구기호가 같은 사본 두 개를 등록하면
- **THEN** 두 사본이 모두 저장된다

#### Scenario: 도서 목록에 없는 도서
- **WHEN** library_books에 없는 도서 id로 사본을 등록하면
- **THEN** 404를 돌려준다

#### Scenario: 다른 기관의 도서
- **WHEN** B 기관의 기관 도서 id로 A 기관 관리자가 사본을 등록하면
- **THEN** 404를 돌려주고 사본을 저장하지 않는다

### Requirement: 사본 조회
직원은 자기 기관의 사본을 단건과 목록으로 SHALL 조회할 수 있다.
- 목록은 기관 도서(id)와 상태로 거를 수 있고, 페이지네이션을 따른다.
- 각 사본에는 기관 도서의 id와 표시 값(제목·저자)과 ISBN이 함께 들어간다.
- 목록은 `status`를 주지 않으면 제적 사본을 뺀다. `status=withdrawn`이면 제적 사본만 돌려준다.

#### Scenario: 도서로 거르기
- **WHEN** 키오스크가 `GET /holdings?library_book_id={id}`를 호출하면
- **THEN** 자기 기관의 그 책 사본만 돌려준다

#### Scenario: 상태로 거르기
- **WHEN** `GET /holdings?status=available`을 호출하면
- **THEN** 대출 가능한 사본만 돌려준다

#### Scenario: 제적 사본 제외
- **WHEN** 제적 사본이 있는 기관에서 `GET /holdings`를 호출하면
- **THEN** 제적 사본은 들어 있지 않다

#### Scenario: 제적 사본만 보기
- **WHEN** `GET /holdings?status=withdrawn`을 호출하면
- **THEN** 제적 사본만 돌려준다

### Requirement: 빠진 정보 표기
사본 조회 결과에는 매입 사본에 빠진 정보를 `missing_fields`로 SHALL 표기한다. `purchased` 사본의 도서에 ISBN이 없으면 `isbn`, 구입가가 없으면 `purchase_price`가 들어간다. 저장하지 않고 조회할 때 계산하므로 정보를 채우면 표기가 사라진다. `GET /holdings?incomplete=true`로 표기가 있는 사본만 거를 수 있다.

#### Scenario: ISBN 없는 매입 사본 표기
- **WHEN** ISBN 없는 도서의 가져온 `purchased` 사본을 조회하면
- **THEN** `missing_fields`에 `isbn`이 있다

#### Scenario: ISBN을 채우면 표기가 사라짐
- **WHEN** 그 도서에 `PATCH /library-books/{id}`로 ISBN을 채운 뒤 사본을 조회하면
- **THEN** `missing_fields`에 `isbn`이 없다

#### Scenario: 빠진 정보가 있는 사본만 거르기
- **WHEN** `GET /holdings?incomplete=true`를 호출하면
- **THEN** `missing_fields`가 비어 있지 않은 자기 기관 사본만 돌려준다

#### Scenario: 기증 사본은 표기하지 않음
- **WHEN** 기증처와 ISBN이 없는 `donated` 사본을 조회하면
- **THEN** `missing_fields`는 비어 있다
