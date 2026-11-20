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
- 운영 에이전트: 장서·대출 분석(정해진 분석 tool), 프로필, 관리자 대화
- 승인 흐름: 확정 작업의 공통 상태·전이, 큐레이션(초안 → 승인 → 게시), 연체 안내(틀 승인 → 확정, 목록은 계산)

## 구성

| 위치 | 내용 |
| --- | --- |
| `api/` | 라우터. 로직을 넣지 않는다 |
| `services/` | 비즈니스 로직. REST API와 이후 에이전트 tool이 함께 쓴다 |
| `models/` | `library`(기관·직원·세션), `catalog`(기관 도서·사본·가져오기), `circulation`(회원·대출), `guide`(안내), `curation`(큐레이션), `overdue_notice`(연체 안내문 틀) |
| `schemas/` | Pydantic 스키마 |
| `importing/` | 파일 읽기, 머리글 인식, 정규화. DB와 HTTP를 모른다 |
| `deps.py` | 현재 직원·기관, 역할 |
| `hooks.py` | 기관 개별 기능의 접점(사건, 관련 책 범위 제공자) |
| `enrichment_targets.py` | 운영자 층 접점 구현, 처리 현황 |
| `recommendation/` | `search`(추천 가능 조건, 키워드 검색), `lookup`(서명·저자 찾기, 자동완성, 문장 속 서명, 고른 책 확인), `checks`(소장 검사), `cards`(요약과 카드), `events`(노출 기록) |
| `api/catalog.py` | `GET /catalog/search`, `GET /catalog/suggest`, `GET /catalog/books/{id}/similar`(비슷한 책) |
| `api/guide.py`, `services/guide.py` | `GET/PUT /library/guide`, `/library/closures`. 개관 여부(`day_status`), 반납 예정일(`due_date`, `compute_due_date`) |
| `recommendation/authors.py` | 같은 지은이의 책 `same_author_books`, 지은이 키 SQL 식 `writer_keys_sql` |
| `services/author_keys.py` | 저자 키 다시 맞추기 `rebuild_author_keys`, 맞춰지지 않은 분류기호 세기 |
| `recommendation/embedding_text.py` | 기관 도서 벡터의 텍스트 `library_embedding_text`(기관 값만, 조립 규칙은 `app/core/embedding_text.py`) |
| `recommendation/embeddings.py` | 기관 도서 벡터 적재 `run_library_embedding`, 기관을 지정한 공식 서지 벡터 적재 조건 `held_official_ids`, 두 층 유사도 조회 `similar_books`(범위 조건, 종류별 가중 평균), 저장된 벡터로 이웃 조회 `neighbors_of`(인코딩 없음), 저장된 벡터 읽기 `book_vectors` |
| `recommendation/ranking.py` | 순수 함수: 역순위 합 `fuse_rrf`, 시리즈 묶기 `cap_series`, 결과 다양화 `mmr`. DB를 모른다 |
| `recommendation/topic.py` | 주제로 찾기 `find_by_topic`(키워드·벡터 순위를 합침), 깊은 키워드 순위 `keyword_ranking`, 설정 `TopicSettings` |
| `recommendation/related.py` | 비슷한 책 `find_similar`(같은 시리즈·같은 저자·KDC·벡터 이웃·함께 대출, 판본 제외 `editions_of`, 근거), 최근 기록 `find_from_history`(기록 신호), 우리 도서관 인기 `popular_ranking`, 정보나루 인기 `national_popular_ranking`, ISBN 순위 → 소장 책 `held_ranking`, 대출 신호 공급 `LoanSignals`, 벡터 근거만 있는 책의 최소 유사도, 설정 `SimilarSettings`·`HistorySettings` |
| `recommendation/basis.py` | 관련 책의 근거 코드 `basis_codes`와 문구 `basis_texts`(순수 함수) |
| `services/related.py` | 제품 경로: 비슷한 책 `similar_for_book`, 대화 세션의 책으로 최근 기록 `related_for_session`. REST와 tool이 이 함수만 부른다 |
| `services/topic.py` | 제품 경로: 주제로 찾기 `search_by_topic`(기본 설정, 10권, 키워드 순위로 내려가기, 키워드 근거 없음), 실행 값 이름 `QUERY_ENCODER`. 소장 도서 검색 tool이 이 함수만 부른다 |
| `models/embedding.py` | `BookEmbedding`(공식 서지 없는 기관 도서·모델·텍스트 버전·종류마다 벡터 하나) |
| `tools.py` | AI 사서의 조회 tool: `search_collection`(주제로 찾기), `find_book`(서명·저자 찾기), `find_related_books`(관련 책), `get_book_detail`, `get_library_guide`(안내), 범위를 좁힌 tool을 만드는 `search_tool`·`related_tool` |
| `librarian.py` | 답 구조, 프롬프트, 운영 방식별 프로필(`build_librarian_profiles`), 정리 규칙, `LibrarianExtension` |
| `privacy.py` | 개인정보 가리기 |
| `services/chat.py` | 대화 순서: 확인, 고른 책·찾은 책, 가리기, 실행, 카드, 저장(책 id 칸), 노출 기록, 끝난 세션 삭제. 세션의 책 `session_books`. 세션 종류(`SessionKind`)별 만료·일일 상한, 운영 에이전트도 쓰는 세션 열기 `open_session`·`release` |
| `analytics/` | 분석 빌더: 분야 결정 `fields`(KDC 주류 + 분류 없음), 기간 `periods`(프리셋·월 숫자), 분석 축 `axes`(`AnalysisAxis`), 책 범위와 묶기 `scope`(`book_facts`, `BookFilter`) |
| `services/analytics.py` | 분석 service 넷: 장서 현황 `collection_status`, 상태별 사본 `holdings_by_status`, 대출 통계 `loan_stats`, 안 빌린 책 `unborrowed_books`. REST는 아직 없고 tool이 부른다 |
| `schemas/analytics.py` | 분석 결과 스키마. 필드는 허용 목록 테스트(`tests/library/test_admin_agent.py`)가 고정한다 |
| `analytics_tools.py` | 운영 에이전트의 분석 tool 넷. 등록된 축으로 입력 모델을 조립 때 만든다 |
| `admin_agent.py` | 운영 에이전트: 답 구조(`message`, `unsupported`), 프롬프트, 운영 방식별 프로필(`build_admin_profiles`), `AdminExtension` |
| `services/admin_chat.py`, `api/admin_agent.py` | 관리자 대화 `POST /admin-agent/messages`, `DELETE /admin-agent/sessions/{id}`(키오스크 403) |
| `approval.py` | 공통 승인 틀: 상태 `ApprovalStatus`, 종류별 전이 표 `TransitionTable`(`PUBLISHING`·`CONFIRMING`), 조건부 갱신 `transition`, 실행 상태 `mark_executed`, 승인 칸 `ApprovalMixin` |
| `overdue_tools.py` | 운영 에이전트의 연체 tool: `list_overdue_loans`(회원 값 없는 결과 `OverdueLoanList`), `draft_overdue_notice`(틀을 승인 대기로, 입력 기록 없음). 자체 대출 기관 프로필에만 |
| `services/overdue_notices.py`, `api/overdue_notices.py`, `overdue_template.py` | 연체 안내: 틀 관리 `/overdue-notice-templates`, 오늘의 목록 `GET /overdue-notices/today`(모두 관리자), 자리표시 검사·채우기(순수 함수) |
| `services/curations.py`, `api/curations.py` | 큐레이션: 관리 `/curations`(관리자), 게시본 읽기 `GET /librarian/curations`(키오스크·관리자). REST와 두 에이전트 tool이 같은 service를 쓴다 |

