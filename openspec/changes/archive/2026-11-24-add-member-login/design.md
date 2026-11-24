# Design

## Context

동기는 proposal의 Why를 본다. 지금 코드에서 이 설계를 정한 사실은 아래와 같다.

- `Member`(`app/library/models/circulation.py`)의 `phone`은 `String(11)`, 선택, 유일 제약 없음이다. 회원은 `(library_id, member_number)`와 `(library_id, id)`가 유일하다. 전화번호 정규화(`normalize_phone`)는 `schemas/circulation.py`에 있고 등록·수정 입력에만 쓴다. 개발 DB 회원 20명 모두 전화번호가 없다.
- 직원 세션(`StaffSession`)은 토큰 해시(`hash_token`), 만료, 철회 시각으로 저장되고, `deps.current_staff`가 요청마다 세션·계정·기관을 확인한다. 기관은 토큰으로 정하고 요청 값을 믿지 않는다.
- `POST /loans`와 `POST /book-requests`는 본문의 `member_number`를 service가 `(library_id, member_number)`로 찾는다. `LoanCreate`·`BookRequestCreate`는 `BaseModel`이라 모르는 필드는 그냥 무시한다.
- 화면: `api.js`는 401이면 키오스크 토큰을 지우고 로그인 화면으로 보낸다. `idle.js`의 `onClear`는 `main.js`의 `resetAll({ toStart: true })`를 부르고, 상한 시계는 "비운 뒤 첫 입력"에서 시작한다. `actions.js`는 입력칸 한 개로 모드 셋(빌리기, 반납하기, 희망도서)을 오가고 회원번호 칸을 갖는다. 담은 책(`basket.js`)은 메모리 `Map`이다. 화면은 브라우저 저장소에 토큰 키 하나만 쓴다.
- AI 사서 프롬프트(`app/library/librarian.py`)에 "회원번호로 신청·대출" 안내가 두 곳 있다.
- 관리자 화면에는 회원 관리 탭이 없다. 회원 등록은 `POST /members`(Swagger)로 한다.

## Goals / Non-Goals

**Goals:**
- 번호 하나로 로그인해 빌리기·희망도서·담기까지 가고, 이용자 화면 어디에도 회원번호·이름·번호가 남지 않는다.
- 회원 세션이 키오스크 세션과 기관을 넘어 쓰이지 않는다.
- 화면이 회원 세션 실패(403)와 직원 세션 실패(401)를 구분해 키오스크가 통째로 로그아웃되지 않는다.

**Non-Goals:**
- 문자 인증, 실패 횟수 제한, 가족 번호 공유, 관리자 회원 화면, 회원 명부 가져오기. 담은 책의 서버 보관은 24c다.
- 회원 세션을 AI 사서 대화·검색에 쓰는 것. 대화는 로그인 뒤에도 익명이다.

## Decisions

### 1. 스키마: 전화번호 유일 제약과 `member_sessions`

- `members`에 `UniqueConstraint("library_id", "phone", name="uq_members_library_id_phone")`을 더한다. PostgreSQL은 NULL끼리 같다고 보지 않으므로 번호 없는 회원은 여럿 둘 수 있다. 이 제약이 로그인 조회의 인덱스도 된다.
- 새 모델 `MemberSession`(`models/circulation.py`, 테이블 `member_sessions`): `id`, `library_id`, `staff_session_id`(FK `staff_sessions.id`, `ondelete=CASCADE`), `member_id`, `token_hash`(유일), `expires_at`, `revoked_at`, 생성·수정 시각. `(library_id, member_id)`는 `members(library_id, id)`로 가는 복합 FK에 `ondelete=CASCADE`를 둔다. 그래서 회원을 지우면 세션이 함께 사라지고 회원 삭제는 막히지 않는다. `member_id` 인덱스를 둔다.
- `staff_session_id`의 기관이 `library_id`와 같은지는 로그인 service가 직원 컨텍스트에서 둘을 함께 채워 보장한다(`staff_sessions`에는 `(library_id, id)` 유일 제약이 없다. 이 제약을 더하려면 마이그레이션이 하나 더 필요해 이번에는 코드로만 지킨다).
- `app/models.py`에 등록하고 마이그레이션 하나(`alembic revision --autogenerate`)로 만든다. 다른 안: 서명 토큰(JWT류) → 로그아웃해도 끊을 수 없어 버림. 직원 세션 테이블에 회원 칸 추가 → 직원 세션과 수명·철회가 섞여 버림.

