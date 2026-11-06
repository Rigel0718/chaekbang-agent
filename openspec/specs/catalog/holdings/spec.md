# catalog/holdings Specification

## Purpose

기관이 실제로 가진 책을 사본 단위로 보관해, 같은 책을 여러 권 가진 경우와 사본별 청구기호·서가 위치·대출 상태를 다루고, 추천이 "소장 도서만" 고를 수 있는 근거를 만든다.

## Requirements

### Requirement: 사본 등록
관리자는 도서 목록에 있는 도서(내부 id)로 자기 기관의 사본을 SHALL 등록할 수 있다.
- 사본 정보: 등록번호(필수), 입수 구분(필수), 청구기호(선택), 서가 위치(선택), 상태
- 입수 구분별 정보는 "입수 구분" 요구사항을 따른다.
- 등록번호는 사본을 식별하는 번호이고, 청구기호(예: `813.7-한232ㅊ`)는 서가에서 책을 찾는 주소다. 같은 책의 복본은 청구기호가 같을 수 있다.
- 상태의 기본값은 `available`(대출 가능)이다.
- 출처는 `manual`(직접 등록)로 기록한다.
- 같은 책을 여러 권 등록할 수 있다.

#### Scenario: 정상 등록
- **WHEN** 관리자가 ISBN이 있는 도서의 id, 등록번호 `EM0001`, 청구기호 `813.7-한232ㅊ`, 입수 구분 `purchased`, 구입가 15000으로 `POST /holdings`를 호출하면
- **THEN** 201과 함께 입력한 값이 저장된 상태 `available`, 출처 `manual`인 사본을 돌려준다

#### Scenario: 같은 책 두 권
- **WHEN** 같은 도서로 등록번호가 다르고 청구기호가 같은 사본 두 개를 등록하면
- **THEN** 두 사본이 모두 저장된다

#### Scenario: 도서 목록에 없는 도서
- **WHEN** books에 없는 도서 id로 사본을 등록하면
- **THEN** 404를 돌려준다

### Requirement: 등록번호 유일성
등록번호는 한 기관 안에서 MUST 유일하다. 다른 기관은 같은 등록번호를 쓸 수 있다.

#### Scenario: 같은 기관에서 중복
- **WHEN** 이미 있는 등록번호로 같은 기관에 사본을 등록하면
- **THEN** 409를 돌려준다

#### Scenario: 다른 기관의 같은 번호
- **WHEN** A 기관에 `EM0001`이 있을 때 B 기관이 `EM0001`로 사본을 등록하면
- **THEN** 201로 등록된다

### Requirement: 입수 구분
사본마다 입수 구분(`acquisition_type`)을 MUST 기록한다. 값은 `purchased`(매입·공식 납품), `donated`(기증), `unknown`(알 수 없음) 세 가지다. `unknown`은 장서 가져오기에서만 생기고, 직접 등록에서는 422로 거부한다. 같은 책이라도 기관마다, 사본마다 입수 경로가 다를 수 있으므로 입수 구분은 도서가 아니라 사본에 둔다.
- **매입·납품 사본(`purchased`)**
  - 구입가(`purchase_price`)가 필수다. 0 이상의 정수(원 단위)이고, 실제로 산 가격이라 도서의 정가와 다를 수 있다.
  - ISBN이 있는 도서로만 등록할 수 있다.
  - 기증처는 둘 수 없다.
- **기증 사본(`donated`)**
  - 기증처(`donor`, 선택)를 적을 수 있다. 예: "주민 기증", "OO초등학교 학부모회"
  - 구입가는 둘 수 없다.
  - ISBN이 없는 도서로도 등록할 수 있다. 도서의 필수 항목(제목·저자)만 있으면 된다.
- **입수 구분을 모르는 사본(`unknown`)**
  - 구입가와 기증처를 둘 수 없다. 관리자가 사본을 수정해 `purchased`나 `donated`로 바꿀 수 있다.
- **가져온 사본의 예외**: 출처가 `imported`인 `purchased` 사본은 구입가나 ISBN이 없어도 된다. 오류가 아니라 빠진 정보로 표기한다.
- 사본을 수정해 입수 구분이나 구입가·기증처를 바꿀 때도 같은 규칙을 따른다. 가져온 사본의 예외는 이미 `purchased`인 가져온 사본을 수정할 때만 유지한다. 다른 구분에서 `purchased`로 바꿀 때는 적용하지 않는다.

#### Scenario: 기증 사본 등록
- **WHEN** 관리자가 ISBN이 없는 도서로 입수 구분 `donated`, 기증처 "주민 기증"인 사본을 등록하면
- **THEN** 201과 함께 구입가가 비어 있는 기증 사본을 돌려준다

#### Scenario: 구입가 없는 매입 사본
- **WHEN** 관리자가 입수 구분 `purchased`로 구입가 없이 사본을 등록하면
- **THEN** 422를 돌려주고 사본을 저장하지 않는다

#### Scenario: ISBN 없는 도서로 매입 사본
- **WHEN** 관리자가 ISBN이 없는 도서로 입수 구분 `purchased`, 구입가 12000인 사본을 등록하면
- **THEN** 422를 돌려주고 ISBN을 먼저 채우라는 메시지를 준다

#### Scenario: 기증 사본에 구입가
- **WHEN** 관리자가 입수 구분 `donated`에 구입가를 함께 보내면
- **THEN** 422를 돌려준다

#### Scenario: 입수 구분 규칙 직접 저장
- **WHEN** holdings에 입수 구분 `purchased`이면서 구입가가 비어 있는 행이나, `donated`이면서 구입가가 있는 행을 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 직접 등록의 unknown
- **WHEN** 관리자가 입수 구분 `unknown`으로 `POST /holdings`를 호출하면
- **THEN** 422를 돌려준다