## 규칙

- `app/features`를 import하지 않는다. 기능을 이름으로 부르지 않고 훅으로 사건만 알린다.
- `app/central`은 import해도 된다. 공식 서지는 읽기만 하고, 기관의 값을 `books`에 쓰지 않는다.
- 기관은 요청 값이 아니라 인증 토큰으로 정한다. 다른 기관의 데이터는 404다 (`app/core/tenancy.py`의 `get_owned`).
- 표시 값은 `LibraryBook.shown`으로 읽는다. 공식 값이 먼저이고, 비어 있으면 기관 값이다.
- 공식 서지에 연결된 기관 도서는 ISBN만 고칠 수 있다.
- 저자 키(`library_books.author_keys`)는 저자를 쓸 때 모델(`LibraryBook._set_author_keys`)이 함께 정한다. 등록, 수정, 가져오기가 모두 ORM이라 따로 부르지 않는다. Core `insert`로 기관 도서를 넣는 곳(시드)은 `app/core/contributors.py`의 `author_keys`로 값을 넣어야 하고, 빠뜨리면 DB가 거부한다(기본값 없음). Core `update`로 저자를 바꾸지 않는다(`tests/catalog/test_library_book_author_keys.py`가 소스를 검사한다).
- 분류기호(`kdc`)는 쓸 때 KDC 숫자 문자열로 맞춘다(`813.7`). 읽을 수 없는 값은 공백만 정리해 둔다. 이미 저장된 행은 바꾸지 않는다.
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
- 키워드 검색은 표시 값의 서명(4), 부제·시리즈·저자(3), 소개(1)를 공백을 지운 부분 문자열로 찾고 가중치를 더한다. 최대 10권이다. AI 사서의 소장 도서 검색 tool은 이 순위와 벡터 순위를 합친 주제로 찾기(`services/topic.py`)를 쓰고, 결과는 `{books, note}`다.
- 기관 개별 기능은 `LibrarianExtension`(tool, 최종 검사, 프롬프트 문구)으로 끼운다. 이 패키지는 기능을 이름으로 부르지 않는다. 조립은 `app/main.py`가 하고, 평가도 같은 `build_librarian_profiles`를 부른다.
- 쓰기 tool은 없다. 대출·반납·희망도서는 `add-librarian-actions`에서 한다.
- `chat_messages`에는 가린 이용자 문장과 최종 답만 둔다. 최종 답에는 코드가 `[추천한 책: #id 서명]`을 덧붙인다. 끝난 세션은 `lifespan`의 작업이 1분마다 지운다.
- tool 입력은 실행 기록에 남기지 않는다. 키워드에 이용자 문장 일부가 들어 있을 수 있어서다.
- **관련 책 tool** `find_related_books(library_book_id | None)`: id가 있으면 비슷한 책, 비우면 대화 세션의 책으로 최근 기록(세션에 책이 없으면 우리 도서관 인기)이다. 비슷한 책 API와 같은 service(`services/related.py`)를 쓴다. 결과는 검색 결과와 같은 값에 `basis_text`를 더하고, 비면 `note`가 다음 할 일을 알린다. 입력의 책 id는 실행 기록에 남긴다(개인정보가 아니다).
- **대화 세션의 책**: `chat_messages.library_book_ids`에 이용자 행은 고른 책·찾은 책, 답 행은 카드가 된 추천 책의 id를 코드가 쓴다. 실행 전에 그 세션의 책을 최신 순, 서로 다른 책으로 모아 실행 값(`SESSION_BOOKS`)으로 넘긴다. service가 그 기관에서 추천할 수 있는 책만 남겨 3권까지 쓴다. LLM은 이 목록을 정하지 않는다. 세션이 끝나면 메시지와 함께 지워진다.