### 2. 회원 세션 서비스와 의존성

- `services/member_auth.py`(새): `login(session, library_id, staff_session_id, phone)`, `logout(session, library_id, staff_session_id, token)`.
  - 번호는 `normalize_phone`으로 맞춘다. `ValueError`나 `None`(빈 값)이면 없는 번호와 같은 `NotFoundError("번호를 확인해 주세요")`다. 받은 번호는 메시지·로그에 넣지 않는다.
  - 회원은 `(library_id, phone)`으로 찾는다. 없으면 같은 404.
  - 성공하면 같은 키오스크 세션의 열린 회원 세션을 모두 철회한 뒤 새 세션을 만든다(한 PC에 로그인은 하나). 같은 트랜잭션에서 만료된 지 하루가 지난 행을 지운다(테이블이 자라지 않게). 토큰은 `new_token()`, 저장은 `hash_token()`, 수명은 `settings.member_session_minutes`(코드값 3, `.env`에 없음)이다.
  - `logout`은 토큰이 이 키오스크 세션의 것일 때만 철회하고, 아니거나 없거나 이미 끝났어도 조용히 끝난다(라우터는 204).
- `deps.py`: `current_member`가 `CurrentStaff`를 먼저 받고(그래서 직원 토큰 오류는 401이 먼저다) `X-Member-Token` 헤더(`APIKeyHeader`, `auto_error=False`)로 세션을 찾는다. 조건은 해시 일치, 철회 없음, 만료 전, `library_id == staff.library_id`, `staff_session_id == staff.session_id`다. 하나라도 틀리면 403 "회원 로그인이 필요합니다"(`HTTPException`, 인증 계층의 일). 통과하면 `MemberContext(member_id, session_id)`를 돌려주고 `CurrentMember`로 쓴다.
- 직원 세션이 끝나거나 계정이 중지되면 `current_staff`가 먼저 막으므로 회원 세션도 자동으로 못 쓴다. 따로 철회할 필요가 없다.
- 라우터(`api/auth.py`)는 얇게 service만 부른다. `POST /auth/member-login`은 `CurrentStaff`면 되고(관리자도 Swagger에서 쓸 수 있다), `POST /auth/member-logout`도 같다. 응답 스키마: 로그인은 `{ member_token, expires_at }`, 로그아웃은 204.

### 3. 대출·희망도서는 회원 세션으로

- `POST /loans`: `LoanCreate`에서 `member_number`를 뺀다. 라우터가 `CurrentMember`를 받아 `create_loan(session, library_id, accession_number, member_id)`로 넘긴다. service는 회원 조회 대신 `member_id`를 쓴다(세션이 살아 있으면 회원은 있다. 회원 삭제는 세션을 지우므로).
- `POST /book-requests`: 같은 방식으로 `BookRequestCreate`에서 `member_number`를 빼고 `create_request`가 `member_id`를 받는다. 중복 신청 규칙은 그대로 `member_id` 기준이다.
- 의존성이 service보다 먼저라서 외부 대출 기관에서 로그인 없이 대출을 부르면 409가 아니라 403이 먼저 나온다. 화면이 외부 기관에서 대출을 숨기므로 문제가 없고, 로그인한 뒤에는 지금처럼 409다(`_library_for_circulation`이 그대로다).
- `POST /loans/return`은 바뀌지 않는다(등록번호만).
- `LoanRead.member_number`는 관리자 대출 목록용으로 남긴다(`GET /loans`는 관리자 전용). 키오스크 대출 응답에는 지금도 쓰지 않으므로 이용자 화면이 표시하지 않는 규칙은 화면 쪽 검사로 지킨다.

