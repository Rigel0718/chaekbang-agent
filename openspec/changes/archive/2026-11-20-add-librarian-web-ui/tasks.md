순서: 1은 서버 쪽 서빙과 계약 테스트의 틀이고, 2~4는 공통 모듈과 화면, 5는 문서, 6은 브라우저 확인이다. 화면 동작은 pytest가 아니라 design의 브라우저 확인 항목(B1~B13)으로 확인한다(design 결정 11).

## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 서빙 (design 결정 1)

- [x] 1.1 `app/web/public/librarian/index.html`(빈 틀)과 `app/main.py`의 `/ui` 마운트(`public/`만, `html=True`)를 만든다(확인: 스펙 web-ui "이용자 화면 내주기"의 화면 HTML·없는 파일·문서는 내주지 않음 테스트, "화면 경로가 API를 가리지 않음" 셋, "기존 API만 사용"의 서버 경로 테스트, `tests/platform/test_web_ui.py`)
- [x] 1.2 `app/web/README.md`와 `app/web/CLAUDE.md`(`@README.md`)를 쓴다. 기존 API만 쓰기, 저장 규칙, 글자로만 넣기, `safeUrl`, `book.필드` 형태, 4분 30초와 서버 설정 이름, 최신 크롬·엣지 가정을 적는다(확인: 파일이 있고 `/ui/README.md`가 404)

## 2. 공통 모듈 (design 결정 4·5·9·10)

- [x] 2.1 `public/shared/api.js`에 토큰 읽기·쓰기·지우기(`localStorage` 키 하나), 경로 함수(suggest, search, similar, messages, sessions, guide), 오류 구분(401·404·409·429·그 밖)을 만든다(확인: 스펙 "기존 API만 사용"의 화면이 부르는 경로, "브라우저 저장"의 저장소 사용 테스트)
- [x] 2.2 `public/shared/sse.js`에 fetch 스트림을 `{name, data}` 사건으로 푸는 함수(청크 경계 버퍼, `done` 없이 끝남 알림)를 만든다(확인: "서버 값의 안전한 표시"의 HTML 해석 없음 테스트가 shared 파일도 검사)
- [x] 2.3 `public/shared/card.js`와 `base.css`에 카드 그리기를 만든다. 종류 셋, 표지 자리 표시와 출처 링크, 대출 상태와 갱신 시각, 서가·청구기호, 이유·근거 한 줄, 버튼 자리, `safeUrl`을 넣는다(확인: "카드 필드와 응답 스키마 일치" 둘의 테스트(없는 필드를 넣은 임시 소스로 실패 확인 포함), "서버 값의 안전한 표시"의 주소 형식 테스트)

## 3. 이용자 화면 (design 결정 2·3·5·8)

- [x] 3.1 `librarian/index.html`, `librarian.css`, `main.js`에 화면 틀(반납일 머리, 대화 영역, 입력창과 주의 문구, 담기 사이드, 새 대화), 토큰 넣기(`#token=` → 저장 → 주소에서 지움), 반납일 머리(`registered`, 휴관, `due_is_estimate`)를 만든다(확인: 1.1의 화면이 참조하는 파일 테스트가 모든 모듈로 통과, 소스 검사 테스트 통과)
- [x] 3.2 `suggest.js`에 자동완성을 만든다. 200ms 기다리기, `AbortController`, 화살표·Enter·Esc, 조합 중 Enter 무시, "모두 찾기" 줄, 검색 카드 줄 블록을 넣는다(확인: 소스 검사 테스트 통과. 동작은 6의 B1·B2·B4·B5)
- [x] 3.3 `chat.js`에 턴 흐름을 만든다. 보내는 동안 입력 잠금, `session`·`found`·`status`·`answer`·`done` 그리기, 고른 책 턴, [이 책 물어보기], 카드 펼치기와 한 권 자동 펼침, `suggest_book_request` 안내, 오류 표시를 넣는다(확인: 소스 검사 테스트 통과. 동작은 6의 B3·B6·B7·B8·B11)

## 4. 담기와 비우기 (design 결정 6·7)

- [x] 4.1 `basket.js`에 담기(메모리 Map, [담김], [x], 좁은 화면 접기)를 만든다(확인: "브라우저 저장" 테스트 통과. 동작은 6의 B9)
- [x] 4.2 `idle.js`와 `main.js`에 비우기를 만든다. [새 대화](DELETE), 4분 30초(답 받는 동안 멈춤, 확인용으로 짧게 바꿀 수 있는 값), 세션 404 세 경우를 한 함수로 처리한다(확인: 소스 검사 테스트 통과. 동작은 6의 B10·B13)

## 5. 문서

- [x] 5.1 `docs/design.md` 이용자 화면 절에 화면 주소, 카드 누르기·담기·비우기 규칙을 짧게 더하고, `CLAUDE.md` 자주 쓰는 명령에 화면 주소(`/ui/librarian/#token=…`)를 한 줄 더한다(확인: 두 문서에 화면 주소가 있고 내용이 design.md 결정과 같다)
- [x] 5.2 `uv run pytest`와 `uv run ruff check . && uv run ruff format --check .`를 돌린다(확인: 모두 통과, 통과 수를 design "결과"에)

## 6. 브라우저 확인 (design 결정 11)

- [x] 6.1 개발 DB `실험용 가상 작은도서관`의 키오스크 토큰과 임베딩 서버로 LLM 없는 항목(B1·B2·B6·B7·B9·B10·B12·B13)을 확인하고, 스크린숏과 잘 안 된 것을 design "결과"에 적는다(확인: 항목마다 판정 기록)
- [x] 6.2 LLM을 부르는 항목(B3·B4·B5·B8·B11)의 예상 호출 수를 알리고 승인을 받은 뒤 확인해서 결과를 적는다(확인: 승인 기록과 항목마다 판정 기록)
- [x] 6.3 6.1·6.2에서 고친 것이 있으면 5.2를 다시 돌린다(확인: 모두 통과)

## Workflow follow-up

- 사람이 화면을 확인한 뒤 archive한다. archive 전에 `docs/roadmap.md`의 이 change 상태와 새 미룬 일을 고친다.
