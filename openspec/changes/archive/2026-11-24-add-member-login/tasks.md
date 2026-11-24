순서: 1은 스키마, 2~3은 서버(회원 세션, 대출·희망도서 전환), 4~6은 시드·프롬프트·기존 테스트 정리, 7~9는 화면, 10은 문서, 11은 통합 확인이다. 설계와 다르게 만들어야 하면 멈추고 스펙 delta부터 고친 뒤 알린다(MVP 우선, 범위를 늘리지 않음). 모든 테스트는 이름이나 docstring에 요구사항을 적는다.

모델 분리: **1·2·3·5의 카나리아·7·11은 Opus**(스키마, 인증 경계, 기관 분리, 화면 흐름과 시계), **0·4·5의 프롬프트·6·8·9·10은 Sonnet**(기준 측정, 시드, 문구, 테스트 교체, 마크업·CSS, 소스 검사, 문서). 넘칠 때 나누는 경계는 3과 4 사이다(3까지가 서버, 화면이 아직 `member_number`를 보내므로 그 둘은 함께 끝내야 한다).

## 0. 시작 전 기준 (Sonnet)

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 스키마 (Opus, design 결정 1)

- [x] 1.1 `app/library/models/circulation.py`에 `members`의 `uq_members_library_id_phone`과 `MemberSession` 모델을 더하고 `app/models.py`에 등록한다(확인: 1.3의 테스트)
- [x] 1.2 개발 DB를 백업하고 `alembic revision --autogenerate`로 마이그레이션을 만든 뒤, 백업과 `alembic upgrade head`를 `&&`로 이어 적용한다. 생성된 마이그레이션이 제약과 테이블만 건드리는지 읽어 본다(확인: `\d members`, `\d member_sessions`, `downgrade -1` 뒤 `upgrade head`가 돈다)
- [x] 1.3 `tests/platform/test_database_schema.py`: 같은 기관의 같은 전화번호 두 건 직접 저장 거부, 번호 없는 행 둘 허용, 다른 기관 같은 번호 허용, 회원 삭제로 `member_sessions` 행이 사라짐을 본다(확인: 스펙 `members` "저장 계층의 중복 거부", `member-login` "회원을 지우면 세션도 지운다")

## 2. 회원 세션 서비스와 API (Opus, design 결정 2)

- [x] 2.1 `app/core/config.py`에 코드값 `member_session_minutes = 3`을 더한다(`ENV_FIELDS`에는 넣지 않음)(확인: `platform/app-settings` 테스트가 통과)
- [x] 2.2 `app/library/services/member_auth.py`: `login`(번호 정규화, 형식 오류·없는 번호가 같은 404, 같은 키오스크 세션의 열린 세션 철회, 새 세션, 오래 지난 행 정리)과 `logout`(자기 키오스크 세션의 토큰만, 조용히 끝남)(확인: 2.5의 테스트)
- [x] 2.3 `app/library/deps.py`에 `current_member`·`CurrentMember`를 더한다(직원 컨텍스트 먼저, `X-Member-Token`, 해시·철회·만료·기관·키오스크 세션 조건, 실패는 403 "회원 로그인이 필요합니다")(확인: 2.5의 테스트)
- [x] 2.4 `app/library/api/auth.py`와 `schemas/auth.py`: `POST /auth/member-login`(`{ phone }` → `{ member_token, expires_at }`), `POST /auth/member-logout`(204). 응답에 회원 값이 없고 받은 번호를 로그에 남기지 않는다(확인: 2.5의 테스트)
- [x] 2.5 새 `tests/circulation/test_member_login_api.py`: 스펙 `member-login`의 시나리오를 모두 테스트로 둔다(정상, 하이픈 번호, 번호 없는 회원, 직원 토큰 없음 401, 없는 번호와 형식 오류의 같은 404와 번호 없는 메시지, `caplog`에 번호 없음, 다른 기관 번호 404, 두 기관 같은 번호, 유효·없음·3분 만료(`clock` 고정)·다른 키오스크 세션·다른 기관 키오스크, 키오스크 로그아웃 뒤 401, 토큰 원문이 저장소에 없음, 로그아웃 후 403·두 번 204·직원 토큰 유지, 로그인 중 회원 삭제, 대화 요청에 붙인 토큰이 기록 어디에도 없음). 같은 키오스크의 두 번째 로그인이 앞 세션을 끊는지도 본다(확인: `uv run pytest tests/circulation/test_member_login_api.py` 통과)
- [x] 2.6 `tests/library/`의 키오스크 권한 테스트(`staff-auth` 스펙)에 "키오스크의 회원 로그인"을 더한다(확인: 스펙 `staff-auth` "키오스크의 회원 로그인", "키오스크의 관리자 전용 API")

## 3. 대출·희망도서·회원 서비스 전환 (Opus, design 결정 3·4)

