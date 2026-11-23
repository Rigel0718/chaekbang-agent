순서: 1~2는 이용자 화면(토큰·역할, 두 시계), 3~6은 관리자 화면(틀, 운영 대화, 승인 목록, 회원 값 탭), 7~9는 검사·확인·문서다. 서버 코드는 바꾸지 않는다. 바꿔야 할 일이 생기면 멈추고 먼저 묻는다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

모델 분리: **1·2·6·8은 Opus**(토큰 저장과 역할 확인, 비우기 시계, 회원 값 경계, curl 확인), **0·3·4·5·7·9는 Sonnet**(마크업·스타일, 목록 화면, 소스 검사 테스트, 문서). 넘칠 때 나누는 경계는 5와 6 사이다(1~5로 로그인부터 승인까지 닫힌다).

## 0. 시작 전 기준 (Sonnet)

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 화면별 토큰과 역할 확인 (Opus, design 결정 2·3)

- [x] 1.1 `shared/api.js`에 `useScreen("kiosk"|"admin")`(키오스크 `localStorage` `chaekbang.kiosk.token`, 관리자 `sessionStorage` `chaekbang.admin.token`), `requireRole(role)`(토큰 없음·401·역할 다름 → 그 키만 지우고 `/ui/login/`), `login`·`me`·`logout` 경로 함수를 만들고 옛 키 `chaekbang.token`을 없앤다(확인: 스펙 web-ui "저장소 사용", "옛 토큰 키"의 테스트)
- [x] 1.2 새 `public/login/`(`index.html`, `login.js`): 아이디·비밀번호(`autocomplete="off"`), 비밀번호 저장 안내, 역할 → 행선지 표(`kiosk` → `/ui/librarian/`, `admin` → `/ui/admin/`), 401 문구 표시, 그 밖의 역할은 이동하지 않음(확인: 스펙 web-ui "역할별 행선지", "로그인 입력칸", "로그인·관리자 화면 내주기"의 로그인 쪽 테스트)
- [x] 1.3 이용자 `main.js`에서 `#token=` 받기와 안내 문구를 지우고 `useScreen("kiosk")`·`requireRole("kiosk")` 뒤에 화면을 그린다. 쓰는 중의 401은 같은 길로 보낸다(확인: 스펙 web-ui "받는 역할"(이용자 쪽), "이용자 화면의 로그아웃"의 테스트, 기존 이용자 화면 테스트 통과)

## 2. 이용자 화면의 두 시계 (Opus, design 결정 4)

- [x] 2.1 `librarian/idle.js`를 두 시계(상수 `IDLE_MS` 60초·`IDLE_WARN_MS` 45초·`CAP_MS` 180초·`CAP_WARN_MS` 150초, 이용 시작은 비운 뒤 첫 입력, 무입력은 답 받는 동안 멈춤, 상한은 멈추지 않음)와 `onWarn`·`onClear`로 바꾼다. 개발용 `?idle_seconds=`는 그대로 두고 `?cap_seconds=`를 더한다(확인: 스펙 web-ui "시간 값"의 테스트)
- [x] 2.2 `librarian/index.html`·`librarian.css`에 알림 띠 `#clear-warning`(`role="status"`, 남은 초, 무입력일 때만 [계속 쓰기])을 두고, `main.js`에서 상한으로 비울 때 진행 중인 답을 abort한 뒤 `resetAll`한다(확인: 기존 입력칸 비우기 테스트 통과, B4~B6은 9.3에서)

- [x] 2.3 시작 화면(2026-11-23 사용자 결정으로 더함, 로그아웃 아님): `index.html`에 `#start-screen`(숨김이 아님), `librarian.css`, `main.js`에서 시계의 `onClear`만 시작 화면을 다시 보이고 [새 대화]·세션 끝은 그대로 비움, 누르면 사라지고 입력칸에 포커스(확인: 스펙 web-ui "처음 열 때", "로그아웃하지 않음"의 테스트, B6은 9.3에서)

## 3. 관리자 화면 틀 (Sonnet, design 결정 5)

- [x] 3.1 새 `shared/dom.js`(`textContent`만 쓰는 요소 도우미)와 `public/admin/`(`index.html`, `admin.css`, `main.js`)를 만든다. 머리(기관 이름, 아이디, [로그아웃]), 탭 넷과 hash 전환, 숨긴 탭 hash는 `#chat`으로, 720px 아래 한 줄 쌓기, `useScreen("admin")`·`requireRole("admin")`, `pageshow` `persisted`에서 화면을 비우고 다시 확인, [로그아웃]은 `POST /auth/logout` → 키 지움 → 로그인 화면(확인: 스펙 web-ui "화면 HTML", "화면이 참조하는 파일", "받는 역할"(관리자 쪽)의 테스트)
- [x] 3.2 `GET /library`의 `loan_mode`가 `internal`일 때만 `#tab-overdue`·`#group-templates`의 `hidden`을 한 곳에서 푼다. 못 읽으면 숨긴 채 둔다(확인: 스펙 web-ui "처음 그린 화면"(관리자), "보이는 조건"의 테스트)

## 4. 운영 대화 (Sonnet, design 결정 6)

