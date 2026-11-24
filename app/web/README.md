# web

화면 파일이다. FastAPI가 `public/`만 `/ui/`에 정적 파일로 내준다(`app/main.py`). 빌드가 없고 Python 코드도 없다. 로그인은 `/ui/login/`, 이용자 화면은 `/ui/librarian/`, 관리자 화면은 `/ui/admin/`이다. 이 README와 CLAUDE.md는 `public/` 밖이라 내주지 않는다.

## 구성

| 위치 | 내용 |
| --- | --- |
| `public/shared/` | 화면들이 함께 쓰는 모듈: `api.js`(화면별 토큰, 역할 확인, 경로 함수, 오류 구분), `sse.js`(fetch 스트림을 사건으로), `card.js`(책 카드, `safeUrl`), `dom.js`(글자만 넣는 요소 도우미), `base.css` |
| `public/login/` | 로그인 화면: `index.html`, `login.css`, `login.js`(응답 역할로 행선지) |
| `public/librarian/` | 이용자 화면: `index.html`, `librarian.css`, `suggest.js`(자동완성), `chat.js`(턴 흐름, 두 단계 검색 결과 블록), `basket.js`(담기), `actions.js`(대출·반납·희망도서 입력칸), `idle.js`(두 시계), `main.js`(조립) |
| `public/admin/` | 관리자 화면(한 페이지, 탭 넷): `index.html`, `admin.css`, `main.js`(조립·탭·로그아웃), `chat.js`(운영 대화), `approvals.js`(승인 목록), `requests.js`(희망도서), `overdue.js`(오늘의 연체) |

## 규칙