### 4. 회원 등록·수정의 번호 중복

- `members.create_member`/`update_member`가 번호가 있으면 `(library_id, phone)` 중복을 먼저 조회해 `ConflictError`("이미 쓰는 전화번호입니다", 번호를 넣지 않음)를 내고, `IntegrityError`도 같은 409로 바꾼다. 회원번호 중복 처리(`_duplicate`)와 같은 모양이다. 수정은 자기 자신을 제외한다.

### 5. 화면 구조

```
member.js (새)   회원 상태와 토큰(메모리 한 칸), login(phone)/logout(), onChange
   |                  ^                                  ^
actions.js ----- 모드 login 추가, 기다리는 동작 하나(pending), 403이면 member.clearLocal + 로그인 칸
idle.js --------- 상한은 login에서 시작, onClear가 익명/회원을 가려 부름
basket.js ------- 로그인 전 [담기]는 로그인 칸으로(main이 연결), 로그아웃에 clear
main.js --------- resetAll(익명 비우기) / resetChat([새 대화]·세션 404) / memberLogout() 세 길
api.js ---------- memberLogin, memberLogout(token), borrow(accession, token), requestBook(.., token), 403 → member_required
```

- **`api.js`**: `KINDS`에 `403: "member_required"`를 더한다(이용자 화면은 관리자 전용 API를 부르지 않으므로 403은 회원 세션 오류뿐이다). `request()`가 `headers` 옵션을 받고 `X-Member-Token`은 `borrow`·`requestBook`·`memberLogout`만 붙인다. 토큰은 `member.js`가 쥐고 호출하는 쪽이 인자로 넘기므로 `api.js`에 회원 토큰 전역 상태를 두지 않는다. 브라우저 저장소는 쓰지 않는다.
- **`member.js`**: 로그인 여부와 토큰 한 칸. `login(phone)`은 `api.memberLogin`의 응답 토큰을 쥐고 `onChange(true)`를 부른다. `logout({ remote })`는 `remote`이면 서버 로그아웃을 실패해도 무시하고 시도한 뒤 토큰을 지우고 `onChange(false)`를 부른다. 이름·번호는 어디에도 없다.
- **`idle.js`**: 의미를 "비운 뒤 첫 입력에서 상한 시작"에서 "로그인에서 상한 시작"으로 바꾼다. `createIdleTimer`에 `memberLoggedIn()`(상한 시작, 무입력 재무장)과 `memberLoggedOut()`(상한 정지, 익명 무입력으로 처음부터 다시)를 더한다. 무입력 시계는 지금처럼 비운 뒤 첫 입력에서 시작한다. `onClear`가 `{ member }`를 받는다. 알림 정보에 `member` 여부를 담아 문구를 가른다. 상한 알림은 지금처럼 "계속 쓰기" 없이 글자만이다.
- **`actions.js`**: `MODES`에 `login`(칸 `phone`, 제출 "로그인")을 더하고 `borrow`·`request`에서 `member` 칸을 뺀다. `ui.member`로 로그인 여부와 토큰을 받는다. 로그인이 필요한 모드(빌리기, 희망도서)를 열거나 제출할 때 로그인 전이면 `login` 모드로 열고 `pending = { mode, 이미 적은 값은 칸에 남김 }`을 기억한다. 로그인 성공이면 번호 칸을 지우고 `pending`이 있으면 그 모드를 열고 없으면 칸을 닫는다. `member_required`(403) 오류는 `member.logout({ remote: false })` 뒤 같은 `pending`으로 로그인 칸을 연다. 외부 대출 기관에서는 `setLoanAvailable(false)`가 지금처럼 빌리기를 숨기고, 로그인 모드는 두 방식 모두 쓴다.
- **`basket.js`**: 담기 자체는 그대로다. 로그인 가드는 `main.js`가 카드 [담기] 콜백에서 건다. 로그인 전이면 `actions.openLogin({ then: () => basket.toggle(book) })`로 열고, 성공한 뒤 그 책을 담는다. 위 띠의 [담은 책 N]은 로그인한 동안에만 보인다. `basket.clear()`는 회원 로그아웃에서만 부른다([새 대화]와 세션 404에서는 부르지 않는다).
- **`main.js`**(리뷰 뒤 바뀜: 로그아웃은 대화도 비운다): 비우는 길 셋을 나눈다. `resetAll()`은 익명 시간 만료(전부 비우고 시작 화면), `resetChat()`은 [새 대화]·세션 404(대화·자동완성·알림·입력만, 로그인·담은 책·시계 유지), `memberLogout()`은 버튼·무입력·상한(서버 로그아웃, **`resetChat()`로 대화 비움**, 담은 책·입력칸 비움, 시작 화면 없음, 익명 시계 재무장). 서버 회원 세션 오류(403)로 화면만 로그아웃하는 `memberLost()`도 대화를 비운다. 위 띠는 `member.onChange`로 [회원 로그인]/"로그인 중"+[로그아웃]을 바꾸고 [담은 책]을 보이거나 숨긴다. [직원 로그인]은 JS 없는 `<a href="/ui/login/">`이다(이동만 하고 키오스크 토큰은 지우지 않는다. 로그인 화면은 로그인한 상태로 열려도 넘기지 않으므로 직원이 다른 계정으로 들어가는 길이 된다).
- **개인정보**: 번호는 로그인 칸의 입력 요소 값에만 있고 성공·닫기·비우기에서 지운다. 회원 토큰은 메모리뿐이라 새로 고치면 사라진다. 대화·검색 요청은 `member.js`를 거치지 않는다.

