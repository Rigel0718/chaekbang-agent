# web

화면 파일이다. FastAPI가 `public/`만 `/ui/`에 정적 파일로 내준다(`app/main.py`). 빌드가 없고 Python 코드도 없다. 이용자 화면은 `/ui/librarian/`이다. 이 README와 CLAUDE.md는 `public/` 밖이라 내주지 않는다.

## 구성

| 위치 | 내용 |
| --- | --- |
| `public/shared/` | 이용자·관리자 화면이 함께 쓸 모듈: `api.js`(토큰, 경로 함수, 오류 구분), `sse.js`(fetch 스트림을 사건으로), `card.js`(책 카드, `safeUrl`), `base.css` |
| `public/librarian/` | 이용자 화면: `index.html`, `librarian.css`, `suggest.js`(자동완성), `chat.js`(턴 흐름), `basket.js`(담기), `idle.js`(비우기), `main.js`(조립) |

## 규칙

- **기존 API만 쓴다.** 화면 전용 API를 만들지 않는다. 필요해 보이면 먼저 묻는다. 부르는 경로는 `shared/api.js`에 모은다(자동완성, 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내).
- **기관은 토큰으로 정한다.** 화면은 `library_id`를 보내지 않는다.
- **브라우저에는 토큰만 저장한다.** `localStorage`의 토큰 키 하나뿐이다. 대화, 검색어, 담은 책은 메모리에만 두고 새로 고치거나 비우면 사라진다(공용 PC).
- **서버 값은 글자로만 넣는다.** `textContent`, `setAttribute`를 쓰고 `innerHTML` 계열, `eval`은 쓰지 않는다. 주소(표지, 상품 링크)는 `card.js`의 `safeUrl`을 거쳐 `http`·`https`만 쓴다.
- **책 값은 `book.필드` 형태로만 읽는다.** 필드 이름은 `BookSummary`·`BookCard`·`RelatedBook`에 있어야 한다. 테스트가 `card.js`를 검사한다.
- **표지는 원본 URL로만 보이고 출처(`cover_source`)를 함께 보인다.** 외부 대출 기관은 대출 상태의 갱신 시각(`status_synced_at`)을 보인다. 표지가 없으면 자리 표시를 둔다.
- **무입력 비우기는 4분 30초다**(`public/librarian/idle.js`). 서버의 AI 사서 세션이 입력 없이 5분이면 지워지므로(`librarian_session_idle_minutes`) 그보다 앞서게 둔다. 서버 설정을 바꾸면 이 값도 바꾼다.
- 최신 크롬·엣지를 가정한다(`fetch` 스트림, `TextDecoderStream`, ES 모듈).
- 대화 요청은 POST에 토큰 헤더가 필요해서 `EventSource`가 아니라 `fetch` 스트림으로 읽는다.

## 개발용 토큰

로그인 화면이 아직 없다(`add-web-ui`). Swagger(`/docs`)에서 키오스크 계정으로 `POST /auth/login`을 한 뒤 `/ui/librarian/#token=<토큰>`으로 연다. 화면이 토큰을 저장하고 주소에서 지운다. 401이면 토큰을 지우고 안내한다.

## 시험

`tests/platform/test_web_ui.py`가 서빙, 경로, 기존 API만 쓰기, 저장 규칙, 안전한 표시, 카드 필드 계약을 본다. 화면 동작은 `openspec/changes/add-librarian-web-ui/design.md`의 브라우저 확인 항목으로 본다. 브라우저 자동화 테스트는 대출·승인 같은 여러 단계 흐름이 생기면 다시 본다(`add-web-ui`).