## 같은 저자

- 책의 지은이 키는 두 층에서 읽는다. 공식 서지에 연결된 책은 기여자(`book_contributors`) 중 `author`·`original`의 이름 맞춤 키, 연결되지 않은 책은 저자 키다. 연결된 책은 기관이 적은 저자를 보지 않는다.
- 저자 키는 연결 여부와 상관없이 채운다. 연결이 풀리거나 생겨도 다시 계산하지 않기 위해서다. 읽는 쪽이 연결 여부로 고른다.
- 그린이는 기본에 넣지 않는다. 추천 실험에서 어린이 도서일 때 넣는 변형을 비교한다.
- `same_author_books`는 그 기관의 추천 가능한 책만 돌려준다. 비슷한 책의 같은 저자 신호로 제품에 나간다(`services/related.py`).
- 서명·저자 찾기는 저자 키가 아니라 원문의 자모 키로 한다.

## 도서 임베딩

- **벡터는 두 층이다.** 책 하나는 한 층에만 속하고, 연결 여부(`library_books.book_id`)가 층을 정한다.
  - 공식 서지에 연결된 책: 공식 서지 벡터(`official_book_embeddings`, 운영자 층, 기관 공통 테이블). 공식 서지마다 하나라 여러 기관이 함께 쓴다. 텍스트는 공식 값만이다(`app/central/embedding_text.py`).
  - 연결되지 않은 책(ISBN 없음, 못 찾음): 기관 도서 벡터(`book_embeddings`). 다른 기관 데이터 테이블처럼 `library_id`와 복합 외래 키로 나눈다. 기관 도서를 지우면 벡터도 지워진다(다시 만들 수 있는 값).
