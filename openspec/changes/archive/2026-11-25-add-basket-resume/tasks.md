# Tasks

모델 분담: 1·2·3은 Opus(스키마·경계·service), 4·5는 Sonnet(화면 마크업·문서). 화면 확인(6)은 사용자가 직접 하고 번호는 B1~B12다.

## 1. 스키마와 모델 (Opus)

- [x] 1.1 `basket_items` 모델(`(library_id, member_id)`·`(library_id, library_book_id)` 복합 외래 키 둘 다 CASCADE, `(library_id, member_id, library_book_id)` 유일, `added_at` 색인)을 `app/library/models/circulation.py`에 더하고 `app/models.py`의 `TENANT_TABLES`에 등록한다. `tests/platform/test_database_schema.py`를 30개로 고치고, 같은 회원·같은 책 두 줄과 다른 기관 회원·기관 도서 직접 저장 거부, 회원·기관 도서 삭제 CASCADE 테스트를 더해 통과를 확인한다
- [x] 1.2 Alembic 마이그레이션 하나를 만든다. 개발 DB는 백업한 뒤 `&&`로 이어 적용하고, `alembic upgrade head`·`downgrade -1`·`upgrade head`가 오류 없이 돌며 모델과 autogenerate 차이가 없는지(스키마 테스트) 확인한다
- [x] 1.3 `Settings`에 `basket_keep_hours = 3`, `basket_limit = 10`을 코드값으로 더한다(`ENV_FIELDS`에는 넣지 않는다). `tests`의 설정 테스트가 두 값이 `.env`로 덮이지 않음을 확인하는지 맞춘다

## 2. service와 API (Opus)

- [x] 2.1 `schemas/basket.py`(`BasketBook` = `BookSummary` + `added_at`, 응답 `{books}`)와 `services/basket.py`를 만든다: `add`(`get_findable` 404, 만료 줄 정리, 이미 있으면 그대로, 10권 409), `remove`, `clear`, `list_books`(3시간 안의 줄 → `get_candidates`·`build_summaries`로 지금 값, 추천 불가는 숨김, 읽기만), `purge_expired`. `tests/circulation/test_member_basket.py`에 스펙 `circulation/member-basket`의 시나리오(담고 불러오기, 멱등, 뺐다 다시 담기, 404 셋, 10권·11권째, 3시간 경계, 다시 담아도 늘지 않음, 대출 상태 변화, 소장에서 빠짐·돌아옴, 빼기·비우기가 자기 것만, 응답 필드 허용 목록, 오류 메시지에 회원 값·책 id 없음)를 테스트 이름이나 docstring에 적어 통과시킨다
- [x] 2.2 `api/basket.py`(`GET /basket`, `PUT`·`DELETE /basket/{library_book_id}`, `DELETE /basket`, 모두 `CurrentStaff + CurrentMember`)를 만들고 `app/main.py`에 라우터를 등록한다. 회원 토큰 없음·끝남·다른 키오스크 세션은 403, 직원 토큰 오류는 401이 먼저, 관리자 토큰만으로는 403, 다른 기관 책 담기 404·다른 기관 id 빼기 204 무변화, 다른 회원·다른 기관 분리, 회원 삭제 시 담은 책 삭제(204)를 API 테스트로 확인한다
- [x] 2.3 `services/chat.py`의 `purge_forever`가 한 회차에 담은 책 `purge_expired`도 부르게 한다(`chat.py`는 함수만 부르고 테이블을 언급하지 않는다). 정리 작업이 3시간이 지난 줄만 지우고 한 기관의 실패가 다음 회차를 막지 않음을 테스트로 확인한다
- [x] 2.4 경계 테스트(`tests/platform/test_basket_boundary.py`)를 만든다: `BasketItem`·`basket_items`를 언급하는 `app/` 파일이 허용 목록뿐, `services/basket.py`에 로그 출력 없음, 담기·불러오기·빼기·비우기 전후 `recommendation_events`·`agent_runs`·`chat_messages` 행 수 불변. 통과를 확인한다

## 3. 서버 검증 (Opus)