### 6. AI 사서 프롬프트

`librarian.py`의 희망도서 안내(`서명과 회원번호로 신청`)를 "화면 위 [희망도서 신청]에서 휴대폰 번호로 로그인한 뒤 서명으로 신청"으로, 자체 대출 안내를 "[대출·반납]에서 (먼저 휴대폰 번호로 로그인하고) 책의 등록번호로 직접 한다"로 고친다. 번호나 회원 값을 묻지 않고 다시 쓰지 않는 규칙은 그대로다. 안내 문구만 바뀌므로 `evals/conversation`은 돌리지 않는다(원하면 승인을 받고 대출·희망도서 안내 케이스만).

### 7. 시드와 테스트 헬퍼

- 시드(`app/seed/circulation.py`)는 기관마다 회원 일부에 가상의 번호(예: `010-0000-0001` 형태의 서로 겹치지 않는 값)를 넣는다. 일부는 번호 없이 둔다. `on_conflict_do_nothing`을 쓰는 반복 실행은 번호를 덮어쓰지 않는다.
- `tests/helpers.py`: `add_member`에 `phone` 인자를 더하고, 키오스크 클라이언트로 로그인해 `X-Member-Token` 헤더 dict를 돌려주는 `member_login(client, phone)`을 둔다. `POST /loans`·`/book-requests`를 부르던 기존 테스트(대출·희망도서·구매 요청서·카나리아·tool 테스트)는 이 헬퍼로 바꾼다.

### 8. 사용자 확인 항목

브라우저 확인은 사용자가 직접 한다. 시계는 `?idle_seconds=N`·`?cap_seconds=N`으로 줄인다. B8의 "담은 책이 사라짐"은 의도한 동작이고 24c에서 고친다.