- 기관 도서 벡터의 대상은 연결되지 않은 추천 가능한 책이다(`search.py`의 추천 가능 조건). 제적·분실·파손 사본만 남은 책은 인코딩하지 않는다. 나중에 연결된 책의 기관 도서 벡터는 지우지 않고 조회가 쓰지 않는다.
- 임베딩 텍스트의 조립 규칙은 `app/core/embedding_text.py` 한 곳이다. 서명(: 부제), 분류, 소개 순이고 빈 값은 건너뛴다. **저자는 넣지 않는다**(텍스트 버전 2). 같은 저자는 기여자·저자 키, 저자 이름 질의는 서명·저자 찾기가 맡는다. 소개가 마지막인 것은 입력 한도에서 잘릴 때 앞의 값이 남게 하기 위해서다. **규칙을 바꾸면 `TEXT_VERSION`을 올린다.** 기관 도서 텍스트(`library_embedding_text`)는 기관 값만 쓰고 `shown`을 쓰지 않는다.
- 벡터마다 종류(`kind`, `TextKind`)가 있다. 지금은 책 한 권을 벡터 하나로 만드는 `full`뿐이다. 필드별 벡터는 종류를 더해 같은 테이블에 둔다(DB에는 값 목록 제약이 없다).
- 텍스트 원문은 저장하지 않는다. 벡터, 모델 이름, 텍스트 버전, 종류, 텍스트의 SHA-256만 둔다.
- 증분 적재는 현재 모델·텍스트 버전·종류의 벡터가 없거나 해시가 다른 대상만 인코딩한다. 공식 서지 채움으로 공식 서지가 생기면 다음 증분이 잡는다. 기관 값을 고쳐도 공식 서지 벡터는 바뀌지 않는다. 해시는 자르기 전 전체 텍스트의 값이라, `EMBEDDING_MAX_TOKENS`를 바꾼 뒤에는 `--full`로 다시 적재한다.
- 배치 흐름(`app/central/embedding.py`의 `run_layer`)은 두 층이 같이 쓴다. 인코딩 호출 동안 트랜잭션을 잡지 않고 배치마다 커밋한다. 중간에 멈추면 끝난 배치는 남고 증분으로 이어 한다.
- 적재는 운영자가 `scripts/embed_books.py`로 돌린다(공식 서지, 기관 도서 순서. `--layer`로 한 층만). 서버 실행 중 자동 적재는 없다. 파생 값만 쓰고 기관이 정한 값은 바꾸지 않으며 훅을 부르지 않는다.
- `similar_books`는 그 기관의 추천 가능한 책을 기준으로 연결된 책은 공식 서지 벡터, 연결되지 않은 책은 기관 도서 벡터를 붙여 한 순위로 합친다(`UNION ALL`). 조회에 쓴 인코더의 모델 이름, 현재 텍스트 버전, 종류의 벡터만 비교한다. 공식 서지 벡터가 결과에 오르는 길은 이 기관의 추천 가능한 기관 도서가 그 공식 서지를 가리키는 것뿐이다. 주제로 찾기의 벡터 신호로 쓴다(AI 사서의 소장 도서 검색, `services/topic.py`).
- `similar_books`의 `within`은 순위를 매기기 전에 거는 기관 도서 id 조건이다(어린이 도서처럼 뜻은 부르는 쪽만 안다). 뽑은 뒤 거르면 조건 밖의 책에 밀려 몇 권 안 남는다. `weights`는 종류별 가중치이고 점수는 그 책에 벡터가 있는 종류들의 유사도 가중 평균이다(필드별 벡터 `title`·`category`·`description`을 합칠 때 쓴다). 종류 하나면 이전과 같다.

## 주제로 찾기

