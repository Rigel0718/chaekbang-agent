# features/children Specification

## Purpose

작은도서관처럼 어린이 추천이 필요한 기관이 도서를 어린이 도서와 일반 도서로 나누게 한다. 기관 개별 기능이라 공통 기능과 공식 서지는 이 구분을 모른다.

## Requirements

### Requirement: 어린이 구분
시스템은 기관 도서마다 대상 구분과 근거를 어린이 기능의 저장소에 SHALL 보관한다. 어린이 도서는 영유아·초등학생 대상 도서다. 대상 구분은 `children`과 `general`이고, 근거는 `manual`, `import_label`, `external_category`, `default`다. 우선순위는 이 순서이고, 낮은 근거는 높은 근거의 값을 바꾸지 않는다. 같은 ISBN이라도 기관마다 값이 다를 수 있다. 저장된 값이 없으면 `general`, `default`다.

#### Scenario: 기본값
- **WHEN** 어린이 구분을 지정한 적 없는 기관 도서를 `GET /children/books/{id}`로 조회하면
- **THEN** 대상 구분 `general`, 근거 `default`를 돌려주고 library_book_audiences에는 행이 없다

#### Scenario: 기관별 구분
- **WHEN** 같은 ISBN의 기관 도서를 A 기관 관리자가 `children`으로 지정하면
- **THEN** B 기관 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 허용되지 않은 구분
- **WHEN** library_book_audiences에 대상 구분 `teen`으로 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

#### Scenario: 기관 도서와 함께 삭제
- **WHEN** 어린이 구분이 저장된 기관 도서를 `DELETE /library-books/{id}`로 삭제하면
- **THEN** 그 도서의 library_book_audiences 행도 사라진다

### Requirement: 어린이 구분 조회
직원은 `GET /children/books/{id}`로 자기 기관 도서의 대상 구분과 근거를 SHALL 조회할 수 있다. 키오스크 계정도 조회할 수 있다. 다른 기관 도서는 404다.

#### Scenario: 키오스크 조회
- **WHEN** 키오스크 계정이 자기 기관 도서의 구분을 조회하면
- **THEN** 200과 대상 구분, 근거를 돌려준다

#### Scenario: 다른 기관 도서
- **WHEN** B 기관 도서의 id로 A 기관 직원이 조회하면
- **THEN** 404를 돌려준다

### Requirement: 관리자 지정
관리자는 `PUT /children/books/{id}`로 대상 구분을 SHALL 지정할 수 있고, 근거는 `manual`이 된다. 공식 서지에 연결된 도서도 지정할 수 있다.

#### Scenario: 관리자 지정
- **WHEN** 관리자가 `PUT /children/books/{id}`로 대상 구분을 `children`으로 보내면
- **THEN** 대상 구분은 `children`, 근거는 `manual`이 된다

#### Scenario: 파일 근거보다 우선
- **WHEN** 근거가 `import_label`인 도서를 관리자가 `general`로 지정하면
- **THEN** 대상 구분은 `general`, 근거는 `manual`이 된다

#### Scenario: 키오스크 계정 거부
- **WHEN** 키오스크 계정이 `PUT /children/books/{id}`를 호출하면
- **THEN** 403을 돌려준다

#### Scenario: 다른 기관 도서 지정
- **WHEN** B 기관 도서를 A 기관 관리자가 지정하려 하면
- **THEN** 404를 돌려주고 값은 바뀌지 않는다

### Requirement: 어린이 도서 목록
직원은 `GET /children/books`로 자기 기관의 어린이 도서만 페이지 단위로 SHALL 조회할 수 있다. 응답 항목은 기관 도서 목록과 같다.

#### Scenario: 어린이 도서만 거르기
- **WHEN** 어린이 도서와 일반 도서가 있는 기관에서 `GET /children/books`를 호출하면
- **THEN** 대상 구분이 `children`인 도서만 돌려준다

#### Scenario: 다른 기관 도서 제외
- **WHEN** B 기관에만 어린이 도서가 있고 A 기관 직원이 호출하면
- **THEN** 빈 목록을 돌려준다

### Requirement: 파일 근거
장서 가져오기를 적용할 때 시스템은 별치기호 `아`, `아동`, `어린이`, `유`, `유아`, `j`, 자료실 이름의 어린이·아동·유아 표시, 부가기호 첫 자리 6(초등 학습참고서)과 7(아동)을 어린이 도서 근거로 MUST 인식한다. 근거가 있고 기관 도서의 근거가 `default`나 `external_category`이면 대상 구분을 `children`, 근거를 `import_label`로 정한다. 근거가 없는 행은 대상 구분을 바꾸지 않는다.

