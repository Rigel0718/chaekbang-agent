## MODIFIED Requirements

### Requirement: 기존 API만 사용
화면은 화면 전용 API 없이 기존 API만 MUST 쓴다. 이용자 화면이 부르는 경로는 자동완성, 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 대출, 반납, 희망도서 신청이다. 화면을 더해도 서버의 API 경로는 늘지 않는다.

#### Scenario: 서버 경로
- **WHEN** 서버의 경로 목록을 읽으면
- **THEN** `/ui` 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다

#### Scenario: 화면이 부르는 경로
- **WHEN** 이용자 화면 스크립트에서 서버에 요청하는 경로를 모두 모으면
- **THEN** 모두 `/catalog/suggest`, `/catalog/search`, `/catalog/books/{id}/similar`, `/librarian/messages`, `/librarian/sessions/{id}`, `/library/guide`, `/loans`, `/loans/return`, `/book-requests` 중 하나다

## ADDED Requirements

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