- **기존 API만 쓴다.** 화면 전용 API를 만들지 않는다. 필요해 보이면 먼저 묻는다. 부르는 경로는 `shared/api.js`에 모은다(로그인·내 정보·로그아웃, 자동완성, 검색, 주제 검색 `/catalog/topic`, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 대출 `/loans`, 반납 `/loans/return`, 희망도서 `/book-requests`, 기관 정보 `/library`, 운영 에이전트 대화, 큐레이션·연체 안내문 틀·구매 요청서의 목록·상세·승인·반려·내리기, 오늘의 연체 `/overdue-notices/today`). 테스트가 부르는 경로·메서드가 서버 OpenAPI에 있는지 맞춰 본다.
- **기관은 토큰으로 정한다.** 화면은 `library_id`를 보내지 않는다.
- **브라우저에는 토큰만 저장한다. 화면마다 키 하나다.** 키오스크(이용자 화면)는 `localStorage`의 `chaekbang.kiosk.token`(PC를 다시 켜도 이어짐), 관리자 화면은 `sessionStorage`의 `chaekbang.admin.token`(탭을 닫으면 사라지고 키오스크 토큰을 덮어쓰지 않음)이다. 저장소 접근은 `api.js`에만 있고 화면은 처음에 `useScreen`으로 정한다. 대화, 검색어, 담은 책, 관리자 목록은 메모리에만 두고 새로 고치거나 비우면 사라진다(공용 PC).
- **서버 값은 글자로만 넣는다.** `textContent`, `setAttribute`를 쓰고 `innerHTML` 계열, `eval`은 쓰지 않는다. 주소(표지, 상품 링크)는 `card.js`의 `safeUrl`을 거쳐 `http`·`https`만 쓴다.
- **책 값은 `book.필드` 형태로만 읽는다.** 필드 이름은 `BookSummary`·`BookCard`·`RelatedBook`에 있어야 한다. 테스트가 `card.js`를 검사한다.
- **표지는 원본 URL로만 보이고 출처(`cover_source`)를 함께 보인다.** 외부 대출 기관은 대출 상태의 갱신 시각(`status_synced_at`)을 보인다. 표지가 없으면 자리 표시를 둔다.
- **이용자 화면은 두 시계로 비운다**(`public/librarian/idle.js`): 무입력 1분(45초에 알림, 입력하면 다시 셈, 답을 받는 동안에는 세지 않음), 이용 상한 3분(비운 뒤 첫 입력에서 시작, 2분 30초에 알림, 입력해도 늘지 않고 답을 받는 중에도 끊고 비움). 알림은 화면 아래 띠다. 시간이 다 돼 비우면 시작 화면("화면을 눌러 시작하세요")이 보이고 누르면 대화 화면으로 간다(처음 열 때도 시작 화면). 키오스크는 로그아웃하지 않는다. [새 대화]와 세션 끝은 시작 화면 없이 비운다. 둘 다 서버 AI 사서 세션 한도(5분, `librarian_session_idle_minutes`)보다 짧아야 하고 테스트가 본다. 확인용으로 `?idle_seconds=N`, `?cap_seconds=N`이 시계를 줄인다(알림은 15초·30초 앞).
- **로그인과 역할 확인.** 화면은 열 때 `requireRole`로 `GET /auth/me`를 불러 역할을 확인한다(이용자 화면은 `kiosk`, 관리자 화면은 `admin`). 토큰이 없거나 401이거나 역할이 다르면 그 화면의 키만 지우고 `/ui/login/`으로 간다. 이용자 화면에는 로그아웃 버튼이 없다(키오스크를 끌 사람이 없다). 관리자 화면에는 [로그아웃]이 있고 뒤로 가기 캐시로 돌아오면 토큰을 다시 확인한다. 로그인 화면은 로그인한 상태로 열려도 넘기지 않는다(같은 PC에서 관리자가 새 탭으로 로그인하는 길).
- **Enter는 서명·저자 찾기를 먼저 한다**(`librarian/chat.js`의 `submitText`, `main.js`의 `submit`). 1권 이상이면 AI 사서 대화를 보내지 않고 두 단계 결과를 보인다: 위 단 "이 책을 찾으시나요?"(찾기 결과 앞 2권), 아래 단 "'질의'와 관련된 책"(`/catalog/topic` 결과에서 위 단 책을 뺀 것, 비거나 실패하면 제목째 숨김), [사서에게 물어보기](같은 글을 대화로 한 번). 0권이거나, 입력이 100자(`suggest.js`의 `MAX_QUERY`, 서버 질의 상한과 같음)를 넘거나, 찾기가 실패하면(401은 로그인 화면) 지금처럼 AI 사서 대화로 간다. 자동완성 후보 고르기와 "모두 찾기"는 그대로다. 두 단계 결과는 서버 세션을 만들거나 바꾸지 않고 [새 대화]·무입력으로 지워진다.
- **관리자 화면은 보고 승인·반려한다.** 승인 목록(큐레이션·연체 안내문 틀·구매 요청서)은 상세 보기, 승인(확인 한 번), 반려(사유 필수), 게시 내리기만 하고 만들기·고치기 양식은 없다(초안은 운영 대화로 만든다). 운영 대화는 답 문장만 보인다(표·차트는 24b). 외부 대출 기관(`loan_mode`가 `internal`이 아님)은 [오늘의 연체] 탭과 틀 묶음이 숨겨진다(`admin/main.js`의 `loadLibrary` 한 곳, 서버 409가 방어선).
- **회원 값은 두 탭에서만 보이고 들어올 때마다 다시 읽는다.** 희망도서와 오늘의 연체 목록의 회원번호·이름·전화·문안은 그 탭에 들어올 때마다 서버에서 다시 읽는다(떠날 때 지우지는 않는다. 숨긴 패널은 보이지 않고 DOM을 볼 수 있는 사람은 이미 로그인한 탭을 쥔 사람이다). 복사·출력·내려받기 버튼과 `console` 출력이 없다. 관리자 무입력 자동 로그아웃은 하지 않는다(개선 사항).
- **회원번호는 대출·희망도서 본문에만 보낸다**(`api.js`의 `borrow`, `requestBook`). 대화 요청 본문의 키는 `session_id`, `message`, `selected_library_book_id`뿐이다. 이용자 화면은 응답의 회원번호를 보이지 않는다. 관리자 화면은 희망도서·연체 목록(`requests.js`, `overdue.js`)에서만 회원 값을 읽어 보이고 어떤 요청에도 넣지 않는다. 테스트가 소스를 검사한다.
- **대출·반납·희망도서 입력칸**(`actions.js`)은 칸 하나에 모드 셋(빌리기, 반납하기, 희망도서)이다. [대출·반납] 버튼은 HTML에서 `hidden`으로 시작하고, 도서관 안내의 `loan_mode`가 `internal`일 때만 보인다(`main.js`의 `loadGuide`, 안내를 못 읽으면 숨김). 외부 대출 기관은 서버가 409로 막는다. [희망도서 신청]은 두 방식 모두 보이고, AI 사서가 희망도서를 안내한 답(`suggest_book_request`)에도 같은 버튼이 붙는다.
- **입력은 칸이 열린 동안만 둔다.** 칸을 닫거나 화면을 비우면(`resetAll`: 새 대화, 무입력, 세션 끝) 모든 입력을 지운다. 입력칸은 `autocomplete="off"`다. 빌리기·반납이 성공하면 등록번호만 지우고(연속 대출) 희망도서가 성공하면 모두 지운다. 서버 문구(404·409)는 글자로만 칸 안에 보인다.
- 최신 크롬·엣지를 가정한다(`fetch` 스트림, `TextDecoderStream`, ES 모듈).
- 대화 요청은 POST에 토큰 헤더가 필요해서 `EventSource`가 아니라 `fetch` 스트림으로 읽는다.

## 로그인

`/ui/login/`에서 아이디·비밀번호로 로그인하면 역할(`kiosk`·`admin`)에 따라 이용자 화면이나 관리자 화면으로 간다. 입력칸은 `autocomplete="off"`이고 공용 PC에서는 비밀번호를 저장하지 말라고 안내한다. 크롬이 자동 완성을 무시할 수 있으니 **키오스크 PC의 크롬 설정에서 "비밀번호 저장 제안"을 꺼 두기를 권한다**(운영 안내). 개발용 `#token=`은 없앴다. 개발 계정은 `.env`의 `SEED_ADMIN_PASSWORD`·`SEED_KIOSK_PASSWORD`로 만든 `sunny-admin`·`sunny-kiosk`(햇살, 자체 대출)와 `forest-admin`·`forest-kiosk`(푸른숲, 외부 대출) 등이다.

## 시험

`tests/platform/test_web_ui.py`가 세 화면의 서빙, 경로(서버 OpenAPI와 대조), 기존 API만 쓰기, 저장 규칙, 안전한 표시, 카드 필드 계약, 회원번호 행선지, 대출 버튼 조건, 입력칸 자동 완성, 로그인·역할 확인, 시간 값, 관리자 화면 규칙을 본다. 화면 동작은 change `design.md`의 브라우저 확인 항목으로 본다(`add-librarian-web-ui`, `add-librarian-actions`, `add-web-ui`, `add-two-step-search`). 브라우저 자동화 테스트(Playwright)는 승인 흐름이 화면으로 생겼으니 24b 뒤에 다시 본다.
