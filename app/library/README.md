# library

기관 공통 층이다. 어느 유형의 기관이든 쓰는 기능을 맡는다. 모든 데이터는 로그인한 기관 범위 안에서만 다룬다.

## 맡는 일

- 기관, 직원, 인증
- 기관 도서(`library_books`): 이 도서관의 그 책. 파일·입력 값과 ISBN 없는 책이 여기 있다.
- 사본(`holdings`), 회원, 대출
- 엑셀·CSV 장서 가져오기
- 서지 채움 처리 현황
- 서명·저자 찾기와 자동완성(LLM 없음)
- 도서관 안내: 대표 연락처, 운영 시간, 휴관일, 이용 규칙, 자유 항목, 개관 여부와 반납 예정일 계산
- AI 사서: 후보 검색, 조회 tool, 프로필, 대화 세션, 개인정보 가리기, 추천 카드와 노출 기록

## 구성

| 위치 | 내용 |
| --- | --- |
| `api/` | 라우터. 로직을 넣지 않는다 |
| `services/` | 비즈니스 로직. REST API와 이후 에이전트 tool이 함께 쓴다 |
| `models/` | `library`(기관·직원·세션), `catalog`(기관 도서·사본·가져오기), `circulation`(회원·대출), `guide`(안내) |
| `schemas/` | Pydantic 스키마 |
| `importing/` | 파일 읽기, 머리글 인식, 정규화. DB와 HTTP를 모른다 |
| `deps.py` | 현재 직원·기관, 역할 |
| `hooks.py` | 기관 개별 기능의 접점 |
| `enrichment_targets.py` | 운영자 층 접점 구현, 처리 현황 |
| `recommendation/` | `search`(추천 가능 조건, 키워드 검색), `lookup`(서명·저자 찾기, 자동완성, 문장 속 서명, 고른 책 확인), `checks`(소장 검사), `cards`(요약과 카드), `events`(노출 기록) |
| `api/catalog.py` | `GET /catalog/search`, `GET /catalog/suggest` |
| `api/guide.py`, `services/guide.py` | `GET/PUT /library/guide`, `/library/closures`. 개관 여부(`day_status`), 반납 예정일(`due_date`, `compute_due_date`) |
| `recommendation/kdc.py` | 청구기호 → KDC 주류 이름 |
| `recommendation/embedding_text.py` | 임베딩 텍스트 `build_embedding_text`, `TEXT_VERSION`, 해시 |
| `recommendation/embeddings.py` | 임베딩 적재 `run_embedding`(전체·증분), 기관 범위 유사도 조회 `similar_books` |
| `models/embedding.py` | `BookEmbedding`(기관 도서·모델·텍스트 버전마다 벡터 하나) |
| `tools.py` | AI 사서의 조회 tool: `search_collection`, `find_book`(서명·저자 찾기), `get_book_detail`, `get_library_guide`(안내), 범위를 좁힌 검색 tool을 만드는 `search_tool` |
| `librarian.py` | 답 구조, 프롬프트, 운영 방식별 프로필(`build_librarian_profiles`), 정리 규칙, `LibrarianExtension` |
| `privacy.py` | 개인정보 가리기 |
| `services/chat.py` | 대화 순서: 확인, 고른 책·찾은 책, 가리기, 실행, 카드, 저장, 노출 기록, 끝난 세션 삭제 |

## 규칙

- `app/features`를 import하지 않는다. 기능을 이름으로 부르지 않고 훅으로 사건만 알린다.
- `app/central`은 import해도 된다. 공식 서지는 읽기만 하고, 기관의 값을 `books`에 쓰지 않는다.
- 기관은 요청 값이 아니라 인증 토큰으로 정한다. 다른 기관의 데이터는 404다 (`app/core/tenancy.py`의 `get_owned`).
- 표시 값은 `LibraryBook.shown`으로 읽는다. 공식 값이 먼저이고, 비어 있으면 기관 값이다.
- 공식 서지에 연결된 기관 도서는 ISBN만 고칠 수 있다.
- 서명·저자 찾기 키(`title_jamo_starts`, `author_jamo_starts`)는 DB가 계산하는 생성 열이다. 코드에서 쓰지 않는다. 규칙은 `app/core/text.py`의 `jamo_starts`이고 SQL 함수 `ko_jamo_starts`와 같아야 한다.
- 대화의 책 표시(`[고른 책: …]`, `[찾은 책: …]`)는 `chat_messages.note`에 두고 LLM에게는 안내(`Instruction`)로 보낸다. 이용자 문장에 섞으면 어린이 요청 판단이 서명의 낱말을 읽는다.

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

