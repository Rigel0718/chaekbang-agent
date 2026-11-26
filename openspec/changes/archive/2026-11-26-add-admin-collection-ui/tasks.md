# Tasks

## 1. 서버: 사본 찾기와 접속 기록 (Opus, 경계 작업)

- [x] 1.1 `GET /holdings`에 `q`(strip 뒤 1~100자, 공백만이면 422) 인자를 더하고 조건·정렬은 `services/holdings.py`의 `list_holdings`에 둔다(design 결정 1: 등록번호 같음 또는 기관 값·공식 서지 서명·저자 `ilike` autoescape, `q`만 있으면 제적 포함, 등록번호 일치 → `korean_order` 표시 서명 → 등록번호 → id). 확인: `tests/catalog/test_holdings_api.py`에 `catalog/holdings` "사본 조회" 새 시나리오마다 테스트(등록번호, 서명 일부, 공식 서지 값, 저자, 모든 상태, 상태와 함께, 와일드카드, 빈 찾기 글자, 기관 분리), 기존 사본 조회 테스트 통과
- [x] 1.2 `app/core/`에 질의 문자열을 지우는 기록 필터를 새로 만들고, `app/main.py`가 불러올 때 `uvicorn.access`에 한 번만 붙인다(design 결정 3). 확인: 새 테스트 파일(`tests/core/test_access_log.py`)에 `platform/request-logging` 시나리오 셋(회원 찾기 주소, 질의 문자열 없는 주소, 앱을 불러오면 한 번만 붙음)과 인자 모양이 다른 기록은 그대로 통과하는 테스트
- [x] 1.3 `app/library/README.md`(사본 찾기 인자), `app/core` 기록 필터 설명을 둘 곳(`app/main.py` 주석 또는 README의 공통 도구 절). 확인: 문서에 `q`의 조건과 "접속 기록은 경로만"이 적혀 있다
- [x] 1.4 `uv run pytest`, `uv run ruff check . && uv run ruff format .` 통과 뒤 멈추고 알린다

## 2. 화면: 탭 셋 (Sonnet, 마크업·스크립트)

- [x] 2.1 `admin/index.html`·`main.js`: 탭 여덟, [장서]는 숨김으로 시작하고 `loan_mode`를 읽는 한 곳에서 `internal`일 때만 보임, [회원]·[휴관일]은 늘 보임, hash `#collection`·`#members`·`#closures`, 숨긴 탭 주소는 운영 대화(web-ui "관리자 화면의 탭과 운영 방식")
- [x] 2.2 `admin/collection.js`(새로 만든다): 찾기 표·[더 보기]·탭에 돌아오면 다시 읽기, 상태 고르기(넷, 제적만 확인, 실패·취소 시 되돌림), 대출 중 줄의 [반납](확인 뒤 `POST /loans/return`), [책 등록](ISBN 확인 → 기관 도서 → 사본, 만든 id 들고 있기, 409면 ISBN으로 다시 확인)(design 결정 2, 4)
- [x] 2.3 `admin/members.js`(새로 만든다): 들어오면 첫 20명, 찾기, [더 보기], 등록, [고치기](이름·번호, 빈 번호는 `null`), [삭제](확인 뒤), 입력칸 `autocomplete="off"`(web-ui "회원 화면")
- [x] 2.4 `admin/closures.js`(새로 만든다): 오늘부터 365일 목록, 더하기(날짜 필수, 사유 `maxlength` 100), [삭제](확인 뒤)(web-ui "휴관일 화면")
- [x] 2.5 `admin/admin.css`: 세 탭의 표·입력칸·좁은 창에서 표만 가로 스크롤. 성공 문구 없음, 실패 문구 한 줄
- [x] 2.6 `tests/platform/test_web_ui.py`: web-ui delta의 소스 검사 시나리오마다 테스트(부르는 경로 목록에 새 경로, 탭 처음 숨김·보이는 조건, 회원 값 읽는 곳에 `members.js`, 사본 찾기는 `q`·`limit`·`offset`만, 읽는 필드가 `HoldingRead`에 있음, 상태 고르기 값이 `HoldingStatus`에서 `on_loan` 뺀 넷, 제적만 확인, 책 등록의 확인 순서와 이어 하기, 보내는 키가 `LibraryBookCreate`·`HoldingCreate`·`MemberCreate`·`MemberUpdate`에 있음, 회원 삭제 확인, 회원 입력칸 자동 완성 끔, 휴관일 `from`·`to` 365일, 사유 길이가 `ClosureCreate` 상한과 같음). 기존 HTML 해석 금지·콘솔 없음 검사 통과
- [x] 2.7 `app/web/README.md`: 관리자 화면 탭 여덟과 운영 방식별 표시, 세 탭의 규칙, 시험 절의 새 검사
- [x] 2.8 `uv run pytest`, `uv run ruff check . && uv run ruff format .` 통과 뒤 멈추고 알린다

