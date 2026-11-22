순서: 1~2는 LLM 없이 희망도서를 서버 끝까지 만들고, 3은 화면, 4는 AI 사서 문구와 회원번호 카나리아, 5는 평가, 6은 문서와 마무리다. 모델은 **Sonnet**(0~3, 6)과 **Opus**(4~5)로 나눈다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

## 0. 시작 전 기준 (Sonnet)

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 저장 (Sonnet, design 결정 2, Migration Plan)

- [x] 1.1 새 `app/library/models/book_request.py`(`book_requests`: design 결정 2의 칸, `BookRequestStatus` StrEnum, 복합 외래 키 `(library_id, member_id)` RESTRICT, 상태·서명·키 CHECK, `requested`인 같은 회원·같은 키의 부분 UNIQUE 인덱스)를 만들고 `app/models.py`의 `TENANT_TABLES`와 모델 등록에 넣는다. 마이그레이션을 만들고 개발 DB를 백업한 뒤 `&&`로 업그레이드한다(확인: 스펙 database-schema "빈 DB에 upgrade"(26개), "모델과 마이그레이션 일치", "희망도서 테이블의 저장 계층 규칙", "다른 기관 회원으로 희망도서 직접 저장"의 테스트, `alembic downgrade -1 && alembic upgrade head`가 됨)

## 2. 희망도서 service와 REST (Sonnet, design 결정 2·3)

- [x] 2.1 `app/library/schemas/book_request.py`(`BookRequestCreate`·`BookRequestRead`·`BookRequestAdminRead`·`BookRequestUpdate`)와 `app/library/services/book_requests.py`의 신청을 만든다: 서명 정리·길이, ISBN `normalize_isbn`, 회원 확인(번호를 메시지에 넣지 않음), 같은 회원·같은 키 `requested` 중복 409(IntegrityError도 409), 추천 가능한 책의 ISBN 409(확인: 스펙 book-requests "정상 신청", "ISBN 정규화", "잘못된 ISBN", "서명 누락", "외부 대출 기관의 신청", "없는 회원번호", "다른 기관의 회원번호", "같은 회원의 같은 서명", "다른 회원의 같은 서명", "닫힌 신청 뒤 다시 신청", "소장한 ISBN", "다른 기관만 소장한 ISBN", "서명만 같은 신청"의 테스트)
- [x] 2.2 목록(상태 거르기, 최신순, 페이지, 회원번호)과 닫기(`closed`만, 이미 닫힌 것은 그대로, `closed_at`)를 만든다(확인: 스펙 book-requests "상태로 거르기", "닫기", "되돌리기 거부"의 테스트)
- [x] 2.3 `app/library/api/book_requests.py`(`POST`는 `CurrentStaff`, `GET`·`PATCH`는 `AdminStaff`)를 만들고 `app/main.py`에 등록한다(확인: 스펙 book-requests "신청 응답의 회원 값", "키오스크의 목록과 닫기", "다른 기관의 목록", "다른 기관의 신청 닫기"의 테스트)
- [x] 2.4 `services/members.py`의 삭제가 그 회원의 신청 `member_id`를 먼저 비운다(확인: 스펙 members "희망도서 신청이 있는 회원 삭제"의 테스트, 기존 회원 삭제 테스트 통과)
- [x] 2.5 `app/library/README.md`에 희망도서 절(저장 값, 중복·소장 검사, 권한, 회원 삭제)과 구성 표의 새 파일, AI 사서 절의 "쓰기 tool은 없다" 문장 갱신을 적는다(확인: README에 희망도서 절이 있음)

## 3. 이용자 화면 (Sonnet, design 결정 4·5)

