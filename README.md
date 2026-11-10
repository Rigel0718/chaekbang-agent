# chaekbang-agent

사서가 없는 작은도서관을 위한 AI 사서 웹 서비스의 백엔드. 도서관 PC에 켜 둔 화면에서 이용자는 AI 사서에게 추천을 받고 대출하며, 관리자는 운영 에이전트로 장서·대출 현황을 다룬다. 배경과 전체 설계는 [docs/design.md](docs/design.md), 코딩 규칙은 [CLAUDE.md](CLAUDE.md)를 참고한다.

현재 단계: 3주차 AI 사서 v1. 이용자는 `POST /librarian/messages`로 AI 사서에게 소장 도서 추천을 받는다. 대출·반납·희망도서 신청은 아직 대화로 처리하지 않는다.

## 도메인

| 구분 | 테이블 | API |
| --- | --- | --- |
| 기관과 인증 | libraries, staff_users, staff_sessions | `/auth`, `/library`, `/staff` |
| 장서 | books(공식 서지, 기관 공통), library_books(기관 도서), holdings(소장 사본), holding_imports(가져오기 기록) | `/library-books`, `/holdings`, `/holding-imports`, `/book-enrichment` |
| 어린이 구분 (기관 개별 기능) | library_book_audiences | `/children` |
| 대출 | members, loans | `/members`, `/loans` |
| AI 사서 | agent_runs, agent_steps(실행 기록), chat_sessions, chat_messages(진행 중 대화), recommendation_events(추천 노출) | `/librarian` |

- **기관 분리**: books·libraries를 뺀 모든 테이블은 `library_id`를 가진다. 기관은 로그인 토큰으로 정해지고, 다른 기관의 데이터는 404로 응답한다.
- **공식 서지**: `books`는 ISBN이 있는 책의 공식 서지다. 기관 API로는 쓸 수 없다.
- **기관 도서와 사본**: 기관 도서는 그 기관의 책이다. 내부 id로 식별하고 ISBN은 선택이다. ISBN이 같은 공식 서지가 있으면 연결되고(`book_id`), 조회할 때 공식 값을 먼저 보여 준다. 연결된 도서는 ISBN만 고칠 수 있다. 사본은 등록번호(`accession_number`), 청구기호(`call_number`), 입수 구분(매입·납품은 구입가와 ISBN 필수, 기증은 기증처 선택, 가져온 사본은 `unknown`도 가능)을 가진다.
- **운영 방식(`loan_mode`)**: `internal` 기관은 이 서비스에서 대출·반납하고, `imported` 기관은 기존 대출 프로그램에서 하므로 대출·반납 요청에 409로 안내한다.

## 로컬 실행