- `find_by_topic`은 "공룡 책", "가벼운 에세이" 같은 요청의 후보 순위를 만든다. LLM을 쓰지 않는다. 키워드 순위(`search.py`의 `ranked_query`와 같은 점수, 10권 상한 없음)와 벡터 순위를 역순위 합(RRF)으로 합치고, 같은 시리즈를 상한까지만 남기고(빠진 권수를 적는다), MMR로 순서를 고친다.
- 범위(그 기관, 추천 가능, `within`)는 신호마다 순위를 매기기 전에 건다. 결과마다 합친 점수와 신호별 순위(근거)가 있다. 난수가 없어 같은 입력이면 같은 결과다.
- 설정(`TopicSettings`: 신호 가중치, 벡터 질의 입력, 종류 가중치, 깊이, k, 시리즈 상한, λ)은 추천 실험(`evals/recommendation`)이 정한다. 기본은 `hybrid-k60`에 벡터 질의를 낱말로 둔 것이다(`add-topic-search-tool` 결정 2, 문장과 차이 없음, 여러 턴·다시 찾기 때문). 시리즈 묶기·MMR은 끈다.
- **제품 경로**(`services/topic.py`의 `search_by_topic`): AI 사서의 소장 도서 검색(`search_collection`, 어린이 `search_children_books`)이 이 함수만 부른다. 낱말이 있으면 기본 설정으로 앞 10권, 없으면 둘러보기(`search.search_collection`)다. 여기서 설정을 다시 고르지 않는다(결과 수만 10).
  - 질의 인코더는 대화 코드가 실행 값(`QUERY_ENCODER`)으로 넘긴다(`app/central`의 `GuardedEmbedder`, 라우터의 `get_query_encoder`). 인코더가 없거나 실패하면(꺼짐, 시간 제한, 다른 모델, 쉬는 중) 키워드 순위만으로 내려간다. 그 결과는 같은 낱말의 키워드 검색과 같다. 로그에는 실패 종류만 남고 이용자 답과 tool 결과에는 드러내지 않는다.
  - 키워드 순위가 비고 벡터 순위로만 나오면 결과의 `note`가 소개로 맞는지 보라고 알린다(키워드 근거 없음). 결과를 비우는 유사도 문턱은 없다. 결과가 비면 `note`가 다시 찾기나 희망도서를 알린다.
  - 내려가기를 `find_by_topic` 안에 두지 않는다. 실험이 같은 함수를 부르므로 실험 중의 인코딩 실패가 조용히 키워드만으로 바뀌면 안 된다.
  - 이용자 문장은 받지 않는다. 벡터 질의는 LLM이 넘긴 낱말을 이은 것이다.
- 벡터 인덱스는 없다. 5,000권(공식 4,500 + 기관 500) 두 층 조회가 약 45ms다(처음 한 번 약 68ms).
- CPU에서 한 권에 약 1.45초가 걸린다(ONNX, 배치 4). 전체 적재는 드물게, 평소에는 증분으로 돌린다.

## 비슷한 책과 최근 기록

- `find_similar`는 기준 책 하나에서 후보 순위를 만든다. 신호는 같은 시리즈(공식 서지 시리즈 키), 같은 저자(`same_author_books`), 같은 KDC 세목(표시 KDC가 소수점 첫째 자리까지 같음), 벡터 이웃(기준 책의 **저장된** 벡터, `neighbors_of`)이다. 질의를 인코딩하지 않아 임베딩 서버 없이 돌고, 인코더 대신 모델 이름을 받는다.
- 합치기는 RRF(`fuse_rrf`) 또는 규칙 신호 먼저(`fuse_priority`: 시리즈 → 저자 → KDC → 벡터)다. 결과마다 신호별 순위(근거)가 있다. 시리즈 묶기와 MMR은 주제로 찾기의 함수를 쓴다.
- 기준 책 자신과 같은 책의 다른 판본은 내지 않는다. 판본 규칙은 `editions_of`다: 판본·묶음 표기를 지운 표시 서명에서 공백·문장부호를 지운 값이 같고 지은이가 겹친다. 괄호 안 권 표기(`(봄·여름)`)도 판본으로 본다(한계).
- `category_scope`는 벡터 이웃을 같은 외부 분류 원문 안으로 좁힌다. 외부 분류는 상위 분야라 KDC 세목 대신으로 쓰지 않는다.
- 같은 KDC의 단위(`kdc_level`)는 세목(기본, 소수점 첫째 자리까지), 세 자리, 계층(세목 먼저, 그다음 세 자리)이고, 단위 안 순서(`kdc_order`)는 서명 순(기본) 또는 기준 책 벡터 순이다. `kdc_scope`는 진단용으로 벡터 이웃을 같은 KDC 단위 안으로 좁힌다.
- 함께 대출(`co_loan`)은 정보나루 함께 대출 ISBN 순위에서 그 기관이 가진 추천 가능한 책만 남긴 순위다(`held_ranking`: 공식 서지 ISBN 먼저, 없으면 기관 도서 ISBN). 순위는 `LoanSignals`가 준다(실험은 파일, 제품 테이블은 정보나루 약관 확인 뒤 `add-loan-signal-store`에서). `mania`·`reader`는 진단 신호다. ISBN 없는 기준 책이나 공급이 없으면 비어 있다.
- `find_from_history`는 최근 기록(책 목록)에서 고른다. `mean`은 기록 책 벡터의 평균, `per-book`은 책마다 만든 비슷한 책 순위의 RRF다(근거 이름 `book:<id>`). 기록 책 중 그 기관의 책만 근거로 쓴다. `mean`은 기록 신호(`signals`: 같은 KDC, 겹치는 저자, 기록 책마다의 함께 대출 RRF)를 벡터 평균 순위와 RRF로 합칠 수 있다(기본은 벡터만). 결과가 모자라면 `popular_ranking`(최근 180일 대출 행 수, 그 기관만)으로 먼저, 그다음 정보나루 인기(`national_popular_ranking`, `popular_group`: 기본은 조건 없음 `all`, 어린이 조건이면 부르는 쪽이 어린이 연령 묶음 이름을 넘긴다)로 채운다. 기록이 비어 있으면 인기로만 채우고, 둘 다 비면 빈 결과다(신착·무작위로 채우지 않는다). 인기는 순위 신호로 섞지 않는다.
- 범위(그 기관, 추천 가능, `within`)는 신호마다 순위 전에 건다. 다른 기관의 기준 책은 NotFoundError다. 설정은 추천 실험이 정한다.
- `min_vector_similarity`는 근거가 벡터 이웃 하나뿐인 책 중 기준 책 벡터와의 코사인이 문턱보다 낮은 책을 뺀다. 규칙 근거가 있는 책은 빼지 않고, 뺀 자리를 채우지 않는다. 기본은 `None`(빼지 않음)이다.