- [x] 3.1 `shared/api.js`에 `borrow`, `returnBook`, `requestBook`을 더하고 `ApiError`가 404 서버 문구도 담게 한다(대화 쪽 404 처리는 그대로)(확인: 기존 화면 테스트 통과, 스펙 web-ui "화면이 부르는 경로"의 테스트를 아홉 경로로 고쳐 통과)
- [x] 3.2 새 `librarian/actions.js`와 `index.html`·`librarian.css`의 칸(세 모드, `autocomplete="off"`, [대출·반납]은 `hidden`으로 시작), `main.js`의 조립(안내의 `loan_mode`로 버튼, `resetAll()`이 칸 닫기·지우기, 보내는 동안 `idle.pause`), `chat.js`의 희망도서 안내 문구와 [희망도서 신청] 버튼을 만든다(확인: 스펙 web-ui "회원번호를 보내는 곳", "대화 요청의 본문", "처음 그린 화면", "버튼을 보이는 조건", "입력칸 자동 완성"의 정적 테스트, 기존 저장소·HTML 해석·`safeUrl` 검사 통과)
- [x] 3.3 `app/web/README.md`의 구성 표와 "기존 API만 쓴다" 경로 목록, 입력칸 규칙(회원번호 행선지, 비우기)을 고친다(확인: README에 `actions.js`와 세 경로가 있음)
- [x] 3.4 서버를 띄워 curl로 자체 대출 기관의 빌리기·반납·희망도서와 외부 대출 기관의 409를 확인하고, 사용자에게 design의 확인 항목 B1~B9를 요청한다(확인: curl 결과와 사용자 확인 기록을 design "결과"에 적음. 스펙 web-ui "화면 비우기", "칸 닫기"는 B8로 확인)

## 4. AI 사서 v8과 회원번호 카나리아 (Opus, design 결정 1·6·7)

- [x] 4.1 `app/library/librarian.py`의 `LOAN_NOTES`와 `BASE_PROMPT` 희망도서 문장을 고치고 `PROFILE_VERSION`을 v8로 올린다. tool 목록은 그대로다(확인: 스펙 librarian "자체 대출 기관의 안내 문구", "외부 대출 기관의 안내 문구", "운영 방식별 tool 목록", "대화 후 데이터 변화 없음"(희망도서 행 포함)의 테스트, 기존 사서 테스트 통과)
- [x] 4.2 대화 요청에 `member_number` 칸을 보내면 422이고 LLM을 부르지 않는지 테스트한다(확인: 스펙 librarian "대화 요청의 회원번호 칸"의 테스트)
- [x] 4.3 카나리아 테스트: 같은 키오스크 토큰으로 카나리아 회원번호의 대출·반납·희망도서 신청 뒤 대화 두 턴(하나는 그 번호를 문장에 적음)을 보내고, 가짜 LLM이 받은 모든 요청과 `chat_messages`·`agent_runs`·`agent_steps`의 텍스트 칸에 그 번호가 없음을 본다(확인: 테스트 통과, docstring에 스펙 librarian "쓰기 tool 없음"과 chat-sessions "개인정보 가리기"를 적음)

## 5. 평가 (Opus, design 결정 8)

- [x] 5.1 `evals/librarian`의 `Scenario`에 `loan_mode` 칸을 더하고 실행이 시나리오별 운영 방식의 기관·프로필을 쓰게 한다. 시나리오 4개(`loan-how`, `loan-external`, `loan-member-number`, `book-request-how`)와 회원번호를 묻는 문장 정규식을 더한다(확인: 가짜 LLM 평가 테스트(`tests/evals/test_librarian_eval.py`) 통과, 시나리오 추적 이름이 스펙 librarian의 시나리오와 맞음)
- [x] 5.2 실제 LLM 실행: 호출 수를 알리고 승인을 받은 뒤 새 시나리오 4개, 그다음 사서 평가 전체를 한 번 돌려 design "결과"에 적는다(확인: 새 시나리오 모두 맞음, 전체가 지난 결과보다 나빠지지 않음. 2026-11-22 사용자 결정으로 새 4개만 돌림: 4/4 맞음, `asks_personal` 오탐 1건은 판정을 고쳐 다시 채점해 위반 0. 전체 회귀는 미룸, design 결과)

## 6. 문서와 마무리 (Sonnet)

- [x] 6.1 `docs/design.md`(AI 사서 tool 표의 쓰기 세 줄을 화면 기능으로, `search_external_books`는 미룸, 그 아래 문단, 공용 PC 문단, 테이블 목록의 `book_requests`)를 고친다(확인: 문서에 각 항목이 있음)
- [x] 6.2 전체 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`를 돌린다(확인: 모두 통과, 0.1보다 테스트 수가 늘어남. 1897 통과·7 건너뜀, 0.1은 1843)

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다. 그 전에 `docs/roadmap.md`의 23 상태와 "`add-librarian-actions`에서 미룸"(design "미룰 것")을 고친다.
- `CLAUDE.md` "현재 단계"를 다음 change(`add-purchase-request`)로 바꾼다.
