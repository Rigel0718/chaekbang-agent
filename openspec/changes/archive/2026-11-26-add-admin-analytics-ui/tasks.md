## 1. 실행기와 결과 사건 (Opus, 경계 작업)

- [x] 1.1 `app/agent/tools.py`에 `Tool.present` 선택 칸, `app/agent/runner.py`에 `ResultEvent`와 모으기·내보내기(design 결정 2). 확인: `tests/agent/test_runner.py`에 러너 delta 시나리오마다 테스트(결과 사건 순서, 정리한 답, 고정 답·실패·중단이면 없음, 없음을 돌려준 변환, 변환 없는 tool은 지금과 같음, 오류 호출은 없음, 변환 입력, 실행 기록에 없음), 기존 러너 테스트 통과
- [x] 1.2 `app/library/schemas/admin_results.py`(새 모듈, 순환 import를 피함)에 `TableResult`, `DraftLink`, 묶음 타입(결정 3). 확인: 칸 수·50줄 검증과 키 목록 테스트(`agent/admin` "결과 사건의 모양")
- [x] 1.3 `analytics_tools.py` 변환 넷(결정 4: 묶음 표, 순위 표, 사본·서명 목록 표, 설명 줄의 기간·분야·가져오기 날짜). 확인: `agent/admin` "장서·대출 묶음 표", "사본·서명 목록 표" 시나리오마다 단위 테스트(외부 대출 기관 설명 줄 포함)
- [x] 1.4 `curation_tools.py`, `overdue_tools.py`, `purchase_tools.py` 초안 변환. 확인: "초안 결과 사건" 시나리오 테스트(종류와 id뿐, 오류면 없음)
- [x] 1.5 개인정보·기관 범위 테스트 `tests/library/test_admin_results_privacy.py`(결정 5): 열 허용 목록, 회원 값 없음, 다른 기관 값 없음
- [x] 1.6 `services/admin_chat.py`에서 `ResultEvent` → SSE `result`(결정 6). 확인: SSE 사건 순서 테스트(`result` 있는 경우·없는 경우), `chat_messages`에 결과가 없음, 평가 러너 방식(이름별 dict)으로 모아도 `answer`·`done`을 읽음
- [x] 1.7 `app/agent/README.md`(`present`, 결과 사건, 기록에 남지 않음), `app/library/README.md`(tool 파일의 변환 함수, 열 허용 목록 테스트)
- [x] 1.8 `uv run pytest`, `uv run ruff check . && uv run ruff format .` 통과 뒤 멈추고 알린다

## 2. 운영 평가 회귀 (Opus)

- [x] 2.1 예상 호출 수(LLM 약 80~110회, 최악 288회, 약 $0.04, 외부 API 없음)를 알리고 승인을 받는다
- [x] 2.2 `uv run python -m evals.admin_agent`로 36개를 돌리고, 흔들림으로 기록된 `science-word`·`busy-fields`·`curation-space`만 틀리면 `--only`로 한 번 더(결정 9). 그 밖이 틀리면 멈추고 보인다. 확인: 결과를 design "확인 결과와 미룬 일"에 적고 멈춘다

## 3. 화면 (Sonnet)

- [x] 3.1 `admin/chat.js`: `result` 모으기, `answer` 뒤 표·막대·잘림 문구, `answer` 없으면 버림, 모르는 종류 건너뜀, [새 대화]가 표도 비움(결정 7)
- [x] 3.2 `admin/admin.css`: 표, 막대, `.result-table` 가로 스크롤, 숫자 오른쪽 맞춤
- [x] 3.3 [초안 보기]: `chat.js`의 `DRAFT_KINDS`와 버튼, `main.js`의 `openDraft`, `approvals.js`의 `reveal`(대기 → 전체 → 찾지 못함)(결정 8)
- [x] 3.4 `tests/platform/test_web_ui.py`: `result`는 `answer` 뒤에만 그림·`table`/`draft`만 처리, `DRAFT_KINDS`가 `DraftLink`의 종류 값과 같고 승인 목록 묶음으로 감, [초안 보기] 문구, 승인 목록이 `reveal`을 내놓음, 기존 HTML 해석 금지 검사 통과
- [x] 3.5 `app/web/README.md`: 관리자 화면 규칙의 "운영 대화는 답 문장만"을 표·막대·[초안 보기]로, 시험 절에 새 검사
- [x] 3.6 `uv run pytest`, `uv run ruff check . && uv run ruff format .` 통과 뒤 멈추고 알린다

## 4. 확인용 DB와 브라우저 확인 (Opus)

- [x] 4.1 개발 DB 상태(햇살·푸른숲의 장서·대출·연체·희망도서 수)를 읽기 전용으로 보고, 개발 DB를 템플릿으로 확인용 DB를 만들고 그 DB로 서버를 띄우는 명령을 드린다(결정 10)
- [x] 4.2 B1~B14의 예상 호출 수(LLM 약 40~50회, B11의 YES24 정가 조회)를 알리고 승인을 받는다
- [x] 4.3 사용자 브라우저 확인 B1~B14 결과를 design에 적고, 고칠 것이 나오면 tasks에 더해 알린다

## Workflow follow-up

- 사용자 확인 뒤 `/opsx:archive`: `docs/roadmap.md`의 24b 상태, "운영 평가 전체 회귀" 미룬 일을 끝남으로, design의 미룬 일을 새 절로, Playwright 줄 고치기. `CLAUDE.md` 현재 단계
- 커밋은 요청할 때만, PR은 제목·본문 텍스트만