| 번호 | 확인할 것 |
| --- | --- |
| B1 | 익명: 위 띠에 [회원 로그인]이 보이고 [담은 책]·[로그아웃]은 숨겨져 있다. 검색과 대화가 된다 |
| B2 | 익명으로 반납(등록번호만) |
| B3 | 익명으로 카드 [담기] → 로그인 칸 → 번호 입력 → 그 책이 담기고 위 띠는 "로그인 중"(이름·번호 없음) |
| B4 | `010-xxxx-xxxx`(하이픈)로 로그인된다. 없는 번호·틀린 번호는 같은 "번호를 확인해 주세요" |
| B5 | 로그인 뒤 빌리기: 회원번호 칸 없이 등록번호만, 반납 예정일 문구 |
| B6 | 익명으로 빌리기 → 로그인 칸 → 성공하면 빌리기 탭으로 돌아오고 등록번호가 남아 있다 |
| B7 | 익명으로 [희망도서 신청] → 로그인 → 신청 칸이 열리고 신청된다 |
| B8 | 로그인 중 무입력: 45초에 "N초 뒤 로그아웃해요"+[계속 쓰기], 1분에 로그아웃. 대화와 담은 책이 사라진다(시작 화면은 없음) |
| B9 | 로그인 중 상한: 2분 30초에 알림(버튼 없음), 3분에 로그아웃 |
| B10 | 로그아웃 뒤 익명 무입력 1분: 화면이 비워지고 시작 화면 |
| B11 | 익명으로 3분 넘게 계속 써도 끊기지 않는다 |
| B12 | [로그아웃] 버튼은 대화·담은 책·입력칸을 비운다. [새 대화]는 대화만 비우고 로그인과 담은 책을 남긴다 |
| B13 | 서버 세션만 끝난 상태(`?cap_seconds=600`으로 3분 넘게 기다림)에서 [빌리기] → 로그인 칸이 열리고 키오스크 로그인 화면으로는 가지 않는다 |
| B14 | 새로 고치면 로그아웃된다. 개발자 도구 저장소에 회원 토큰이 없다 |
| B15 | 외부 대출 기관: 로그인 칸이 보이고 [대출·반납]은 숨겨진다. 로그인 뒤 담기와 희망도서가 된다 |
| B16 | [직원 로그인] 링크: 누르면 로그인 화면이 열린다. 키오스크 계정으로 다시 들어가거나 뒤로 가기로 이용자 화면에 돌아와도 다시 로그인하지 않고 쓸 수 있다. 관리자 계정으로 로그인하면 관리자 화면으로 간다 |

## Risks / Trade-offs

- [남의 번호를 아는 사람이 그 회원으로 빌릴 수 있다] → 응답에 이름·번호가 없고 대면 환경이며 수명 3분. 실패 횟수 제한은 문자 인증과 함께 미룬다.
- [번호 없는 회원은 키오스크에서 직접 빌리지 못한다] → 보호자 회원으로 빌린다. 가족 번호 공유는 미룬다.
- [로그인 중 새로 고치면 로그아웃되고 담은 책이 사라진다] → 공용 PC의 의도다. 담은 책 보존은 24c.
- [마이그레이션이 겹치는 번호를 가진 다른 설치에서 실패한다] → 운영 중인 설치가 없다. 생기면 사전 검사를 더한다(미룬 일).
- [`POST /loans` 계약이 깨진다(본문 `member_number` 제거)] → 호출하는 클라이언트는 이용자 화면과 기존 테스트뿐이고 모두 이번에 함께 바꾼다. 보낸 `member_number`는 무시된다.
- [403을 화면이 회원 세션 오류로만 읽는다] → 이용자 화면은 관리자 전용 API를 부르지 않는다. 소스 검사가 부르는 경로를 고정한다.

## Migration Plan

1. 개발 DB를 백업한다(`pg_dump`).
2. `docker compose up -d db` 뒤 `uv run alembic upgrade head`를 백업과 `&&`로 이어 실행한다(도구의 여러 줄 Bash에서 `set -e`가 멈추지 않는다).
3. `uv run python scripts/seed.py`로 시드 회원 번호를 채운다(기존 시드 회원은 `on_conflict_do_nothing`이라 번호가 들어가지 않으므로, 개발 DB 확인용 번호는 관리자 `PATCH /members/{id}`로 넣거나 시드 DB를 다시 만든다. 개발 DB의 SQL `delete`는 도구 권한으로 막혀 있다).
4. 되돌리기: `alembic downgrade -1`(제약과 테이블 삭제). 데이터 손실은 회원 세션뿐이다.