## 관련 책 (제품 경로)

- `services/related.py`가 제품 경로다. 비슷한 책 API(`GET /catalog/books/{id}/similar`)와 AI 사서 tool이 이 함수만 부른다.
  - 추천 실험의 기본 설정(`SimilarSettings()`, `HistorySettings()`)을 그대로 쓴다. 여기서 설정을 다시 고르지 않는다.
  - 저장된 벡터만 쓴다. 모델 이름은 설정의 `embedding_model`이고 임베딩 서버를 부르지 않는다. 적재 전인 책은 벡터 이웃이 비어 규칙 신호만 남는다. 새 책은 `scripts/embed_books.py --incremental`로 적재한다.
  - 대출 신호 공급이 없다. 함께 대출은 비고, 인기 채우기는 우리 도서관 인기에서 끝난다. 정보나루 인기는 테이블이 생긴 뒤(`add-loan-signal-store`)다. 외부 대출 기관처럼 대출 행이 없으면 "아무거나"는 빈 결과다.
  - 기준 책은 그 기관의 찾을 수 있는 책이어야 한다(`get_findable`). 아니면 NotFoundError(404)다.
- 결과마다 근거 코드(오른 신호 모두)와 문구(두 개까지)가 있다(`recommendation/basis.py`). 순서는 시리즈 → 지은이 → 분류 → 내용 → 인기다. 분류 문구는 그 책의 표시 KDC 세목(`같은 분류 813.7`)이다. 지은이 이름은 넣지 않는다(카드에 있다).
- **범위 제공자**: 기관 개별 기능은 `hooks.register_related_scope`로 기준 책(들)에 따라 결과를 좁힐 조건을 등록한다. 공통 코드는 조건의 뜻을 모르고, 부르는 쪽 `within`과 등록된 조건을 모두 건다. 서버를 거치지 않는 진입점(평가)도 같은 등록을 해야 한다.
- 질의, 실행 기록, 노출 기록을 남기지 않는다.

## 도서관 안내

- 계산에 쓰는 값(운영 시간, 휴관일, 반납일 규칙)은 칸으로 나누고, 말로만 전하는 값(시설 위치, 이용 규칙, 알림)은 자유 항목(`library_guide_entries`)으로 둔다. 정기 휴관은 저장하지 않는다. 운영 시간 구간이 없는 요일이 정기 휴관이다.
- `library_guides` 행이 없으면 안내를 등록하지 않은 기관이다. 조회는 200이고 `registered`가 false다.
- **대표 연락처는 기관 대표 번호만 둔다.** 개인 번호를 넣지 않도록 API 설명에 적었다. 코드로 막지는 않는다(대표 번호가 휴대폰인 기관이 있다).
- 반납 예정일은 `services/guide.py`의 한 함수가 정한다. REST, `get_library_guide` tool, 자체 대출(`create_loan`)이 같은 값을 쓴다. 이미 만든 대출의 `due_on`은 나중에 휴관일을 등록해도 바꾸지 않는다.
- 공휴일은 `app/core/holidays.py`(`holidays` 패키지, 오프라인)다. 임시공휴일은 기관이 임시 휴관으로 등록한다.
- 날짜·요일·시각은 코드가 계산해 tool 결과에 넣는다. LLM은 날짜를 세지 않는다.