- [x] 3.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`가 모두 통과하는지 확인한다. 기존 테스트가 `member_sessions` 등 테이블 수를 세는 곳이 있으면 맞춘다

## 4. 이용자 화면 (Sonnet)

- [x] 4.1 `shared/api.js`에 담은 책 함수 넷(`basket()`, `addBasket(id)`, `removeBasket(id)`, `clearBasket()`)을 더한다. 모두 `X-Member-Token`을 붙이고 403은 `member_required`로 매핑되며 409는 상한을 구별하게 한다. `tests/platform/test_web_ui.py`의 경로·메서드가 OpenAPI에 있고, 회원 토큰 헤더가 대출·희망도서·담은 책·회원 로그아웃 요청에만 붙는지 검사를 고쳐 통과시킨다
- [x] 4.2 `librarian/basket.js`를 서버 연동으로 바꾼다: 서버 성공 뒤에 `Map`을 바꾸고 버튼 동기화, 요청 중 그 버튼만 비활성, `load()`(로그인 직후 불러오기, 실패는 문구 없이 빈 목록), `removeAll()`, 줄에 외부 기관의 "대출 상태 … 기준"(`status_synced_at`이 있을 때), `clear()`는 화면만 비운다. 담은 순간의 글을 복사해 두던 `state` 값은 카드 값(`BookSummary`)으로 대체한다. 테스트로 소스가 브라우저 저장소를 쓰지 않음을 확인한다
- [x] 4.3 `librarian/main.js`·`index.html`·`librarian.css`를 고친다: `renderMember`가 바깥 요소의 로그인 표시 클래스를 켜고 끄고 CSS가 `.btn-basket`을 보이고 숨긴다, `memberBasket.toggle`의 로그인 분기를 없애고(담기에 기다리는 동작이 없다), 로그인 성공 뒤 `basket.load()`, 담은 책 칸에 [모두 빼기](담은 책이 없으면 숨김), 실패 문구 둘(409는 "담은 책은 10권까지예요", 그 밖은 "잠시 뒤 다시 눌러 주세요", 401·403은 지금 동작). 로그아웃·403·익명 비우기는 `basket.clear()`만 부르고 서버를 부르지 않는다. 소스 검사 테스트(`basket.clear`가 `resetChat`에 없음, 로그인 표시 클래스, `memberBasket`에 `openLogin`이 없음)를 맞춰 통과시킨다

- [x] 4.4 (브라우저 확인 중 사용자 요청) 회원 로그아웃(버튼·무입력·이용 상한)은 로그아웃 문구 없이 바로 시작 화면으로 돌린다. 로그아웃 뒤 익명 무입력 시계가 한 번 더 세던 일을 없앤다. `main.js`의 `memberLogout`이 `resetAll({ toStart: true })`를 부르고, 403(`memberLost`)은 시작 화면 없이 로그인 칸을 연다. 소스 검사 테스트를 맞추고, 스펙 delta·README·`idle.js` 주석을 고친다

## 5. 문서 (Sonnet)

- [x] 5.1 `app/library/README.md`(구성 표에 `services/basket.py`·`api/basket.py`·`schemas/basket.py`, 새 절 "담은 책", "회원 세션이 필요한 곳"에 `/basket`), `app/web/README.md`(부르는 경로, 저장 규칙, 두 시계 절의 로그아웃 뜻, 회원 토큰 행선지, 회원 로그인 절에서 담기 이어서 하기 삭제, `basket.js` 설명), `docs/glossary.md`(담은 책), `docs/design.md`(이용자 화면 흐름에 담은 책 보관이 있으면 한 줄), `CLAUDE.md`(현재 단계 줄, 도메인 용어 "담은 책")를 고친다. 문서의 경로·값이 코드와 같은지(`/basket` 경로, 3시간, 10권) 읽어 확인한다
- [x] 5.2 `docs/roadmap.md`는 archive 때 고친다(24c 줄 상태·정한 값, 진행 순서, "`add-basket-resume`에서 미룸" 묶음, 확정된 기본값 표의 담은 책 한 줄)

## 6. 브라우저 확인 (사용자 직접)

- [x] 6.1 B1 로그인 전: 카드에 [담기]가 없고 위 띠에 [담은 책]이 없다
- [x] 6.2 B2 로그인하면 이미 떠 있는 카드에도 [담기]가 바로 보이고, 로그아웃하면 바로 숨는다
- [x] 6.3 B3 [담기] → [담김], 숫자 +1, 칸에 줄. 다시 누르거나 ×로 빼면 카드 버튼이 [담기]로 돌아온다
- [x] 6.4 B4 [모두 빼기]로 비워지고, 0권이면 버튼이 숨는다
- [x] 6.5 B5 성공 기준: 담고 [로그아웃] → 같은 번호로 로그인 → 문구 없이 담은 책이 그대로 나온다
- [x] 6.6 B6 `?cap_seconds=40`으로 상한 로그아웃 → 다시 로그인 → 그대로
- [x] 6.7 B7 `?idle_seconds=20`으로 무입력 로그아웃 → 다시 로그인 → 그대로
- [x] 6.8 B8 새로 고침(로그아웃됨) → 다시 로그인 → 그대로. 브라우저 저장소에 담은 책이 없다
- [x] 6.9 B9 다른 회원 번호로 로그인하면 앞 회원의 담은 책이 안 보인다
- [x] 6.10 B10 담은 책 하나를 Swagger로 분실 처리하고 다른 하나를 대출한 뒤 다시 로그인하면 분실 책은 없고 대출한 책은 "모두 대출 중"으로 보인다
- [x] 6.11 B11 외부 대출 기관(`forest-kiosk`)에서 담기가 되고 줄에 "대출 상태 … 기준"이 보인다
- [x] 6.12 B12 [새 대화]를 눌러도 담은 책이 그대로이고, 10권 상한에서 "담은 책은 10권까지예요"가 보인다

- [x] 6.13 B13 무입력 1분이나 이용 상한이나 [로그아웃]이면 문구 없이 바로 시작 화면이 보이고, 1분을 더 기다려도 아무 일이 없다(시계가 두 번 세지 않는다)

## Workflow follow-up

- 사용자가 확인한 뒤 archive한다. archive 전에 `docs/roadmap.md`를 고친다(5.2).
- 3시간 만료와 연결 오류 문구는 브라우저로 확인하기 번거로워 pytest(만료)와 개발 도구 네트워크 차단(오류 문구)로만 본다.
