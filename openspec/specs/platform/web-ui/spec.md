# platform/web-ui Specification

## Purpose
이용자·관리자 화면을 같은 서버의 정적 파일로 내주는 방식과, 화면 코드가 지켜야 할 계약(기존 API만 쓰기, 브라우저 저장 규칙, 서버 값의 안전한 표시, 응답 스키마와의 일치)을 정한다. 화면의 세부 동작은 design의 화면 규칙과 브라우저 확인 항목이 맡는다.

## Requirements

### Requirement: 이용자 화면 내주기
시스템은 `/ui/librarian/`에서 이용자 화면 HTML을 SHALL 내준다. 화면이 쓰는 스타일과 스크립트는 같은 서버의 `/ui/` 아래에서 빌드 없이 내준다. 화면 파일에는 비밀 값이 없으므로 토큰 없이도 내준다. 기관 데이터는 화면 파일이 아니라 토큰을 붙인 API 호출로만 받는다.

#### Scenario: 화면 HTML
- **WHEN** 토큰 없이 `GET /ui/librarian/`을 호출하면
- **THEN** 200이고 본문은 HTML이다

#### Scenario: 화면이 참조하는 파일
- **WHEN** 이용자 화면 HTML이 참조하는 스타일과 스크립트, 그리고 그 스크립트가 불러오는 모듈을 모두 호출하면
- **THEN** 모두 200이다

#### Scenario: 없는 화면 파일
- **WHEN** `/ui/` 아래의 없는 파일을 호출하면
- **THEN** 404다

#### Scenario: 화면 패키지 문서는 내주지 않음
- **WHEN** `GET /ui/README.md`나 `GET /ui/CLAUDE.md`를 호출하면
- **THEN** 404다

### Requirement: 화면 경로가 API를 가리지 않음
화면 경로는 기존 API와 문서 경로를 MUST NOT 가린다. 화면을 내준 뒤에도 기존 API는 이전과 같은 응답을 준다.

#### Scenario: AI 사서 대화 경로
- **WHEN** 화면을 내주는 상태에서 토큰 없이 `POST /librarian/messages`를 호출하면
- **THEN** 401이다

#### Scenario: 검색 경로
- **WHEN** 화면을 내주는 상태에서 토큰 없이 `GET /catalog/suggest?q=데`를 호출하면
- **THEN** 401이다

#### Scenario: API 문서
- **WHEN** `GET /docs`를 호출하면
- **THEN** 200이다

### Requirement: 기존 API만 사용
화면은 화면 전용 API 없이 기존 API만 MUST 쓴다. 이용자 화면이 부르는 경로는 자동완성, 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 대출, 반납, 희망도서 신청이다. 화면을 더해도 서버의 API 경로는 늘지 않는다.

#### Scenario: 서버 경로
- **WHEN** 서버의 경로 목록을 읽으면
- **THEN** `/ui` 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다

#### Scenario: 화면이 부르는 경로
- **WHEN** 이용자 화면 스크립트에서 서버에 요청하는 경로를 모두 모으면
- **THEN** 모두 `/catalog/suggest`, `/catalog/search`, `/catalog/books/{id}/similar`, `/librarian/messages`, `/librarian/sessions/{id}`, `/library/guide`, `/loans`, `/loans/return`, `/book-requests` 중 하나다

### Requirement: 브라우저 저장
화면은 브라우저에 직원 토큰 말고 아무것도 MUST NOT 저장한다. 대화, 검색어, 담은 책은 화면 메모리에만 두고, 새로 고치거나 화면을 비우면 사라진다. 공용 PC에서 다음 이용자가 앞사람의 기록을 보지 않게 하기 위해서다.

#### Scenario: 저장소 사용
- **WHEN** 화면 스크립트에서 브라우저 저장소(`localStorage`, `sessionStorage`, `indexedDB`, 쿠키)를 쓰는 곳을 모두 모으면
- **THEN** `localStorage`의 토큰 키 하나를 읽고 쓰고 지우는 곳뿐이다

### Requirement: 서버 값의 안전한 표시
화면은 서버가 준 값(서명, 답 문장, 추천 이유, 근거 문구, 안내 문구)을 글자로만 MUST 넣고 HTML로 해석하지 않는다. 표지와 상품 링크는 서버가 준 원본 URL을 그대로 쓰고, `http`·`https` 주소만 쓴다.