## 미룰 일

문자 인증과 대출 알림 문자, 로그인 실패 횟수 제한, 번호 하나에 여러 회원(가족)과 아이 회원의 연체 연락처, 회원 번호 바꾸기 화면과 관리자 회원 탭, 외부 대출 기관의 회원 명부 가져오기, 번호 유일 제약 마이그레이션 전 겹침 검사, 상한 로그아웃 뒤 바로 재로그인 제한, "내 책 언제까지"(MVP 뒤), 담은 책의 서버 보관(24c).

## 결과

- 기준(구현 전): pytest 2055 통과·7 스킵, ruff 통과.
- 구현 뒤: pytest **2102 통과**·7 스킵, `ruff check`·`ruff format --check` 통과. 테스트 47개가 늘었다(회원 로그인 28, 회원 전화번호 유일성 API 4·스키마 3, 희망도서·대출 세션 5, 소스 검사 7 등).
- 마이그레이션: 개발 DB를 백업한 뒤(`dev_before_member_login.sql`) `alembic upgrade head` 적용, `downgrade -1` 뒤 `upgrade head`도 돈다. 새 테이블 `member_sessions`와 제약 `uq_members_library_id_phone`만 건드린다.
- curl(개발 서버, 개발 DB, LLM·외부 API 호출 0회): 번호 로그인 200(응답 키는 `member_token`·`expires_at`뿐), 하이픈 번호 로그인, 없는 번호·형식이 틀린 번호가 같은 404 "번호를 확인해 주세요", 다른 기관 번호 404, 회원 토큰 없는 `POST /loans` 403, 로그인 뒤 대출 201·반납 200(회원 불필요), 로그아웃 204 뒤 대출 403, 외부 대출 기관(푸른숲)은 로그인 200·대출 409, 직원 토큰 없는 로그인 401, 번호 겹침 수정 409, 서버 로그에 번호 0건.
- 개발 DB에 확인용으로 넣은 값(관리자 `PATCH /members/{id}`): 햇살 M0001=`010-0000-1001`, M0002=`010-0000-1002`, 푸른숲 M0001=`010-0000-2001`. curl 확인 중 햇살 사본 `SUN00001`을 빌렸다 반납한 기록이 하나 남았다.
- 시계 상태 전이(Node 시뮬레이션): 익명은 무입력에서만 비우고 상한이 없으며, 로그인 중에는 무입력·상한 모두 회원만 로그아웃으로 알리고, 로그아웃 뒤 익명 무입력이 처음부터 다시 센다.
- 구현 중 스펙 문장 하나를 고쳤다: 대출 응답(`LoanRead`)에는 기존대로 `member_number`가 있어서, `member-login`의 "회원 세션은 회원 값을 돌려주지 않음"을 "로그인·로그아웃·희망도서 응답에 없고 이용자 화면은 어떤 회원 값도 표시하지 않음"으로 맞췄다. 응답 필드는 바꾸지 않았다.
- 리뷰 중 변경(사용자 요청): ① 회원 로그아웃(버튼·무입력·상한·403)이 대화도 비운다, ② 위 띠에 `/ui/login/`으로 가는 [직원 로그인] 링크를 둔다(이동만 하고 키오스크 토큰은 지우지 않음). 스펙 delta·design·tasks(12번)를 먼저 고친 뒤 구현했다. 그 뒤 pytest **2104 통과**·7 스킵, ruff 통과. B8·B9·B12 기대값이 바뀌었고 B16이 늘었다.
- 브라우저 확인 B1~B16: 사용자가 모두 통과로 확인했다(11.3).