필요한 것: [uv](https://docs.astral.sh/uv/), Docker (Compose v2)

```bash
cp .env.example .env
```

```bash
uv sync
```

```bash
docker compose up -d db
```

```bash
uv run alembic upgrade head
```

```bash
uv run python scripts/seed.py
```

```bash
uv run uvicorn app.main:app --reload
```

서버가 뜨면 Swagger 문서는 http://localhost:8000/docs 에 있다.

- DB 컨테이너는 처음 만들어질 때 테스트용 `chaekbang_test` DB도 함께 만든다.
- 시드는 여러 번 실행해도 중복되지 않는다 (이미 있는 기관명·아이디·ISBN·등록번호·회원번호는 건너뜀). 마이그레이션 전이거나, DB가 꺼져 있거나, 시드 비밀번호가 없으면 안내 메시지와 함께 종료 코드 1로 끝난다.
- 시드의 도서·ISBN·출판사·회원 이름은 Faker로 만든 데모용 가짜 데이터다. 체크 디지트는 맞지만 실제 도서와 우연히 겹칠 수 있다. 시드의 공식 서지도 연결을 보여 주는 데모 값이다.
- `add_library_books` 마이그레이션은 기존 `books` 값을 기관 도서로 옮기고 `books`를 비운다. 사본이 없던 도서는 사라진다.

### 시드 데이터와 계정

| 기관 | 운영 방식 | 관리자 | 키오스크 |
| --- | --- | --- | --- |
| 햇살 작은도서관 | `internal` (대출 14일, 대출·연체 데이터 있음) | `sunny-admin` | `sunny-kiosk` |
| 푸른숲 작은도서관 | `imported` | `forest-admin` | `forest-kiosk` |

비밀번호는 `.env`의 `SEED_ADMIN_PASSWORD`, `SEED_KIOSK_PASSWORD`다 (`.env.example`의 개발용 값).

### 인증 사용법

1. `POST /auth/login`에 `{"login_id": "sunny-kiosk", "password": "..."}`를 보내 토큰을 받는다.
2. 이후 요청에 `Authorization: Bearer <토큰>` 헤더를 붙인다. Swagger에서는 오른쪽 위 **Authorize**에 토큰을 넣는다.
3. 키오스크(도서관 PC)는 기관 정보·기관 도서·사본 조회, 대출·반납, AI 사서 대화만 할 수 있다. 나머지는 관리자만 할 수 있고, 키오스크가 부르면 403이다.
4. 토큰 만료: 관리자 12시간, 키오스크 30일 (`ADMIN_TOKEN_HOURS`, `KIOSK_TOKEN_HOURS`). `POST /auth/logout`으로 끊고, 비밀번호를 바꾸면 그 계정의 기존 토큰이 모두 끊긴다.

### 이전 스키마(무인 서점)에서 넘어올 때

초기 마이그레이션을 새 도메인으로 다시 만들었다. 이전 리비전(`896d5140154e`)이 적용된 로컬 DB는 **이전 코드가 있는 커밋에서** 먼저 내린 뒤 새 코드로 올린다.

```bash
uv run alembic downgrade base
```

이미 새 코드로 바꿨다면 DB 볼륨을 지우고 다시 만드는 편이 간단하다 (`docker compose down -v` 후 `docker compose up -d db`). 로컬 데이터가 모두 지워진다.

## 장서 가져오기

기존 대출 프로그램의 엑셀(xlsx)·CSV 내보내기로 장서를 채운다. `loan_mode = imported` 기관의 관리자만 쓸 수 있다.

1. `POST /holding-imports`에 파일을 올린다 (multipart `file`). 장서는 바뀌지 않고 미리 보기가 만들어진다.
2. 응답의 `summary`(새 사본, 바뀐 사본, 건너뛴 행, 표기, 파일에서 빠진 사본 수)와 `GET /holding-imports/{id}/rows`를 확인한다.
3. `POST /holding-imports/{id}/apply`로 적용한다.

- **필수 열은 등록번호, 서명, 저자 세 개다.** `자료번호`, `도서명`, `지은이`처럼 흔한 표기를 인식하고, 머리글 위의 제목 줄도 건너뛴다. 인식하지 못하면 `column_mapping`에 `{"author": "책임표시"}`처럼 지정한다.
- 가져오기는 기관 도서와 사본만 쓴다. 공식 서지가 없어도 끝나고, ISBN이 같은 공식 서지가 있으면 연결한다. 같은 책 찾기는 그 기관 안에서만 한다.
- 나머지 열(ISBN, 출판사, 청구기호, 별치기호, 자료실, 대출 상태, 수입구분, 가격, 기증처, 분류기호, 부가기호)은 있으면 쓴다. 파일에 없는 값은 기존 값을 유지한다.
- 인식하지 못한 열은 저장하지 않는다. 원본 파일도 보관하지 않는다.
- 매입 사본에 ISBN이나 가격이 없으면 오류가 아니라 표기다. `GET /holdings?incomplete=true`로 모아 본다.
- 다시 가져오면 파일에서 빠진 사본은 제적(`withdrawn`)되고, 다시 나타나면 복구된다. 빠진 사본이 절반 이상이면 `?confirm_withdraw=true`가 필요하다.
- 별치기호(`아`, `아동`, `어린이`, `유`, `유아`, `j`)·자료실·부가기호(첫 자리 6, 7)로 그 기관의 어린이 도서를 분류한다. 관리자가 지정한 값이 우선한다.

가상 내보내기 파일로 인식률을 재는 평가는 다음으로 실행한다.

```bash
uv run python -m evals.holdings_import
```

## 어린이 구분

기관 개별 기능이다. 공통 API의 응답에는 어린이 값이 없고 `/children`에서 다룬다.

| API | 하는 일 | 권한 |
| --- | --- | --- |
| `GET /children/books` | 자기 기관의 어린이 도서 목록 | 직원 |
| `GET /children/books/{id}` | 대상 구분과 근거 | 직원 |
| `PUT /children/books/{id}` | 관리자 지정 | 관리자 |
| `POST /children/refresh` | 공식 서지의 분류 원문으로 갱신 | 관리자 |

근거의 우선순위는 `manual`, `import_label`, `external_category`, `default` 순이다. 저장된 값이 없으면 `general`, `default`다.

## 패키지 구조

`features → library → central → core` 방향으로만 의존한다. `tests/platform/test_package_layers.py`가 강제한다.

- `app/agent/`: 공통 실행기. `app/core`만 의존하고 세 층이 필요하면 import한다
- `app/central/`: 운영자 층. 공식 서지와 외부 연동
- `app/library/`: 기관 공통
- `app/features/`: 기관 개별 기능. 공통은 훅(`app/library/hooks.py`)으로 사건만 알리고, 기능은 `app/main.py`에서 등록한다

## AI 사서

| API | 하는 일 | 권한 |
| --- | --- | --- |
| `POST /librarian/messages` | `{"session_id": null, "message": "공룡 책 추천해줘"}`를 보내면 SSE로 답한다 | 직원(키오스크 포함) |
| `DELETE /librarian/sessions/{id}` | 대화를 바로 끝내고 메시지를 지운다 | 직원 |

- SSE 사건은 `session`(세션 id), `status`(진행 문구), `answer`(문장, 추천 카드, 희망도서 안내 표시, 운영 방식), `done`(실행 id, 상태) 순서다. 답은 검사를 통과한 뒤 한 번에 나가고, 카드는 코드가 DB 값으로 만든다.
- 추천은 그 기관의 추천 가능한 책(대출 가능이나 대출 중 사본이 있는 책)만이다. 어린이 요청(코드가 문장으로 판단)에는 그 기관의 어린이 도서만 나간다. 둘 다 최종 검사가 코드로 막는다.
- 전화번호, 이메일, 주민등록번호, 그 기관의 회원번호는 LLM과 저장 전에 `[개인정보]`로 가린다. 이름은 가리지 못한다.
- 대화는 마지막 입력에서 `LIBRARIAN_SESSION_IDLE_MINUTES`(5분)가 지나면 끝나고, 서버가 1분마다 지운다. 세션당 `LIBRARIAN_MAX_TURNS`(20턴), 기관당 하루 `LIBRARIAN_DAILY_RUN_LIMIT`(500회), 문장 500자가 상한이다. 넘으면 409, 429, 422다. 같은 세션에 답을 기다리는 중 다시 보내면 409다.
- 보인 추천은 `recommendation_events`에 남는다. 회원, 세션, 문장은 남기지 않는다.

## 에이전트 실행기

공통 실행기는 `app/agent/`에 있다. `.env`의 `OPENAI_API_KEY`가 없어도 서버는 시작하고, 실행만 고정 답으로 끝난다. 기본 모델은 `LLM_MODEL`이고, 모델별 토큰 가격은 `app/core/config.py`의 `LLM_PRICES`에 있다. 규칙은 [app/agent/README.md](app/agent/README.md)를 참고한다.

## 서지정보 채움 (운영자)

공식 서지(`books`)는 서비스 운영자가 YES24로 채운다. 기관 API로는 실행할 수 없다. `.env`에 `YES24_API_KEY`가 필요하다.

```bash
uv run python scripts/enrich_books.py --limit 100
```

- 어느 기관이든 소장한 처리 대기 ISBN을 `--limit`개까지 처리한다. 같은 ISBN은 한 번만 조회하고, 공식 서지가 이미 있으면 호출 없이 연결한다.
- 처리 상태는 기관 도서마다 저장한다. 다시 실행하면 남은 ISBN부터 이어서 처리한다.
- 찾지 못한 도서(`not_found`, `mismatch`)는 `--retry-failed`를 줄 때만 처리 대기 뒤에 다시 조회한다.
- 호출 한도는 하루 20,000회, 초당 10회이고 초당 5회 이하로 호출한다. 한도 초과나 외부 장애가 나면 사유를 출력하고 멈춘다.
- 종료 코드: `0` 완료, `1` 키·인자·DB 문제, `2` 외부 장애로 중단.
- 기관 도서의 파일 값과 어린이 구분은 바뀌지 않는다. 연결되면 조회할 때 공식 값과 출처(`external_source`, `external_url`)가 나온다.
- 어린이 구분은 기관 개별 기능이다. 채움 뒤 기관 관리자가 `POST /children/refresh`를 호출하면 자기 기관 도서를 공식 서지의 분류 원문으로 갱신한다. 어린이 구분이 필요 없는 기관은 호출하지 않으면 된다.
- 기관 관리자는 `GET /book-enrichment`로 자기 기관의 처리 현황을 본다.
- YES24 이용 조건에 따라 소장 도서의 ISBN만 조회하고, 판매가와 판매 상태는 저장하지 않는다. 표지는 원본 URL만 저장한다.

### AI 사서 평가

YES24 상품 검색으로 받은 표본 약 100권(`evals/librarian/data/yes24_sample.json`)을 테스트 DB의 가상 기관에 적재해 시나리오를 실제 LLM으로 돌리고, 규칙 검사 표를 낸다. 표본은 YES24 이용 조건(축적·재배포 금지) 때문에 저장소에 없고, 다시 받지 않는다. 실제 LLM 비용이 든다.

```bash
uv run python -m evals.librarian --only dinosaur,not-held
```

- 테스트 DB 트랜잭션 안에서 돌고 되돌린다. 개발 DB는 쓰지 않는다.
- 규칙 검사: 추천 가능하지 않은 책 추천, 어린이 요청의 일반 도서, 이름·연락처를 묻는 문장, 문장 속 소장하지 않은 서명. 고정 답 비율도 낸다. 위반이나 기대 불일치가 있으면 종료 코드 1이다.
- 서지는 실제 값이지만 기관과 사본 상태는 가상이다. 수치를 실제 서비스 성능으로 쓰지 않는다.

## 테스트와 린트

테스트는 실제 PostgreSQL(`TEST_DATABASE_URL`)에서 돈다. DB 컨테이너가 떠 있어야 한다.

```bash
uv run pytest
```

`tests/samples/`의 표본 테스트(`sample` 표시)는 표본 파일이 있을 때만 돌고, 없으면 건너뛴다. 스펙 시나리오는 표본 없이도 도는 시나리오 테스트가 맡는다. 표본 테스트만 빼려면 다음을 쓴다.

```bash
uv run pytest -m "not sample"
```

```bash
uv run ruff check . && uv run ruff format --check .
```

## 개발 흐름

기능 작업은 OpenSpec change 단위로 한다 (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`). 규칙은 CLAUDE.md의 "OpenSpec 작업 규칙"을 따른다.