#### Scenario: unknown을 기증으로 수정
- **WHEN** 관리자가 `unknown` 사본을 `PATCH /holdings/{id}`로 `donated`로 바꾸면
- **THEN** 입수 구분이 `donated`가 된다

#### Scenario: 가져온 매입 사본의 구입가 채우기
- **WHEN** ISBN 없는 도서의 가져온 `purchased` 사본에 `PATCH /holdings/{id}`로 구입가만 보내면
- **THEN** 구입가가 저장되고 `missing_fields`에는 `isbn`만 남는다

#### Scenario: 가져온 unknown 사본을 매입으로 수정
- **WHEN** ISBN 없는 도서의 가져온 `unknown` 사본을 구입가와 함께 `purchased`로 바꾸면
- **THEN** 422를 돌려준다

#### Scenario: 가져온 매입 사본의 구입가 없음 직접 저장
- **WHEN** holdings에 출처 `imported`, 입수 구분 `purchased`, 구입가가 빈 행을 직접 저장하면
- **THEN** 데이터베이스가 받아들인다

### Requirement: 사본 상태
사본 상태는 `available`, `on_loan`, `lost`, `damaged`, `withdrawn`(제적) 중 하나만 MUST 허용한다.
- `on_loan`은 대출과 반납, 장서 가져오기로만 바뀐다. 사본 수정 API로 `on_loan`을 지정하거나 `on_loan`에서 다른 상태로 바꾸면 409를 돌려준다.
- 관리자는 `available`, `lost`, `damaged`, `withdrawn` 사이에서 상태를 바꿀 수 있다.
- 제적 사본은 빌릴 수 없고 소장 권수에 들어가지 않는다.

#### Scenario: 분실 처리
- **WHEN** 관리자가 `available` 사본을 `PATCH /holdings/{id}`로 `lost`로 바꾸면
- **THEN** 상태가 `lost`가 된다

#### Scenario: 직접 대출 중으로 바꾸기
- **WHEN** 관리자가 사본 상태를 `on_loan`으로 바꾸려 하면
- **THEN** 409를 돌려준다

#### Scenario: 대출 중인 사본의 상태 변경
- **WHEN** 관리자가 `on_loan` 사본을 `lost`로 바꾸려 하면
- **THEN** 409를 돌려주고 반납을 먼저 하라는 메시지를 준다

#### Scenario: 허용되지 않은 상태
- **WHEN** holdings에 상태 `missing`으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 제적 처리
- **WHEN** 관리자가 `available` 사본을 `PATCH /holdings/{id}`로 `withdrawn`으로 바꾸면
- **THEN** 상태가 `withdrawn`이 된다

### Requirement: 사본 조회
직원은 자기 기관의 사본을 단건과 목록으로 SHALL 조회할 수 있다.
- 목록은 도서(id)와 상태로 거를 수 있고, 페이지네이션을 따른다.
- 각 사본에는 도서 제목·저자·ISBN이 함께 들어간다.
- 목록은 `status`를 주지 않으면 제적 사본을 뺀다. `status=withdrawn`이면 제적 사본만 돌려준다.

#### Scenario: 도서로 거르기
- **WHEN** 키오스크가 `GET /holdings?book_id={id}`를 호출하면
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

### Requirement: 사본 수정과 삭제
관리자는 자기 기관 사본의 등록번호·청구기호·서가 위치·상태·입수 정보를 수정하고, 사본을 삭제할 수 있어야 SHALL 한다. 대출 기록이 있는 사본은 삭제할 수 없고(409), 대신 상태를 `lost`나 `damaged`로 바꾼다.

#### Scenario: 서가 위치 수정
- **WHEN** 관리자가 `PATCH /holdings/{id}`로 서가 위치만 보내면
- **THEN** 서가 위치만 바뀐다

#### Scenario: 대출 기록 없는 사본 삭제
- **WHEN** 대출 기록이 없는 사본을 `DELETE /holdings/{id}`로 지우면
- **THEN** 204를 돌려준다

#### Scenario: 대출 기록 있는 사본 삭제
- **WHEN** 대출 기록이 있는 사본을 지우려 하면
- **THEN** 409를 돌려주고 사본은 남아 있다

### Requirement: 빠진 정보 표기
사본 조회 결과에는 매입 사본에 빠진 정보를 `missing_fields`로 SHALL 표기한다. `purchased` 사본의 도서에 ISBN이 없으면 `isbn`, 구입가가 없으면 `purchase_price`가 들어간다. 저장하지 않고 조회할 때 계산하므로 정보를 채우면 표기가 사라진다. `GET /holdings?incomplete=true`로 표기가 있는 사본만 거를 수 있다.

#### Scenario: ISBN 없는 매입 사본 표기
- **WHEN** ISBN 없는 도서의 가져온 `purchased` 사본을 조회하면
- **THEN** `missing_fields`에 `isbn`이 있다

#### Scenario: ISBN을 채우면 표기가 사라짐
- **WHEN** 그 도서에 `PATCH /books/{id}`로 ISBN을 채운 뒤 사본을 조회하면
- **THEN** `missing_fields`에 `isbn`이 없다

#### Scenario: 빠진 정보가 있는 사본만 거르기
- **WHEN** `GET /holdings?incomplete=true`를 호출하면
- **THEN** `missing_fields`가 비어 있지 않은 자기 기관 사본만 돌려준다

#### Scenario: 기증 사본은 표기하지 않음
- **WHEN** 기증처와 ISBN이 없는 `donated` 사본을 조회하면
- **THEN** `missing_fields`는 비어 있다
