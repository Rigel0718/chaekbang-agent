# Spec Delta

## MODIFIED Requirements

### Requirement: 사본 조회
직원은 자기 기관의 사본을 단건과 목록으로 SHALL 조회할 수 있다.
- 목록은 기관 도서(id)와 상태로 거를 수 있고, 페이지네이션을 따른다.
- 각 사본에는 기관 도서의 id와 표시 값(제목·저자)과 ISBN이 함께 들어간다.
- 목록은 `status`를 주지 않으면 제적 사본을 뺀다. `status=withdrawn`이면 제적 사본만 돌려준다.
- 목록은 찾기 글자 `q`(앞뒤 공백을 지운 1~100자)로 거를 수 있다. 등록번호가 `q`와 같은 사본과, 기관 도서의 서명·저자(공식 서지 값과 기관 값 중 하나라도)에 `q`가 대소문자 구분 없이 들어간 사본을 돌려준다. `%`·`_`는 글자 그대로 찾는다. 오타는 허용하지 않는다.
- `q`가 있고 `status`가 없으면 제적 사본을 포함한 모든 상태를 돌려준다. `status`가 함께 있으면 그 상태만 돌려준다.
- `q`가 있으면 등록번호가 같은 사본을 맨 앞에 두고, 나머지는 서명 가나다순, 등록번호 순이다. 공백만 있거나 100자를 넘는 `q`는 422다.
- `q`가 없으면 최근에 등록한 사본부터 돌려준다(등록 시각 내림차순, 같으면 id 내림차순).

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

#### Scenario: 최근 등록순
- **WHEN** 등록번호 `A-2`, `A-1`, `A-3` 순서로 사본을 등록한 기관에서 `q` 없이 `GET /holdings`를 호출하면
- **THEN** `A-3`, `A-1`, `A-2` 순서로 돌려준다

#### Scenario: 등록번호로 찾기
- **WHEN** 등록번호 `EM0012`인 사본이 있는 기관에서 `GET /holdings?q=EM0012`를 호출하면
- **THEN** 그 사본이 첫 번째로 나온다

#### Scenario: 서명 일부로 찾기
- **WHEN** 서명이 `만복이네 떡집`인 책의 사본이 둘 있을 때 `GET /holdings?q=떡집`을 호출하면
- **THEN** 두 사본이 모두 나오고 서명에 `떡집`이 없는 사본은 없다

#### Scenario: 공식 서지 값으로 찾기
- **WHEN** 기관 값 서명은 `만복이 떡집`이고 연결된 공식 서지 서명이 `만복이네 떡집`인 책에서 `GET /holdings?q=만복이네`를 호출하면
- **THEN** 그 책의 사본이 나온다

#### Scenario: 저자로 찾기
- **WHEN** `GET /holdings?q=김리리`를 호출하면
- **THEN** 저자에 `김리리`가 들어간 책의 사본이 나온다

#### Scenario: 찾기는 모든 상태
- **WHEN** 한 책의 사본이 이용 가능·대출 중·분실·훼손·제적 하나씩일 때 `status` 없이 그 서명으로 `GET /holdings?q=`를 호출하면
- **THEN** 다섯 사본이 모두 나온다

#### Scenario: 찾기와 상태를 함께
- **WHEN** 위 책에서 `GET /holdings?q={서명}&status=lost`를 호출하면
- **THEN** 분실 사본 하나만 나온다

#### Scenario: 와일드카드 글자
- **WHEN** 서명에 `%`가 없는 기관에서 `GET /holdings?q=%`를 호출하면
- **THEN** 빈 목록을 돌려준다

#### Scenario: 빈 찾기 글자
- **WHEN** `GET /holdings?q=%20%20`처럼 공백만 보내면
- **THEN** 422를 돌려준다

#### Scenario: 찾기의 기관 분리
- **WHEN** B 기관에만 서명 `구름빵`과 등록번호 `EM0999` 사본이 있을 때 A 기관 직원이 `GET /holdings?q=구름빵`과 `GET /holdings?q=EM0999`를 호출하면
- **THEN** 둘 다 빈 목록을 돌려준다