#### Scenario: HTML 해석 없음
- **WHEN** 화면 스크립트를 검사하면
- **THEN** `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`이 없다

#### Scenario: 주소 형식
- **WHEN** 화면 스크립트에서 표지·상품 링크 주소를 요소에 넣는 곳을 검사하면
- **THEN** 모두 `http`·`https` 주소만 통과시키는 같은 함수를 거친다

### Requirement: 카드 필드와 응답 스키마 일치
책 카드가 읽는 필드는 카드에 쓰는 응답 스키마(찾기 결과, 추천 카드, 비슷한 책)의 필드에 MUST 있다. 백엔드가 필드 이름을 바꾸면 테스트가 깨져 화면과 API가 어긋난 것을 알린다.

#### Scenario: 카드 필드
- **WHEN** 카드 스크립트가 책 값에서 읽는 필드 이름을 모두 모으면
- **THEN** 모두 찾기 결과, 추천 카드, 비슷한 책 스키마의 필드 중 하나다

#### Scenario: 필드 이름이 바뀜
- **WHEN** 카드 스크립트가 스키마에 없는 필드 이름을 읽으면
- **THEN** 카드 필드 테스트가 실패하고 그 이름을 알린다

### Requirement: 회원번호의 행선지
이용자 화면은 회원번호를 대출 요청(`POST /loans`)과 희망도서 신청(`POST /book-requests`)의 본문에만 MUST 넣는다. 대화 요청, 대화 종료, 검색·자동완성 요청에는 회원번호를 넣지 않는다. 화면은 대출·신청 응답의 회원번호를 표시하지 않는다.

#### Scenario: 회원번호를 보내는 곳
- **WHEN** 화면 스크립트에서 `member_number`를 쓰는 곳을 모두 모으면
- **THEN** 대출 요청과 희망도서 신청의 본문을 만드는 곳뿐이다

#### Scenario: 대화 요청의 본문
- **WHEN** 화면 스크립트에서 대화 요청 본문을 만드는 곳을 검사하면
- **THEN** 본문의 키는 `session_id`, `message`, `selected_library_book_id`뿐이다

### Requirement: 운영 방식에 따른 대출 버튼
이용자 화면은 도서관 안내 응답의 운영 방식이 `internal`일 때만 [대출·반납] 버튼을 MUST 보인다. 외부 대출 기관이거나 안내를 읽지 못하면 숨긴다. [희망도서 신청] 버튼은 두 방식 모두 보인다. 대출·반납의 최종 판단은 서버가 한다.

#### Scenario: 처음 그린 화면
- **WHEN** 이용자 화면 HTML을 읽으면
- **THEN** [대출·반납] 버튼은 숨김 상태로 시작하고 [희망도서 신청] 버튼은 숨김이 아니다

#### Scenario: 버튼을 보이는 조건
- **WHEN** 화면 스크립트에서 [대출·반납] 버튼을 보이게 하는 곳을 검사하면
- **THEN** 안내 응답의 `loan_mode`가 `internal`인지 보는 한 곳뿐이다

### Requirement: 대출·희망도서 입력칸 비우기
이용자 화면은 대출·반납·희망도서 입력칸의 값을 화면 메모리에만 두고, 칸을 닫을 때와 화면을 비울 때(새 대화, 무입력, 세션 끝) 모든 입력을 MUST 지운다. 희망도서 신청이 성공하면 모든 입력을, 빌리기·반납이 성공하면 등록번호를 지운다. 입력칸은 브라우저 자동 완성을 끈다. 이 요구사항은 브라우저 확인 항목으로 확인한다.

#### Scenario: 화면 비우기
- **WHEN** 회원번호를 적은 채 무입력 시간이 지나거나 [새 대화]를 누르면
- **THEN** 입력칸이 닫히고 다시 열면 모든 칸이 비어 있다

#### Scenario: 칸 닫기
- **WHEN** 회원번호를 적은 뒤 칸을 닫았다 다시 열면
- **THEN** 회원번호 칸이 비어 있다

#### Scenario: 입력칸 자동 완성
- **WHEN** 이용자 화면 HTML의 대출·희망도서 입력칸을 읽으면
- **THEN** 모두 `autocomplete="off"`다