## 도서 임베딩

- 벡터는 기관 도서 기준이다(`book_embeddings`). ISBN 없는 책도 대상이고, 다른 기관 데이터 테이블처럼 `library_id`와 복합 외래 키로 나눈다. 기관 도서를 지우면 벡터도 지워진다(다시 만들 수 있는 값).
- 대상은 추천 가능한 책이다(`search.py`의 추천 가능 조건). 제적·분실·파손 사본만 남은 책은 인코딩하지 않는다.
- 임베딩 텍스트는 `embedding_text.py` 한 곳에서 만든다. 표시 값의 서명(부제), 저자, 분류(외부 분류 원문, KDC 주류 이름), 소개 순이고 빈 값은 건너뛴다. 소개가 마지막인 것은 입력 한도에서 잘릴 때 앞의 값이 남게 하기 위해서다. **구성을 바꾸면 `TEXT_VERSION`을 올린다.** 이 모듈은 DB, 인코더, 설정을 import하지 않는다.
- 텍스트 원문은 저장하지 않는다. 벡터, 모델 이름, 텍스트 버전, 텍스트의 SHA-256만 둔다.
- 증분 적재는 현재 모델·텍스트 버전의 벡터가 없거나 해시가 다른 책만 인코딩한다. 공식 서지 채움으로 소개가 생기면 해시가 달라져 다음 증분이 잡는다. 해시는 자르기 전 전체 텍스트의 값이라, `EMBEDDING_MAX_TOKENS`를 바꾼 뒤에는 `--full`로 다시 적재한다.
- 인코딩 호출 동안 트랜잭션을 잡지 않고 배치마다 커밋한다. 중간에 멈추면 끝난 배치는 남고 증분으로 이어 한다.
- 적재는 운영자가 `scripts/embed_books.py`로 돌린다. 서버 실행 중 자동 적재는 없다. 파생 값만 쓰고 기관이 정한 값은 바꾸지 않으며 훅을 부르지 않는다.
- `similar_books`는 그 기관의 추천 가능한 책 중에서, 조회에 쓴 인코더의 모델 이름과 현재 텍스트 버전의 벡터만 비교한다. 옛 버전이나 제적된 책의 벡터가 남아 있어도 결과에 섞이지 않는다. REST와 tool에는 아직 잇지 않았다(`add-related-books`).
- 벡터 인덱스는 없다. 5,000권 순차 탐색이 약 50ms다.
- CPU에서 한 권에 약 2.6초가 걸린다(표본 79권 206초). 전체 적재는 드물게, 평소에는 증분으로 돌린다.

## 도서관 안내

- 계산에 쓰는 값(운영 시간, 휴관일, 반납일 규칙)은 칸으로 나누고, 말로만 전하는 값(시설 위치, 이용 규칙, 알림)은 자유 항목(`library_guide_entries`)으로 둔다. 정기 휴관은 저장하지 않는다. 운영 시간 구간이 없는 요일이 정기 휴관이다.
- `library_guides` 행이 없으면 안내를 등록하지 않은 기관이다. 조회는 200이고 `registered`가 false다.
- **대표 연락처는 기관 대표 번호만 둔다.** 개인 번호를 넣지 않도록 API 설명에 적었다. 코드로 막지는 않는다(대표 번호가 휴대폰인 기관이 있다).
- 반납 예정일은 `services/guide.py`의 한 함수가 정한다. REST, `get_library_guide` tool, 자체 대출(`create_loan`)이 같은 값을 쓴다. 이미 만든 대출의 `due_on`은 나중에 휴관일을 등록해도 바꾸지 않는다.
- 공휴일은 `app/core/holidays.py`(`holidays` 패키지, 오프라인)다. 임시공휴일은 기관이 임시 휴관으로 등록한다.
- 날짜·요일·시각은 코드가 계산해 tool 결과에 넣는다. LLM은 날짜를 세지 않는다.
