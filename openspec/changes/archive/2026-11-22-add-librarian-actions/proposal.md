## Why

이용자 화면(`/ui/librarian/`)은 검색·추천·안내까지 되지만, 사서가 없는 도서관에서 이용자가 직접 책을 빌리고 돌려주고, 없는 책을 신청할 방법이 없다. 대출·반납 REST(`POST /loans`, `POST /loans/return`)는 키오스크 토큰으로 이미 되지만 화면이 없고, 희망도서는 테이블도 API도 없다. 23b `add-purchase-request`가 희망도서를 구매 근거로 읽으므로 그 전에 생겨야 한다.

회원번호는 대출과 희망도서 신청에만 쓰고(설계 원칙 8) LLM과 대화 기록에 남지 않아야 한다. 그래서 이 세 기능은 AI 사서의 tool이 아니라 **화면의 입력칸에서 REST로 바로** 보낸다. LLM은 화면의 버튼을 안내만 한다. 회원번호가 LLM 쪽으로 가는 길이 구조적으로 없다.

## What Changes

- **희망도서**: 새 테이블 `book_requests`와 REST.
  - 키오스크·관리자 `POST /book-requests`: 회원번호(필수), 서명(필수, 200자), 저자(선택, 100자), ISBN(선택, 13자리로 정규화). 그 기관에 없는 회원번호는 404, 잘못된 ISBN은 422.
  - 같은 회원이 같은 서명(이름 맞춤 키)으로 `requested` 상태의 신청이 있으면 409. 다른 회원의 같은 책은 따로 저장한다.
  - ISBN이 그 기관의 추천 가능한 책이면 409("이미 도서관에 있는 책"). 서명만으로는 소장을 검사하지 않는다.
  - 상태는 `requested` / `closed` 두 값. 관리자 `GET /book-requests`(상태 거르기, 페이지, 회원번호 포함), `PATCH /book-requests/{id}`(닫기). 키오스크 응답에는 회원번호가 없다.
  - 두 운영 방식 모두 된다. 회원을 지우면 신청 행은 남고 회원 연결만 끊는다.
- **이용자 화면**: 위쪽 막대에 [대출·반납]과 [희망도서 신청] 버튼, 세 모드(빌리기·반납하기·희망도서)의 입력칸 하나.
  - 빌리기는 등록번호와 회원번호로 기존 `POST /loans`, 반납하기는 등록번호로 `POST /loans/return`, 희망도서는 `POST /book-requests`를 부른다. 서버 문구를 그대로 보여 준다.
  - 화면은 `GET /library/guide`의 `loan_mode`로 버튼을 정한다. 외부 대출 기관과 안내를 읽지 못한 때는 [대출·반납]을 숨긴다. 서버의 409가 최종 방어선이다.
  - 회원번호는 칸이 열린 동안만 둔다. 칸을 닫거나 화면을 비우면(새 대화, 무입력, 세션 끝) 모든 입력이 지워진다.
  - AI 사서가 희망도서를 안내한 답(`suggest_book_request`)에는 [희망도서 신청] 버튼이 붙는다.
- **AI 사서 프로필 v8**: tool은 바뀌지 않는다(쓰기 tool 없음). 자체 대출 기관은 "대출·반납은 화면 위 [대출·반납]으로", 외부 대출 기관은 지금처럼 데스크 안내, 두 방식 모두 희망도서를 "화면의 [희망도서 신청]으로" 안내한다. 회원번호는 계속 묻지 않는다.
- **설계 변경**: `docs/design.md`의 AI 사서 tool 표에서 `create_loan`·`return_loan`·`request_book`을 tool이 아닌 화면 기능(REST)으로 고친다. 원칙 5의 "대출 쓰기 tool 끄기"는 화면 버튼 끄기와 서버 409로 지킨다.
- **평가**: `evals/librarian`에 운영 방식 칸과 시나리오 4개(대출 안내, 외부 대출 안내, 회원번호를 말한 대출 요청, 희망도서 안내).
- **범위 밖**: 외부 도서 검색(`search_external_books`), 회원 확인 수단(비밀번호·카드), 회원별 대출 권수 제한, "내 책 언제까지", 희망도서 상태 세분화와 관리자 화면(`add-web-ui`), 예약·연장·연체료·상호대차, 브라우저 자동화 테스트.

## Capabilities

### New Capabilities

- `circulation/book-requests`: 희망도서 신청의 저장 값, 회원번호 확인, 중복·소장 검사, 상태와 닫기, 키오스크·관리자 응답, 기관 분리

### Modified Capabilities

- `circulation/members`: 회원 삭제 때 희망도서 신청의 회원 연결을 끊음
- `agent/librarian`: "쓰기 tool 없음"을 v8 기준(대출·반납·희망도서는 화면 기능)으로 고치고, 대출·희망도서 요청에 화면 버튼을 안내하는 동작(평가)을 더함
- `platform/web-ui`: 화면이 부르는 경로에 `/loans`, `/loans/return`, `/book-requests`를 더하고, 대출·희망도서 입력칸의 계약(운영 방식에 따른 버튼, 회원번호 행선지, 비우기)을 정함
- `platform/database-schema`: 테이블 25개에서 26개(`book_requests`)로, 기관 간 참조 금지에 희망도서를 더함

## Impact

- 코드: 새 `app/library/models/book_request.py`, `schemas/book_request.py`, `services/book_requests.py`, `api/book_requests.py`, `services/members.py`(삭제), `app/library/librarian.py`(v8 프롬프트), `app/main.py`, `app/models.py`(`TENANT_TABLES`), 화면 `app/web/public/librarian/`(새 `actions.js`, `index.html`, `main.js`, `chat.js`, 스타일), `app/web/public/shared/api.js`
- DB: 마이그레이션 하나(`book_requests`)
- API: 새 `POST/GET /book-requests`, `PATCH /book-requests/{id}`. 대출 REST는 그대로
- 외부 호출: 없음
- LLM: 평가 실행만(새 시나리오 4개, 사서 평가 전체 회귀 약 110~150회). 호출 수를 알리고 승인을 받은 뒤 한다
- 문서: `docs/design.md`(tool 표와 그 아래 문단, 테이블 목록), `app/library/README.md`, `app/web/README.md`, `evals/librarian` 문서, archive 때 `docs/roadmap.md`(23 상태, 미룬 일)와 `CLAUDE.md`(현재 단계)
