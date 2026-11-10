# library

기관 공통 층이다. 어느 유형의 기관이든 쓰는 기능을 맡는다. 모든 데이터는 로그인한 기관 범위 안에서만 다룬다.

## 맡는 일

- 기관, 직원, 인증
- 기관 도서(`library_books`): 이 도서관의 그 책. 파일·입력 값과 ISBN 없는 책이 여기 있다.
- 사본(`holdings`), 회원, 대출
- 엑셀·CSV 장서 가져오기
- 서지 채움 처리 현황
- AI 사서: 후보 검색, 조회 tool, 프로필, 대화 세션, 개인정보 가리기, 추천 카드와 노출 기록

## 구성

| 위치 | 내용 |
| --- | --- |
| `api/` | 라우터. 로직을 넣지 않는다 |
| `services/` | 비즈니스 로직. REST API와 이후 에이전트 tool이 함께 쓴다 |
| `models/` | `library`(기관·직원·세션), `catalog`(기관 도서·사본·가져오기), `circulation`(회원·대출) |
| `schemas/` | Pydantic 스키마 |
| `importing/` | 파일 읽기, 머리글 인식, 정규화. DB와 HTTP를 모른다 |
| `deps.py` | 현재 직원·기관, 역할 |
| `hooks.py` | 기관 개별 기능의 접점 |
| `enrichment_targets.py` | 운영자 층 접점 구현, 처리 현황 |
| `recommendation/` | `search`(추천 가능 조건, 키워드 검색), `checks`(소장 검사), `cards`(카드), `events`(노출 기록) |
| `tools.py` | AI 사서의 조회 tool: `search_collection`, `get_book_detail`, 범위를 좁힌 검색 tool을 만드는 `search_tool` |
| `librarian.py` | 답 구조, 프롬프트, 운영 방식별 프로필(`build_librarian_profiles`), 정리 규칙, `LibrarianExtension` |
| `privacy.py` | 개인정보 가리기 |
| `services/chat.py` | 대화 순서: 확인, 가리기, 실행, 카드, 저장, 노출 기록, 끝난 세션 삭제 |

## 규칙

- `app/features`를 import하지 않는다. 기능을 이름으로 부르지 않고 훅으로 사건만 알린다.
- `app/central`은 import해도 된다. 공식 서지는 읽기만 하고, 기관의 값을 `books`에 쓰지 않는다.
- 기관은 요청 값이 아니라 인증 토큰으로 정한다. 다른 기관의 데이터는 404다 (`app/core/tenancy.py`의 `get_owned`).
- 표시 값은 `LibraryBook.shown`으로 읽는다. 공식 값이 먼저이고, 비어 있으면 기관 값이다.
- 공식 서지에 연결된 기관 도서는 ISBN만 고칠 수 있다.

## 공식 서지 연결

| 함수 | 쓰는 곳 | 기관 개별 기능에 알림 |
| --- | --- | --- |
| `link_official` | 등록, ISBN 수정 | 알림 |
| `connect_official` | 가져오기, 운영자 실행 | 가져오기는 `_notify`가 알리고, 운영자 실행은 알리지 않음 |

운영자 실행이 훅을 부르지 않는 것은 의도한 동작이다. 운영자 실행이 기관의 값을 바꾸면 안 되기 때문이다.

## 훅

`hooks.py`의 사건은 두 가지다.

| 사건 | 언제 |
| --- | --- |
| `official_changed` | 기관의 요청으로 공식 서지 연결이 정해졌을 때. 기관 도서는 저장돼 있다 |
| `row_applied` | 가져오기 행을 적용했을 때. 행에 인식한 파일 값이 들어 있다 |

가져오기는 새 도서의 `official_changed`를 먼저, 행마다 `row_applied`를 그다음에 부른다. 파일 근거가 외부 근거 위에 놓이게 하는 순서다.

훅은 `app/main.py`에서 등록한다. 서버를 거치지 않고 이 패키지의 service를 직접 부르는 코드를 새로 만들면 훅 등록을 함께 챙겨야 한다.

## AI 사서

- 추천 가능한 책은 대출 가능이나 대출 중 사본이 있는 그 기관의 책이다(`recommendation/search.py`의 `recommendable_ids`). 검색과 소장 검사가 이 한 곳을 쓴다.
- 검색은 표시 값의 서명(4), 부제·시리즈·저자(3), 소개(1)를 공백을 지운 부분 문자열로 찾고 가중치를 더한다. 최대 10권이다.
- 기관 개별 기능은 `LibrarianExtension`(tool, 최종 검사, 프롬프트 문구)으로 끼운다. 이 패키지는 기능을 이름으로 부르지 않는다. 조립은 `app/main.py`가 하고, 평가도 같은 `build_librarian_profiles`를 부른다.
- 쓰기 tool은 없다. 대출·반납·희망도서는 `add-librarian-actions`에서 한다.
- `chat_messages`에는 가린 이용자 문장과 최종 답만 둔다. 최종 답에는 코드가 `[추천한 책: #id 서명]`을 덧붙인다. 끝난 세션은 `lifespan`의 작업이 1분마다 지운다.
- tool 입력은 실행 기록에 남기지 않는다. 키워드에 이용자 문장 일부가 들어 있을 수 있어서다.