## 운영 에이전트

- 정해진 분석 tool로 답한다. LLM은 분석 종류·기간·축(enum)만 고르고 숫자는 `services/analytics.py`가 센다. 자연어 SQL은 보류다(`add-admin-agent`).
- **분야**는 공식 서지 KDC → 기관 도서 KDC → 사본 청구기호(제적 아닌 사본 중 가장 작은 id) 앞 세 자리 → 분류 없음 순서다. 키워드·벡터 검색으로 세지 않는다. 분야 그룹에는 0인 분야와 분류 없음도 늘 넣어 합이 전체와 같다.
- **제적 사본**은 장서 수와 그룹에서 빼고 `withdrawn_copies`로 따로 센다. 대출 건수에는 넣는다(기록이 남는다). 권당 대출의 분모는 지금 사본 수다. 책 순위에서 사본이 모두 제적된 책은 `in_collection=false`다. 안 빌린 책은 기간 시작 전에 등록됐고 지금 사본이 있는 서명만이다.
- **기간**은 프리셋 7개 또는 월 숫자(미래면 작년)이고 `clock.today()`로 계산한다. 결과에 계산한 기간(`period.label`)을 넣는다. 대출은 빌린 날이 기간 안이면 센다.
- **한도**: 순위 10/최대 20, 목록 20/최대 50. 목록과 순위는 `total`, `shown`, `truncated`를 낸다. 같은 수는 건수 → 서명 가나다순 → id다.
- **분석 축**: 기관 개별 기능은 `AdminExtension(axes=...)`으로 축을 넘긴다. 이 패키지는 축 이름을 부르지 않는다. 배정이 없는 책은 기본값이다. 축이 없으면 tool 입력에도 없다.
- **개인정보**: 분석은 `members`와 `holdings.donor`를 읽지 않는다. 연체는 건수만 낸다. 분석 tool 입력은 enum과 정수라 모두 실행 기록에 남긴다. 답의 `unsupported`는 최종 답의 기록 필드로 실행 행에 남고, 질문 문장은 새로 저장하지 않는다.
- **운영 방식**: 외부 대출 기관 프로필에는 대출 통계·안 빌린 책 tool이 없다(대출 행이 없다). 사본의 대출 중 상태는 장서 현황의 상태 묶기로 답한다.
- 최종 검사는 없다. 답의 숫자가 tool 결과에 있는지는 평가(`evals/admin_agent`)로 잰다.
- 세션은 AI 사서와 같은 테이블이고 종류(`kind`)로 나눈다. 다른 종류의 세션 id는 404다. 만료는 30분, 일일 상한은 200으로 AI 사서와 따로다.

## 승인 흐름

- **상태**는 초안 테이블마다의 `status` 칸이다(`approval_status`, VARCHAR + CHECK). 공통 승인 표는 없다. 값은 `draft`, `pending_approval`, `approved`, `published`, `confirmed`, `archived`다.
- **전이**는 `approval.py`의 `transition` 하나로 한다. `UPDATE … WHERE id, library_id, status = 이전 상태`라서 겹친 요청은 하나만 반영되고, 바뀐 행이 없으면 없음(404)과 상태 충돌(409)을 나눠 올린다. 커밋은 service가 한다.
  - 제출 `draft → pending_approval`, 승인 `pending_approval → approved`, 반려 `pending_approval → draft`(사유), 내리기 `published → archived`(게시하는 종류만).
  - 내용 수정·삭제는 `draft`에서만이다(`require_status`).
- **승인과 실행은 한 트랜잭션**이다. 승인한 요청이 그 자리에서 실행(게시·확정)하고 `mark_executed`로 실행 상태와 시각(`executed_at`)을 둔다. 에이전트 실행을 다시 이어 가지 않는다. 상태가 DB에만 있으므로 서버가 다시 시작돼도 승인이 이어진다.
- 승인·반려·내리기는 관리자만 한다. 승인자(`approved_by`)와 시각을 남기고, 만든 사람이 승인해도 된다.
- **새 종류 더하기**(구매 요청서. 연체 안내가 `CONFIRMING`을 처음 쓴 예다): 테이블에 `ApprovalMixin`을 섞고 `library_id`로 나눈다. 확정하는 종류는 `CONFIRMING` 표를 쓴다. service에서 `transition`과 `mark_executed`를 부르고, 승인 뒤 할 일(확정)을 같은 트랜잭션 안에서 결정적인 코드로 한다. `app/models.py`의 `TENANT_TABLES`에 테이블을 넣는다.