#### Scenario: 별치기호로 분류
- **WHEN** 별치기호가 `아`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 자료실로 분류
- **WHEN** 자료실이 `어린이자료실`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 부가기호로 분류
- **WHEN** 부가기호가 `77810`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 초등 학습참고서 부가기호
- **WHEN** 부가기호가 `63710`인 행을 적용하면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 중·고등 부가기호
- **WHEN** 부가기호가 `43810`이나 `53710`인 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 출처가 없는 별치기호
- **WHEN** 별치기호가 `어`나 `c`인 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 외부 분류 근거보다 우선
- **WHEN** 근거가 `external_category`인 기관 도서의 행에 별치기호 `아`가 있으면
- **THEN** 도서는 대상 구분 `children`, 근거 `import_label`이 된다

#### Scenario: 관리자 지정 우선
- **WHEN** 관리자가 `general`로 지정한 도서의 행에 별치기호 `아`가 있으면
- **THEN** 대상 구분은 `general`, 근거는 `manual`로 남는다

#### Scenario: 근거가 없는 행
- **WHEN** 별치기호·자료실·부가기호에 어린이 표시가 없는 행을 적용하면
- **THEN** 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 다른 기관에 영향 없음
- **WHEN** A 기관 파일의 별치기호 `아`인 행이 B 기관도 가진 ISBN이면
- **THEN** A 기관 도서만 `children`이 되고 B 기관 도서는 바뀌지 않는다

### Requirement: 외부 분류 근거
어린이 구분은 기관의 요청(등록, 가져오기, ISBN 수정, 어린이 구분 갱신)에서만 MUST 바뀐다. 이때 연결된 공식 서지의 분류 원문이 정확히 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나이고 기관 도서의 근거가 `default`이면 대상 구분을 `children`, 근거를 `external_category`로 정한다. 연결이 풀리거나 근거가 아닌 분류의 공식 서지로 바뀌면 근거가 `external_category`인 값은 `general`, `default`로 되돌린다.

#### Scenario: 어린이 근거인 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서` 중 하나인 공식 서지에 연결되면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 된다

#### Scenario: 어린이 근거가 아닌 분류
- **WHEN** 근거가 `default`인 기관 도서가 분류 원문이 `국내도서-청소년`, `국내도서-전집`, `국내도서-중고등학습서-중학교`, `국내도서-소설/시/희곡`이거나 비어 있는 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 새로 등록하는 도서
- **WHEN** 분류 원문이 `국내도서-어린이`인 공식 서지가 있는 ISBN으로 기관 도서를 등록하면
- **THEN** 그 도서의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 새로 가져오는 도서
- **WHEN** 분류 원문이 `국내도서-어린이`인 공식 서지가 있는 ISBN의 행을 파일 근거 없이 적용하면
- **THEN** 새 기관 도서의 대상 구분은 `children`, 근거는 `external_category`다

#### Scenario: 높은 근거 유지
- **WHEN** 근거가 `manual`이고 대상 구분이 `general`인 기관 도서가 분류 원문이 `국내도서-유아`인 공식 서지에 연결되면
- **THEN** 대상 구분은 `general`, 근거는 `manual`로 남는다

#### Scenario: 파일 근거 유지
- **WHEN** 근거가 `import_label`인 기관 도서가 분류 원문이 `국내도서-유아`인 공식 서지에 연결되면
- **THEN** 근거는 `import_label`로 남는다

#### Scenario: 운영자 실행은 바꾸지 않음
- **WHEN** 운영자의 채움 실행이 기관 도서를 분류 원문이 `국내도서-어린이`인 공식 서지에 연결하면
- **THEN** 대상 구분은 `general`, 근거는 `default`로 남는다

#### Scenario: 연결이 풀리면 되돌림
- **WHEN** 근거가 `external_category`인 기관 도서의 ISBN을 공식 서지에 없는 값으로 고치면
- **THEN** 대상 구분은 `general`, 근거는 `default`가 된다

### Requirement: 어린이 구분 갱신
관리자는 `POST /children/refresh`로 자기 기관 도서의 어린이 구분을 공식 서지의 분류 원문에 맞춰 SHALL 갱신할 수 있다. 근거가 `default`나 `external_category`인 도서만 다시 판단하고, 바뀐 건수를 돌려준다. 다른 기관의 도서는 바뀌지 않는다.

#### Scenario: 채움 뒤 갱신
- **WHEN** 운영자의 채움 실행으로 분류 원문이 `국내도서-어린이`인 공식 서지에 연결된 기관 도서가 있고 관리자가 갱신하면
- **THEN** 대상 구분은 `children`, 근거는 `external_category`가 되고 바뀐 건수 1을 돌려준다

#### Scenario: 높은 근거는 갱신하지 않음
- **WHEN** 근거가 `manual`이나 `import_label`인 도서가 있고 관리자가 갱신하면
- **THEN** 그 도서의 값은 바뀌지 않는다

