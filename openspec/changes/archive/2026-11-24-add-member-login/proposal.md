## Why

이용자 화면(키오스크)에서 빌리기와 희망도서 신청은 회원번호를 직접 쳐야 하고, 담기는 누가 하는지 모른 채 된다. 작은도서관은 대면 가입이라 관리자가 회원을 등록할 때 휴대폰 번호를 함께 받을 수 있다. 번호만으로 로그인하는 회원 세션을 두면 이용자는 회원번호를 외우거나 칠 필요가 없고, 담은 책을 이용자 단위로 다룰 길(24c)이 열린다. 사용자가 `polish-web-ui` 탐색에서 걸린 점으로 꼽았다(roadmap 24e, 2026-11-24 탐색).

## What Changes

- **휴대폰 번호 회원 로그인** `POST /auth/member-login`(`{ phone }`)과 `POST /auth/member-logout`. 비밀번호는 없다. 응답은 회원 토큰과 만료 시각뿐이고 이름·회원번호를 돌려주지 않는다. 없는 번호와 형식이 틀린 번호는 같은 404 "번호를 확인해 주세요"이고 받은 번호를 메시지·로그에 남기지 않는다.
- **회원 세션**: 새 테이블 `member_sessions`. 키오스크 세션에 묶고 수명은 3분이다. 토큰은 별도 헤더 `X-Member-Token`으로 보낸다. 없거나 끝난 세션은 **403** "회원 로그인이 필요합니다"다(401이면 화면이 키오스크를 통째로 로그아웃시킨다).
- **`POST /loans`, `POST /book-requests`**: 본문의 `member_number`를 없애고 회원 세션의 회원으로 처리한다(호환 경로 없음). 반납은 지금처럼 등록번호만 쓰고 로그인이 필요 없다.
- **전화번호 유일성**: `members.phone`이 기관 안에서 유일하다(`uq_members_library_id_phone`, 번호 없는 회원은 여럿 가능, 다른 기관은 같은 번호 허용). 회원 등록·수정에서 겹치면 409다. 번호 없는 회원은 키오스크에서 직접 빌리지 못한다.
- **이용자 화면**
  - 로그인은 입력칸의 네 번째 모드다. 위 띠에는 이름·번호 없이 "로그인 중"과 [로그아웃]만 보인다.
  - 담기·빌리기·희망도서는 로그인이 필요하고, 눌렀을 때 로그인 칸을 열어 성공하면 그 동작을 이어서 한다. 빌리기·희망도서 칸에서 회원번호 칸을 없앤다.
  - 두 시계: 익명은 무입력 1분에 비우고 시작 화면(이용 상한 없음). 로그인 중에는 무입력 1분과 로그인부터 3분이 모두 **회원 로그아웃만** 한다. 로그아웃은 대화·담은 책·입력칸을 모두 비운다.
  - 위 띠에 로그인 화면(`/ui/login/`)으로 가는 [직원 로그인] 링크를 둔다(키오스크·관리자 직원이 다른 계정으로 로그인하는 길. 이동만 하고 키오스크 토큰은 지우지 않는다).
  - [새 대화]는 대화만 비우고 로그인과 담은 책은 남긴다.
  - 회원 토큰은 화면 메모리에만 두고 대출·희망도서·로그아웃 요청에만 붙인다. 대화·검색 요청에는 붙이지 않는다.
- **외부 대출 기관**: 로그인 칸은 두 운영 방식 모두 보인다. 대출·반납은 지금처럼 숨김과 서버 409다. 희망도서와 담기는 로그인 뒤에 쓴다.
- **AI 사서 프롬프트**: "회원번호로 신청·대출" 안내 두 곳을 "로그인한 뒤"로 고친다.
- **범위 밖**(design의 미룰 일): 문자 인증과 대출 알림 문자, 로그인 실패 횟수 제한, 번호 하나에 여러 회원(가족), 관리자 화면의 회원 탭, 외부 대출 기관의 회원 명부 가져오기, 담은 책을 회원에 붙여 서버에 보관하기(24c), "내 책 언제까지".

## Capabilities

### New Capabilities

- `circulation/member-login`: 휴대폰 번호 로그인, 회원 세션(3분, 키오스크 세션·기관에 묶임), 로그아웃, 회원 값을 남기지 않는 규칙

### Modified Capabilities

- `circulation/members`: 전화번호의 쓰임에 회원 로그인을 더하고, 전화번호를 기관 안에서 유일하게 한다
- `circulation/loans`: 대출은 등록번호와 회원 세션으로 한다(회원번호 본문 없음)
- `circulation/book-requests`: 신청의 회원은 회원 세션에서 정한다(회원번호 본문 없음)
- `library/staff-auth`: 키오스크가 할 수 있는 일에 회원 로그인·로그아웃과 희망도서 신청을 넣는다
- `platform/web-ui`: 회원 토큰의 행선지, 브라우저 저장, 입력칸 비우기, 두 시계, 이용자 화면의 회원 로그인
- `platform/dev-seed-data`: 시드 회원 일부에 서로 다른 전화번호를 넣는다

## Impact

- 스키마: `members`에 유일 제약, 새 `member_sessions`(Alembic 마이그레이션 하나). 개발 DB는 전화번호가 0건이라 부딪히지 않는다.
- 서버: `app/library/models/`(세션 모델), `services/member_auth.py`(새), `api/auth.py`·`deps.py`(`current_member`), `services/loans.py`·`book_requests.py`·`members.py`, `schemas/circulation.py`·`book_request.py`, `app/core/config.py`(`member_session_minutes`), `app/library/librarian.py`(프롬프트 두 곳), `app/models.py`(모델 등록).
- 화면: `app/web/public/shared/api.js`(회원 토큰, 403 매핑), `librarian/`의 `actions.js`·`basket.js`·`idle.js`·`main.js`·`index.html`·`librarian.css`.
- 테스트: 새 `tests/circulation/test_member_login_api.py`, `test_members_api.py`·`test_loans_api.py`·`test_book_requests_api.py`·`tests/platform/test_web_ui.py`·카나리아 테스트 확장, `POST /loans`·`/book-requests`를 회원번호 본문으로 부르던 기존 테스트의 헬퍼 교체.
- 문서: `app/web/README.md`, `app/library/README.md`, `docs/design.md`, `docs/glossary.md`, `docs/roadmap.md`(24c 줄 다시 쓰기, 진행 순서 24e → 24c → 24b), `CLAUDE.md`.
- 외부 API·LLM 호출: 없음(대화 평가도 돌리지 않는다. 프롬프트는 안내 문구만 바뀐다).