## 3. 확인용 DB와 브라우저 확인 (Opus)

- [x] 3.1 개발 DB 상태(햇살·푸른숲의 사본 상태별 수, 대출 중 사본, 회원 수, 휴관일)를 읽기 전용으로 보고, 개발 DB를 템플릿으로 확인용 DB를 만들고 그 DB로 서버를 띄우는 명령을 드린다. 확인에 쓸 ISBN·등록번호·회원 값 목록을 저장소 안 git 제외 폴더에 만들어 둔다
- [x] 3.2 B1… 브라우저 확인 목록(계정, 누를 것, 보여야 할 것)을 드린다. LLM·외부 API 호출 없음(새 책의 공식 서지 채움은 하지 않는다)
- [x] 3.3 사용자 확인 결과를 design에 "확인 결과와 미룬 일"로 적고, 고칠 것이 나오면 tasks에 더해 알린다

## 4. 확인 뒤 피드백 (2026-11-26)

- [x] 4.1 서버(Opus): `list_holdings`의 `q` 없는 순서를 최근 등록순(`created_at` 내림차순, id 내림차순)으로. `MemberCreate.phone` 필수(없음·빈 값·null 422), `MemberUpdate`는 `phone`에 null·빈 값 422(보내지 않으면 그대로). 확인: `catalog/holdings` "최근 등록순", `circulation/members` "전화번호 누락"·"전화번호 지우기"·"번호 없는 기존 회원의 이름 고치기"·"번호 없는 회원 여럿"(직접 저장) 테스트, 번호 없이 회원을 만들던 기존 API 테스트를 번호와 함께로 고침, `uv run pytest` 통과
- [x] 4.2 화면(Sonnet): 공통 하이픈 함수 `shared/phone.js`(새로 만든다, 보이기·칸 입력), `admin/members.js`·`overdue.js`의 번호 표시와 회원 칸, `librarian/actions.js` 로그인 칸. `admin/collection.js`의 처음 목록·[전체 보기]·빈 칸 찾기=처음 목록, `members.js`의 번호 필수와 번호 없는 기존 회원 고치기. 확인: web-ui "휴대폰 번호의 하이픈"(보이는 꼴, 한 곳의 규칙)·"처음 목록과 전체 보기"·"번호는 필수" 소스 검사 테스트, 기존 회원 값 검사 통과, `app/web/README.md`
- [x] 4.3 `uv run pytest`, `uv run ruff check . && uv run ruff format .` 통과 뒤 다시 확인할 B(B3 처음 목록, B11·B13·B14 번호 필수, 하이픈 B17~B19)를 확인 파일에 적고 멈춘다

## Workflow follow-up

- 사용자 확인 뒤 `/opsx:archive`: 미룬 일에 "화면 문구 전체 다듬기(따로 change)"를 더하고 `add-overdue-notice` 미룬 일의 "전화번호 표시 형식(하이픈)"을 끝남으로. `docs/roadmap.md`에 이 change 줄과 상태, 확정된 기본값(사본 찾기·접속 기록), "`add-admin-collection-ui`에서 미룸" 절(proposal의 하지 않는 것), 기존 미룬 일의 `add-admin-collection-ui`(가칭) 줄을 끝남으로. `CLAUDE.md` 현재 단계(다음 후보 `add-observability-deploy`)
- 커밋은 요청할 때만, PR은 제목·본문 텍스트만