## 연체 안내

- **승인은 틀에만** 받는다. 틀(`overdue_notice_templates`)은 문장 하나(300자)이고 `draft → pending_approval → confirmed`(`CONFIRMING`, 내리기 없음)다. 승인하면 같은 트랜잭션에서 확정한다. 그 기관이 쓰는 틀은 확정된 틀 가운데 `executed_at`이 가장 늦은 하나다(같으면 id가 큰 것). 이전 확정 틀의 상태는 바꾸지 않는다.
- **연체 안내 목록**(`GET /overdue-notices/today`)은 승인 없이 요청할 때마다 계산한다. 지금의 연체 대출(`services/loans.py`와 같은 조건) × 쓰는 틀 × 회원 행으로 줄마다 문안을 채우고 저장하지 않는다. 확정된 틀이 없으면 409다. 회원번호 → 반납 예정일 → 대출 id 순이고 전부 돌려준다.
- **자리표시** 다섯 개(`overdue_template.py`): `{이름}` `{서명}` `{반납예정일}` `{연체일수}` `{도서관}`. `{서명}`과 `{반납예정일}`은 필수다. 모르는 자리표시는 거부한다. 채우기는 `str.replace`이고 `str.format`은 쓰지 않는다. 연체 일수는 기관 시간대의 오늘 − 반납 예정일(달력 일수)이다.
- **개인정보 경계**: 회원 값(이름·회원번호·전화번호)은 목록 REST의 줄과 채운 문안에만 있다. LLM은 틀만 쓴다. 틀을 저장할 때 `mask_personal`을 돌려 결과가 달라지면(전화번호·이메일·주민번호·그 기관 회원번호) 가리지 않고 거부하며(422) 메시지에 찾은 값을 넣지 않는다. 이름은 가리지 않는다(`privacy.py`의 방침).
- **회원 전화번호**(`members.phone`)는 선택이고 숫자만 저장한다. 관리자 회원 API와 연체 안내 목록에서만 돌려주고 검색(`q`)에 쓰지 않는다. 다른 곳에 복사하거나 목록을 저장하지 않으므로 회원을 지우면 함께 사라진다.
- **외부 대출 기관**은 이 시스템에 대출 기록이 없어 틀 API와 목록이 모두 409다(`services/overdue_notices.py`의 `_library`).
- **운영 에이전트**: 자체 대출 기관 프로필에만 `list_overdue_loans`·`draft_overdue_notice`가 있고 연체 안내 규칙도 그 프로필의 문구(`LOAN_NOTES[INTERNAL]`)에만 있다. 연체 목록 결과는 서명·등록번호·반납 예정일·연체 일수와 수(20건까지)뿐이고, 틀 초안 결과에는 채운 문안이 없다. 카나리아 테스트(`tests/library/test_overdue_tools.py`)가 LLM 요청과 기록에 회원 값이 없음을 확인한다.

## 큐레이션

- 제목 40자, 소개 200자(없어도 됨), 책 3~10권(책마다 이유 60자). 같은 책은 처음 것만 남기고 남은 권수로 센다(`CurationWrite`).
- 책은 **쓸 때** 그 기관의 추천 가능한 책이어야 한다(`get_candidates`). 없거나 다른 기관이면 404, 대출 가능·대출 중 사본이 없으면 409이고 걸린 id를 메시지에 담는다. 승인 때는 다시 보지 않는다.
- **읽을 때** 지금 추천할 수 있는 책만 남긴다(`published_curations`, `recommendable_only`). 저장된 책은 바꾸지 않고, 남는 책이 없는 게시본은 뺀다. 최신 5개는 거른 뒤에 센다.
- 승인하면 바로 게시한다(`approved` → `published`). 내리면 `archived`라 이용자 쪽에서 바로 빠진다.
- 책 카드는 추천 카드와 같은 값(`summary_values`)에 저장한 이유를 더한다. 회원·기증자 값은 없다.
- 운영 에이전트의 `draft_curation`은 만들기와 제출을 한 트랜잭션으로 하고(`submit=True`), AI 사서의 `get_curations`는 게시본 읽기와 같은 함수를 쓴다.
