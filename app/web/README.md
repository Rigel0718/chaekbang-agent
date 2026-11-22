# web

화면 파일이다. FastAPI가 `public/`만 `/ui/`에 정적 파일로 내준다(`app/main.py`). 빌드가 없고 Python 코드도 없다. 이용자 화면은 `/ui/librarian/`이다. 이 README와 CLAUDE.md는 `public/` 밖이라 내주지 않는다.

## 구성

| 위치 | 내용 |
| --- | --- |
| `public/shared/` | 이용자·관리자 화면이 함께 쓸 모듈: `api.js`(토큰, 경로 함수, 오류 구분), `sse.js`(fetch 스트림을 사건으로), `card.js`(책 카드, `safeUrl`), `base.css` |
| `public/librarian/` | 이용자 화면: `index.html`, `librarian.css`, `suggest.js`(자동완성), `chat.js`(턴 흐름), `basket.js`(담기), `actions.js`(대출·반납·희망도서 입력칸), `idle.js`(비우기), `main.js`(조립) |

## 규칙

- **기존 API만 쓴다.** 화면 전용 API를 만들지 않는다. 필요해 보이면 먼저 묻는다. 부르는 경로는 `shared/api.js`에 모은다(자동완성, 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 대출 `/loans`, 반납 `/loans/return`, 희망도서 `/book-requests`).
- **기관은 토큰으로 정한다.** 화면은 `library_id`를 보내지 않는다.
- **브라우저에는 토큰만 저장한다.** `localStorage`의 토큰 키 하나뿐이다. 대화, 검색어, 담은 책은 메모리에만 두고 새로 고치거나 비우면 사라진다(공용 PC).
- **서버 값은 글자로만 넣는다.** `textContent`, `setAttribute`를 쓰고 `innerHTML` 계열, `eval`은 쓰지 않는다. 주소(표지, 상품 링크)는 `card.js`의 `safeUrl`을 거쳐 `http`·`https`만 쓴다.
- **책 값은 `book.필드` 형태로만 읽는다.** 필드 이름은 `BookSummary`·`BookCard`·`RelatedBook`에 있어야 한다. 테스트가 `card.js`를 검사한다.
- **표지는 원본 URL로만 보이고 출처(`cover_source`)를 함께 보인다.** 외부 대출 기관은 대출 상태의 갱신 시각(`status_synced_at`)을 보인다. 표지가 없으면 자리 표시를 둔다.
- **무입력 비우기는 4분 30초다**(`public/librarian/idle.js`). 서버의 AI 사서 세션이 입력 없이 5분이면 지워지므로(`librarian_session_idle_minutes`) 그보다 앞서게 둔다. 서버 설정을 바꾸면 이 값도 바꾼다.
- **회원번호는 대출·희망도서 본문에만 보낸다**(`api.js`의 `borrow`, `requestBook`). 대화 요청 본문의 키는 `session_id`, `message`, `selected_library_book_id`뿐이다. 응답의 회원번호는 보이지 않는다. 테스트가 소스를 검사한다.
- **대출·반납·희망도서 입력칸**(`actions.js`)은 칸 하나에 모드 셋(빌리기, 반납하기, 희망도서)이다. [대출·반납] 버튼은 HTML에서 `hidden`으로 시작하고, 도서관 안내의 `loan_mode`가 `internal`일 때만 보인다(`main.js`의 `loadGuide`, 안내를 못 읽으면 숨김). 외부 대출 기관은 서버가 409로 막는다. [희망도서 신청]은 두 방식 모두 보이고, AI 사서가 희망도서를 안내한 답(`suggest_book_request`)에도 같은 버튼이 붙는다.
- **입력은 칸이 열린 동안만 둔다.** 칸을 닫거나 화면을 비우면(`resetAll`: 새 대화, 무입력, 세션 끝) 모든 입력을 지운다. 입력칸은 `autocomplete="off"`다. 빌리기·반납이 성공하면 등록번호만 지우고(연속 대출) 희망도서가 성공하면 모두 지운다. 서버 문구(404·409)는 글자로만 칸 안에 보인다.
- 최신 크롬·엣지를 가정한다(`fetch` 스트림, `TextDecoderStream`, ES 모듈).
- 대화 요청은 POST에 토큰 헤더가 필요해서 `EventSource`가 아니라 `fetch` 스트림으로 읽는다.

## 개발용 토큰

로그인 화면이 아직 없다(`add-web-ui`). Swagger(`/docs`)에서 키오스크 계정으로 `POST /auth/login`을 한 뒤 `/ui/librarian/#token=<토큰>`으로 연다. 화면이 토큰을 저장하고 주소에서 지운다. 401이면 토큰을 지우고 안내한다.

## 시험

`tests/platform/test_web_ui.py`가 서빙, 경로, 기존 API만 쓰기, 저장 규칙, 안전한 표시, 카드 필드 계약, 회원번호 행선지, 대출 버튼 조건, 입력칸 자동 완성을 본다. 화면 동작은 change `design.md`의 브라우저 확인 항목으로 본다(`add-librarian-web-ui`, `add-librarian-actions`). 브라우저 자동화 테스트는 대출·승인 같은 여러 단계 흐름이 생기면 다시 본다(`add-web-ui`).