#### Scenario: 다른 기관에 영향 없음
- **WHEN** 같은 ISBN의 도서를 가진 두 기관 중 A 기관 관리자만 갱신하면
- **THEN** B 기관 도서의 대상 구분은 바뀌지 않는다

#### Scenario: 다시 갱신
- **WHEN** 갱신한 뒤 바뀐 것 없이 다시 갱신하면
- **THEN** 바뀐 건수 0을 돌려준다

#### Scenario: 키오스크 계정 거부
- **WHEN** 키오스크 계정이 `POST /children/refresh`를 호출하면
- **THEN** 403을 돌려준다

### Requirement: 어린이 도서 검색 tool
어린이 기능은 AI 사서에 어린이 도서만 찾는 tool을 SHALL 제공한다. 검색 방식은 소장 도서 검색과 같고 범위만 그 기관의 어린이 도서로 좁힌다.

#### Scenario: 어린이 도서만 나옴
- **WHEN** 같은 키워드에 맞는 어린이 도서와 일반 도서가 있을 때 이 tool을 호출하면
- **THEN** 어린이 도서만 나온다

#### Scenario: 다른 기관의 어린이 구분
- **WHEN** B 기관에서만 어린이 도서인 책이 A 기관에도 있을 때 A 기관에서 호출하면
- **THEN** 그 책은 나오지 않는다

### Requirement: 어린이 요청 판단
어린이 요청은 코드가 MUST 판단한다. 이용자 문장에 어린이 대상 표현이나 13세 이하 나이가 있거나, 이번 실행에서 어린이 도서 검색 tool을 쓰면 어린이 요청이다. 14세 이상 나이나 부모가 읽을 책 표현이 있는 문장은 어린이 근거로 보지 않는다.

#### Scenario: 나이
- **WHEN** 문장이 `7살 아이 공룡 책`이면
- **THEN** 어린이 요청이다

#### Scenario: 대상 표현
- **WHEN** 문장이 `손주와 같이 읽을 그림책`이면
- **THEN** 어린이 요청이다

#### Scenario: LLM이 어린이 tool을 씀
- **WHEN** 문장에 어린이 표현이 없고 이번 실행에서 어린이 도서 검색 tool을 썼으면
- **THEN** 어린이 요청이다

#### Scenario: 비슷한 낱말
- **WHEN** 문장이 `아이디어 책`, `딸기 요리책`, `아들러 심리학 책` 중 하나면
- **THEN** 어린이 요청이 아니다

#### Scenario: 부모가 읽을 책
- **WHEN** 문장이 `아이 훈육 방법 책`이면
- **THEN** 어린이 요청이 아니다

#### Scenario: 14세 이상
- **WHEN** 문장이 `20살 아들이 읽을 소설`이면
- **THEN** 어린이 요청이 아니다

### Requirement: 대화 안에서 유지
어린이 요청 판단은 대화 안에서 SHALL 유지된다. 뒤 문장에 어린이 표현이 없어도 이어지고, 어른이 읽을 책이라고 밝히면 풀린다. 한 문장에 어린이 표현과 그 표현이 함께 있으면 어린이 요청이다.

#### Scenario: 이어지는 질문
- **WHEN** 첫 문장이 `7살 책`이고 다음 문장이 `다른 건요?`이면
- **THEN** 어린이 요청이다

#### Scenario: 어른 책으로 전환
- **WHEN** 첫 문장이 `7살 책`이고 다음 문장이 `이제 제가 읽을 소설요`이면
- **THEN** 어린이 요청이 아니다

#### Scenario: 함께 읽기
- **WHEN** 문장이 `제가 아이랑 같이 읽을 책`이면
- **THEN** 어린이 요청이다

### Requirement: 어린이 최종 검사
어린이 요청의 답에는 그 기관에서 어린이 도서로 분류된 책만 MUST 있다. 분류가 없는 책은 일반 도서로 본다. 어린이 기능을 등록한 프로필에서 돌고, LLM의 선택과 상관없이 적용된다.

#### Scenario: 어린이 요청에 일반 도서
- **WHEN** 어린이 요청의 답에 일반 도서가 있으면
- **THEN** 그 답은 나가지 않고 LLM이 위반 내용을 받는다

#### Scenario: 분류 없는 책
- **WHEN** 어린이 요청의 답에 어린이 구분 행이 없는 책이 있으면
- **THEN** 그 답은 나가지 않는다

#### Scenario: 어린이 요청이 아님
- **WHEN** 어린이 요청이 아닌 답에 일반 도서가 있으면
- **THEN** 이 검사는 통과한다

#### Scenario: 재시도 뒤에도 위반
- **WHEN** 재시도 한도까지 일반 도서를 내면
- **THEN** 나가는 카드에 일반 도서가 없다

#### Scenario: 어린이 요청에 어린이 도서만 추천
- **WHEN** 평가 시나리오에서 어린이 요청을 하면
- **THEN** 일반 도서 추천이 0건이다