- [x] 4.1 `admin/chat.js`: `shared/sse.js`로 사건 읽기, 본문 `{session_id, message}`, `status` 한 줄, 답은 `pre-wrap`·`textContent`, `unsupported` 표시, 보내는 동안 잠금, [새 대화](abort, 대화 종료), 404는 세션 버림·안내·문장 되돌림, 409·429 문구(확인: 스펙 web-ui "대화 요청의 본문"(운영 에이전트)의 테스트)
- [x] 4.2 `refreshPendingCount()`: 화면을 열 때와 `done` 뒤 큐레이션·구매 요청서(자체 대출이면 틀도) `?status=pending_approval` 개수를 [승인 목록] 탭에 보인다(확인: 외부 대출 기관에서 틀 목록을 부르지 않는 곳이 `loan_mode` 조건 안에 있음을 3.2 테스트가 함께 봄, B8은 9.3에서)

## 5. 승인 목록 (Sonnet, design 결정 7)

- [x] 5.1 `admin/approvals.js`: 종류별 설정 표로 세 묶음, [승인 대기]/[전체], 줄을 누르면 상세(늘 `GET /{id}`), 상태별 동작(승인 `confirm()`·반려 사유 필수·큐레이션 내리기), 요청 중 잠금, 오류는 `ApiError.detail`을 상세 안에(503에 덧붙임), 성공하면 상세·목록·승인 대기 수를 다시 읽음(확인: 개발 서버에서 큐레이션 하나를 반려·승인·내리기 해 보고 결과를 9.2 curl과 맞춤)
- [x] 5.2 구매 요청서 상세: 확정 전 추정 단가·금액·총액·조회 시각, "가격 없음", `missing_price_count`·`unavailable` 안내, 승인 확인 문구(정가 다시 조회·희망도서 닫기), 확정본의 기록 금액·출처·"고칠 수 없어요"(확인: B11은 9.3에서)

## 6. 희망도서·오늘의 연체와 회원 값 경계 (Opus, design 결정 8)

- [x] 6.1 `admin/requests.js`: `?status=requested&limit=20&offset=n`, [더 보기], [닫기](`confirm()` 뒤 `PATCH`, 성공하면 줄 지움)(확인: 스펙 web-ui "회원번호를 보내는 곳"의 테스트가 관리자 파일에서도 통과)
- [x] 6.2 `admin/overdue.js`: 오늘 날짜·건수·줄(문안 `pre-wrap`), 409는 서버 문구 + 틀 만들기 안내(확인: B10은 9.3에서)
- [x] 6.3 두 탭의 `show()`가 목록을 비우고 서버에서 다시 읽는다(탭을 떠날 때 지우지 않음, 2026-11-23 사용자 결정으로 바뀜). 복사·출력 버튼 없음(확인: 스펙 web-ui "회원 값을 읽는 곳", "콘솔 출력 없음"의 테스트, B13은 9.3에서)

## 7. 소스 검사와 회귀 (Sonnet, design 결정 9)

- [x] 7.1 `tests/platform/test_web_ui.py`: `_reachable`을 세 HTML에서 시작하고, 허용 경로 목록을 넓히고, 화면 스크립트의 경로·메서드가 `app.routes`에 있는지 보는 테스트와 1~6에서 아직 없는 시나리오 테스트를 더한다. 테스트 이름이나 docstring에 요구사항 이름을 적는다(확인: 스펙 web-ui delta의 브라우저 확인이 아닌 시나리오마다 테스트가 하나 이상)
- [x] 7.2 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`가 통과한다(확인: 통과 수를 design "결과"에 적음)

## 8. 서버 흐름 확인 (Opus, design 결정 10)

- [x] 8.1 YES24 정가 조회 예상 호출 수(약 5회 이하)를 알리고 사용자 승인을 받은 뒤, 개발 서버에서 curl로 design 결정 10의 순서를 확인한다. 확인용 데이터는 끝에 지우거나 되돌린다(확인: 각 단계의 상태 코드와 응답 요지를 design "결과"에 적음)

## 9. 문서와 사용자 확인 (Sonnet, 9.3은 사용자)

- [x] 9.1 `app/web/README.md`(구성에 `login/`·`admin/`·`dom.js`, 화면별 토큰 규칙, 두 시계, 관리자 화면 규칙, 개발용 토큰 절을 로그인으로 바꿈, 키오스크 PC의 "비밀번호 저장 안 함" 운영 안내)와 `CLAUDE.md`의 이용자 화면 여는 명령 줄을 고친다(확인: 두 문서에 `#token=`이 남지 않음)
- [x] 9.2 사용자가 브라우저로 확인할 계정(자체 대출·외부 대출 기관의 키오스크·관리자)과 준비 데이터(승인 대기 초안, 연체 대출, 가격 없는 ISBN이 든 요청서)를 개발 DB에서 확인해 안내한다(확인: 계정과 준비 상태를 사용자에게 알림)
- [x] 9.3 사용자가 design의 B1~B15를 확인한다(확인: 결과를 design "결과"에 적음)

## Workflow follow-up

- 사용자 확인 뒤 `/opsx:archive`: `platform/web-ui` 병합, `docs/roadmap.md`(24 상태, 24b·24c 행 추가, "`add-web-ui`에서 미룸" 절), `CLAUDE.md` 현재 단계
- 커밋은 사용자가 요청하면, PR은 제목·본문 텍스트만