- [x] 3.1 `schemas/circulation.py`·`schemas/book_request.py`에서 `member_number`를 빼고, `api/loans.py`·`api/book_requests.py`가 `CurrentMember`를 받아 `member_id`를 service에 넘기게 한다. `services/loans.py`의 `create_loan`과 `services/book_requests.py`의 `create_request`는 `member_id`를 받고 회원 번호 조회를 없앤다(확인: 3.4의 테스트)
- [x] 3.2 `services/members.py`: 등록·수정에서 번호 중복이면 409(번호를 메시지에 넣지 않음), 수정은 자기 자신 제외, `IntegrityError`도 같은 409(확인: 3.3의 테스트)
- [x] 3.3 `tests/circulation/test_members_api.py`: 스펙 `members` "전화번호 유일성"의 시나리오(같은 기관 등록 중복, 형식만 다른 같은 번호, 수정 겹침, 다른 기관 201, 번호 없는 회원 여럿)와 수정된 "회원 등록과 최소 정보"를 본다(확인: 통과)
- [x] 3.4 `tests/circulation/test_loans_api.py`·`test_book_requests_api.py`: 스펙의 "정상 대출·신청(대출·신청의 회원은 로그인한 회원)", "없는 회원번호", "끝난 회원 세션", "본문의 회원번호는 쓰지 않음", "외부 대출 기관은 로그인해도 대출하지 않음", "회원 세션 없음", "세션 없는 신청", "다른 기관의 회원 세션", "삭제된 회원의 세션", 중복 신청 규칙이 세션 회원 기준임을 본다(확인: 통과)

## 4. 시드 (Sonnet)

- [x] 4.1 `app/seed/circulation.py`: 기관마다 회원 일부에 가상의 번호를 넣고(기관 안에서 겹치지 않음, 일부는 번호 없음) 반복 실행에 안전하게 한다(확인: 4.2의 테스트)
- [x] 4.2 시드 테스트에 "두 기관 모두 전화번호가 있는 회원과 없는 회원이 있고, 시드 회원의 번호가 `0`으로 시작하는 9~11자리이며 기관 안에서 겹치지 않음"을 더한다(확인: 스펙 `dev-seed-data` 두 시나리오)

## 5. AI 사서 프롬프트와 카나리아 (Sonnet 프롬프트, Opus 카나리아)

- [x] 5.1 (Sonnet) `app/library/librarian.py`의 희망도서·자체 대출 안내 두 곳을 design 결정 6대로 고친다. 대화 평가는 돌리지 않는다(확인: 프롬프트 문자열을 보는 기존 테스트가 통과)
- [x] 5.2 (Opus) `tests/library/test_librarian_actions_canary.py`: 카나리아 회원번호 대신 카나리아 전화번호의 회원으로 로그인해 대출·신청한 뒤 대화하고, 그 번호와 회원번호가 LLM 요청·대화·실행 기록에 없음을 본다(확인: 스펙 `member-login` "대화는 익명")

## 6. 기존 테스트 정리 (Sonnet)

- [x] 6.1 `tests/helpers.py`에 `add_member(phone=…)`와 `member_login(client, phone)`(회원 헤더 dict)을 더한다(확인: 6.2의 변경이 이 헬퍼로 돌아감)
- [x] 6.2 `POST /loans`·`/book-requests`를 `member_number` 본문으로 부르던 테스트(`test_purchase_requests_api.py`, `test_purchase_tools.py`, `tests/library/test_overdue_*`, `test_privacy.py`, 위 3의 파일 등 `grep`으로 찾은 곳)를 헬퍼로 바꾼다(확인: `uv run pytest` 전체가 통과)

## 7. 화면 로직 (Opus, design 결정 5)

- [x] 7.1 `shared/api.js`: `KINDS`에 `403: "member_required"`, `request()`의 `headers` 옵션, `memberLogin(phone)`, `memberLogout(token)`, `borrow(accession, token)`, `requestBook(fields, token)`(본문에서 `member_number` 제거)(확인: 9.1의 소스 검사)
- [x] 7.2 새 `librarian/member.js`: 로그인 여부·토큰 한 칸, `login`, `logout({ remote })`, `onChange`(확인: B3, B14)
- [x] 7.3 `librarian/idle.js`: 상한을 로그인에서 시작·로그아웃에서 정지하는 `memberLoggedIn`/`memberLoggedOut`, `onClear({ member })`, 알림 정보의 회원 여부. 시간 값은 그대로(확인: 9.1의 시간 값 검사, B8~B11)
- [x] 7.4 `librarian/actions.js`: 모드 `login`, `borrow`·`request`에서 회원번호 칸 제거, 기다리는 동작 하나(`pending`), 로그인 성공 뒤 이어하기, `member_required` 처리, `openLogin({ then })`(확인: B3~B7, B13)
- [x] 7.5 `librarian/main.js`·`basket.js` 연결: 비우는 길을 `resetAll`/`resetChat`/`memberLogout` 셋으로 나누고, 카드 [담기]의 로그인 가드, 위 띠의 회원 표시, 외부 대출 기관에서도 로그인 칸 표시(확인: B1, B8~B12, B15)

## 8. 마크업과 모양 (Sonnet)

- [x] 8.1 `librarian/index.html`: [회원 로그인]·"로그인 중"·[로그아웃] 자리, 로그인 모드의 번호 칸(`inputmode="numeric"`, `autocomplete="off"`), 빌리기·희망도서 칸의 회원번호 칸 제거, 알림 띠 문구 자리. [담은 책]은 숨김으로 시작(확인: 9.1의 HTML 검사)
- [x] 8.2 `librarian/librarian.css`: 위 띠의 로그인 표시와 로그인 모드 칸을 기존 `.btn`·`desk` 모양에 맞춘다(확인: B1에서 띠가 어색하지 않음)

## 9. 화면 소스 검사 (Sonnet)

- [x] 9.1 `tests/platform/test_web_ui.py`: `ALLOWED_CALLS`에 `/auth/member-login`·`/auth/member-logout`, `X-Member-Token`을 붙이는 곳이 대출·희망도서·회원 로그아웃 요청뿐임, 이용자 화면 스크립트에 `member_number`가 없음, `403 → member_required` 매핑, 저장소 접근이 그대로 두 키뿐임(회원 토큰이 저장소에 없음), 시간 값 그대로·서버 회원 세션 수명(`member_session_minutes`)과 이용 상한이 같음, HTML의 [회원 로그인]이 숨김이 아니고 [담은 책]·[로그아웃]이 숨김으로 시작, 회원번호 입력 요소 없음·로그인 번호 칸 하나, 입력칸 `autocomplete="off"`, 대화 요청 본문의 키(확인: `uv run pytest tests/platform/test_web_ui.py` 통과)

## 10. 문서 (Sonnet, 사용자 검토)

- [x] 10.1 `app/web/README.md`(18·22·27·29·39줄과 구성 표: 회원 토큰은 메모리뿐, 시계 단계, 회원 토큰의 행선지, 번호 칸, `add-member-login` 확인 항목), `app/library/README.md`(101·201·202줄, 회원 로그인 절 새로: 서비스, `current_member`, 403/404 규칙, 3분, 개인정보)(확인: 문서의 경로·파일 이름이 코드와 같음)
- [x] 10.2 `docs/design.md`(84·125·133·221줄), `docs/glossary.md`(회원번호, 회원 세션, 전화번호 유일)(확인: 문서끼리 용어가 같음)

## 11. 통합 확인 (Opus)

- [x] 11.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` 통과를 design "결과"에 적는다(확인: 0.1보다 테스트 수가 늘고 실패 없음)
- [x] 11.2 curl: 실험이 아닌 개발 기관의 키오스크 토큰으로 `POST /auth/member-login`(번호가 있는 회원 하나는 `PATCH /members/{id}`로 넣음), 같은 번호로 두 번, 틀린 번호, 헤더 없는 `POST /loans` 403, 로그인 뒤 `POST /loans` 201, 로그아웃 뒤 403을 확인해 "결과"에 적는다. LLM·외부 API 호출 0회(확인: 기록한 응답)
- [x] 11.3 사용자에게 B1~B16(design 결정 8)을 넘기고 결과를 "결과"에 적는다. 바꾼 곳이 있으면 해당 B를 다시 확인받는다(확인: 사용자 확인 끝)

## 12. 리뷰 중 변경 (사용자 요청, 2026-11-24)

- [x] 12.1 (Opus) `librarian/main.js`: `memberLogout`과 `memberLost`가 `resetChat()`로 대화(대화 종료·검색 결과·자동완성·입력)도 비운다. 알림 문구는 비운 뒤에 보인다(확인: 12.3의 소스 검사, B8·B9·B12)
- [x] 12.2 (Sonnet) `librarian/index.html`·`librarian.css`: 위 띠에 항상 보이는 `<a href="/ui/login/">직원 로그인</a>`을 더한다(확인: 12.3의 HTML 검사, B16)
- [x] 12.3 (Sonnet) `tests/platform/test_web_ui.py`: 로그아웃 두 길이 `resetChat()`를 부르는지, 직원 로그인 링크가 `/ui/login/`을 가리키고 숨김이 아니며 직원 로그아웃·토큰 지우기가 없는지 본다(확인: 통과)
- [x] 12.4 (Sonnet) `app/web/README.md`: 시계 절, 로그인과 역할 확인 절, 회원 로그인 절을 새 동작에 맞춘다(확인: 문서와 코드가 같음)

## Workflow follow-up

- 사용자가 확인한 뒤 커밋은 요청받을 때 하고, PR은 제목·본문 텍스트만 준다(push 안 함).
- archive 전에 `docs/roadmap.md`를 고친다: 24e 상태 끝, **24c 줄 다시 쓰기**(동기: 서가에서 30분 읽고 돌아와도 담은 책이 남아야 함, 회원에 붙여 서버에 짧게 보관, 책 id와 시각만, 회원 삭제 때 함께 삭제, 추천·분석에 쓰지 않음, 불러오기 코드 안은 버림), 진행 순서를 24e → 24c → 24b로, "24e 쪽 개선 사항"에 design "미룰 일"을 모은다.
- `CLAUDE.md`: "현재 단계"를 다음 24c로, 원칙 8의 회원번호 문장과 도메인 용어(회원 세션)를 고친다.
- 메모리 `two-step-search-plan`처럼 archive 결과를 메모리에 적는다.
