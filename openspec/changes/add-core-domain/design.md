# Design

## Context

저장소에는 아직 코드가 없다 (`CLAUDE.md`, `docs/design.md`, `openspec/`만 있음). 동기는 proposal.md - Why 참고. 이번 change에서 정하는 도메인 경계, 디렉터리 구조, 세션 관리, 테스트 방식, 상태 값 표현이 이후 모든 change의 기본값이 되므로 여기서 결정해 둔다. 코딩 규칙(async, Pydantic 스키마, int 금액, StrEnum, `.env`)은 `CLAUDE.md`를 따른다.

## Goals / Non-Goals

**Goals:**
- 테이블과 코드를 세 에이전트(A·B·C)에 맞춘 도메인 컨텍스트로 나눠, 한 에이전트의 change가 다른 에이전트의 테이블과 코드를 건드리지 않게 한다
- 이후 change가 테이블을 새로 만들지 않고 컬럼 추가 정도로 진행할 수 있도록 MVP 테이블의 뼈대를 확정한다
- REST 라우터와 이후 에이전트 tool이 같은 service 함수를 호출하는 구조를 books·inventory·institutions로 먼저 보여 준다
- 실제 PostgreSQL에 대해 도는 테스트 기반을 만든다

**Non-Goals:**
- API가 없는 8개 테이블의 service 함수 (테이블과 모델만 만든다)
- 상태 전이 규칙(어떤 상태에서 어떤 상태로 갈 수 있는가). 값의 집합만 제약한다
- 컨텍스트별 DB 권한 분리, 별도 DB 분리
- 운영 배포 설정 (앱 컨테이너 이미지, CI). Compose에는 DB만 둔다

## Decisions

### 1. 도메인 컨텍스트

데이터를 "누가 만들고 책임지는가"로 나눈다. 다른 컨텍스트가 읽기만 하는 것은 소유를 바꾸지 않는다.

| 컨텍스트 | 에이전트 | 테이블 | 쓰는 쪽 | 읽는 쪽 |
| --- | --- | --- | --- | --- |
| catalog | 공유 | books, store_inventory | 사장님(관리 API), 이후 외부 API 캐싱 | A, B, C 모두 |
| storefront | A 매장 큐레이터 | chat_logs, owner_messages, book_requests | 손님 대화 중 A | B (주간 요약, 문의·주문 처리) |
| owner-ops | B 사장님 운영 | curations, quotes(글귀) | B와 사장님 승인 | A (승인·게시된 것만) |
| supply | C 기관 납품 | institutions, institution_orders, order_items, quote_drafts | C와 사장님 확인 | (없음) |

판단이 갈린 테이블:
- `owner_messages`, `book_requests`: 사장님이 처리하지만, 손님 응대 중 A가 만들고 손님 연락처·대화 맥락에 붙어 있으므로 storefront 소유. B는 storefront의 service를 통해 상태만 바꾼다.
- `quotes`(글귀): A가 화면에 띄우지만, 사장님이 등록·관리하므로 owner-ops 소유.
- `store_inventory`: 매장(A) 데이터처럼 보이지만 B의 신간 큐레이션·C의 납품 가능 여부 확인도 쓰므로 catalog에 둔다.
- `institutions`: C만 쓰므로 공유가 아니라 supply.

**경계 규칙**
1. catalog는 공유 커널이다. 다른 컨텍스트는 `books.isbn`을 외래 키로 참조할 수 있다. catalog는 다른 컨텍스트를 알지 못한다 (외래 키, import 모두).
2. storefront, owner-ops, supply 사이에는 외래 키를 두지 않는다. 다른 컨텍스트 데이터가 필요하면 그 컨텍스트의 service 함수를 호출한다.
3. 한 컨텍스트의 테이블은 그 컨텍스트의 service만 쓴다. 다른 컨텍스트의 models를 import하지 않는다.

규칙 1·2(외래 키)는 스펙(`platform/database-schema`)과 metadata 검사 테스트로, 규칙 3(import)은 `tests/test_boundaries.py`의 AST 검사로 지킨다.

- 대안 A: 컨텍스트 구분 없이 평평하게 → 지금은 편하지만, 이후 A의 change가 C 테이블에 컬럼을 붙이는 식으로 섞이기 쉬워 기각.
- 대안 B: PostgreSQL 스키마(`catalog.books`, `supply.order_items`)로 물리적으로 분리 → 경계가 DB에서도 보이지만, Alembic `include_schemas`·`search_path` 설정과 테스트 DB 초기화가 복잡해진다. 지금은 단일 DB 사용자라 권한 분리 이점도 없어 보류. 경계 규칙을 지켜 두면 이후 스키마 이동은 테이블 단위 `ALTER TABLE ... SET SCHEMA`로 가능하다.
- 대안 C: import-linter로 import 규칙 검사 → 선언적이지만 의존성이 하나 늘고, 지금 규칙은 AST 검사 테스트 하나로 충분해 보류.

### 2. 프로젝트 구조와 계층

`CLAUDE.md`의 계층(api → services → models, schemas)을 유지하고, 각 계층 안을 컨텍스트로 나눈다.

```
app/
├── core/                  # config, db
├── models/
│   ├── base.py            # Base, timestamp mixin
│   ├── catalog.py         # Book, StoreInventory
│   ├── storefront.py      # ChatLog, OwnerMessage, BookRequest
│   ├── owner_ops.py       # Curation, Quote
│   └── supply.py          # Institution, InstitutionOrder, OrderItem, QuoteDraft
├── schemas/{common,catalog,supply}.py
├── services/
│   ├── errors.py
│   ├── catalog/{books,inventory}.py
│   └── supply/institutions.py
├── api/
│   ├── catalog.py         # /books, /inventory 라우터
│   └── supply.py          # /institutions 라우터
└── matching/isbn.py       # ISBN 정규화·검증 (순수 함수, 컨텍스트 무관)
```

API가 없는 storefront, owner-ops는 이번에 models만 만든다. 상태 `StrEnum`은 해당 컨텍스트의 models 모듈에 함께 둔다. 이 구조는 tasks의 마지막 그룹에서 `CLAUDE.md` 디렉터리 구조에 반영한다.

service 함수는 `AsyncSession`을 첫 인자로 받고 Pydantic 스키마를 입력으로, ORM 객체를 출력으로 다룬다. 응답 변환(ORM → 스키마)은 라우터의 `response_model`이 맡는다. service는 HTTP를 모른다. 도메인 오류는 `app/services/errors.py`의 예외(`NotFoundError`, `ConflictError`)로 올리고, `main.py`의 exception handler가 404/409로 바꾼다. 에이전트 tool이 같은 service를 부를 때 HTTPException에 묶이지 않기 위해서다.

- 대안: 컨텍스트를 최상위 패키지로(`app/supply/{models,services,api}.py`) → 경계는 더 뚜렷하지만 `CLAUDE.md`의 계층 구조와 어긋나 기각. 컨텍스트가 커지면 다시 검토한다.

### 3. 기본 키
- `books`: `isbn`(CHAR(13))을 자연키 PK로 쓴다. 매칭·재고·주문 모두 ISBN으로 연결되고, ISBN이 바뀌면 다른 책이라는 도메인 규칙과 맞는다.
- `store_inventory`: `isbn`을 PK이자 `books.isbn` FK로 둔다 (ISBN당 재고 1건).
- 나머지 테이블: `id` BIGINT identity.
- 대안: 모든 테이블 surrogate id → books 조회마다 ISBN→id 변환이 생겨 기각. 재정가 이력·판본 분리는 이후 catalog에 별도 테이블로 확장한다.

### 4. ISBN 처리
정규화(하이픈·공백 제거)와 ISBN-13 체크 디지트 검증은 `app/matching/isbn.py`의 순수 함수로 둔다. 이후 C의 매칭 파이프라인이 같은 함수를 재사용한다. Pydantic 스키마는 이 함수를 `AfterValidator`로 쓰고, 경로 파라미터(`/books/{isbn}`)도 같은 함수로 정규화한다. DB에는 `CHECK (isbn ~ '^[0-9]{13}$')`를 둔다 (체크 디지트는 DB에서 검사하지 않음).

### 5. 상태 값 표현
상태는 코드에서 `StrEnum`, DB에서는 `VARCHAR` + `CHECK` 제약으로 저장한다 (SQLAlchemy `Enum(..., native_enum=False, create_constraint=True)`).
- 대안: PostgreSQL native ENUM → 값 추가 시 `ALTER TYPE`과 트랜잭션 제약 때문에 Alembic 마이그레이션이 번거로워 기각.

| 컨텍스트 | 테이블.컬럼 | 값 | 기본값 |
| --- | --- | --- | --- |
| storefront | chat_logs.role | customer, assistant | (필수) |
| storefront | owner_messages.status | unread, read, resolved | unread |
| storefront | book_requests.status | received, ordered, notified, closed | received |
| owner-ops | curations.kind | today_pick, recommendation_card | (필수) |
| owner-ops | curations.status | draft, pending_approval, approved, published | draft |
| supply | institutions.type | school, daycare, community_center, military, other | (필수) |
| supply | institution_orders.status | uploaded, matching, reviewing, quoted | uploaded |
| supply | order_items.match_status | unmatched, auto_matched, needs_confirmation, confirmed, rejected | unmatched |
| supply | quote_drafts.status | draft, pending_approval, approved, sent | draft |

### 6. 테이블 뼈대
모든 테이블에 `created_at`, `updated_at`(timestamptz, 서버 기본값)을 둔다. 금액은 `INTEGER` + `CHECK (>= 0)`. 화살표(→)는 외래 키다.

| 컨텍스트 | 테이블 | 주요 컬럼 |
| --- | --- | --- |
| catalog | books | isbn PK, title, author, publisher?, published_date?, list_price, cover_url?, description? |
| catalog | store_inventory | isbn PK → books, quantity (>=0), shelf_location? |
| storefront | chat_logs | id, session_id, role, content |
| storefront | owner_messages | id, chat_session_id?, content, contact?, status |
| storefront | book_requests | id, isbn? → books, title, author?, contact, status, memo? |
| owner-ops | curations | id, kind, isbn? → books, title, body, status, approved_at?, published_at? |
| owner-ops | quotes (글귀) | id, text (빈 문자열 불가), isbn? → books, source_note?, is_active |
| supply | institutions | id, name, type, contact_name?, phone?, email?, address?, memo? |
| supply | institution_orders | id, institution_id → institutions, source_filename, status |
| supply | order_items | id, order_id → institution_orders, row_no, raw_title, raw_author?, raw_publisher?, raw_isbn?, raw_volume?, quantity (>=1), matched_isbn? → books, confidence? (0~1), match_status |
| supply | quote_drafts (견적서) | id, institution_id → institutions, order_id? → institution_orders, subtotal, discount_amount, total, status, approved_at? |

`owner_messages.chat_session_id`는 같은 storefront의 `chat_logs.session_id`를 가리키는 값이지만, chat_logs는 세션 테이블이 없어 외래 키 없이 둔다. `quotes`(글귀)와 `quote_drafts`(견적서)는 이름이 비슷하지만 컨텍스트가 다르다. `docs/design.md`의 테이블명을 유지하고, 모델 docstring에 의미를 적는다. 견적 항목 테이블은 견적 change에서 supply에 추가한다.

외래 키는 모두 `ON DELETE RESTRICT`. 삭제 거부 처리:
- 같은 컨텍스트 안의 참조(재고 → 도서, 주문 목록·견적서 → 기관)는 service가 먼저 확인해 `ConflictError`로 올린다.
- 다른 컨텍스트에서 catalog로 오는 참조(curations, order_items 등 → books)는 catalog service가 다른 컨텍스트를 알면 안 되므로 미리 확인하지 않는다. 삭제 시 DB의 `IntegrityError`(FK 위반)를 잡아 `ConflictError`로 바꾼다.

### 7. 페이지네이션
목록 응답은 `{"items": [...], "total": int, "limit": int, "offset": int}` 공통 제네릭 스키마(`Page[T]`, `schemas/common.py`)를 쓴다. 정렬은 books=title, inventory=shelf_location→isbn, institutions=id.

### 8. DB 세션과 설정
`pydantic-settings`의 `Settings`가 `.env`에서 `DATABASE_URL`(postgresql+asyncpg)을 읽는다. `create_async_engine` 하나를 앱 수명 동안 쓰고, `get_session` 의존성이 요청당 `AsyncSession`을 주고 끝나면 닫는다. 커밋은 service 함수가 쓰기 작업 끝에 한다.

Alembic은 async 템플릿(`alembic init -t async`)으로 만들고, `env.py`는 `app.models`를 import해 네 컨텍스트 모델을 모두 `Base.metadata`에 등록한다. 초기 마이그레이션은 autogenerate 후 CHECK 제약 등을 사람이 검토해 하나의 리비전으로 둔다. 이후 change는 자기 컨텍스트 테이블만 바꾸는 리비전을 추가한다.

### 9. 테스트
SQLite 대신 실제 PostgreSQL에서 테스트한다 (CHECK 정규식, FK RESTRICT, identity 동작이 다르기 때문). Compose의 DB 컨테이너 초기화 스크립트가 `chaekbang_test` DB를 추가로 만들고, 테스트는 `TEST_DATABASE_URL`을 쓴다.
- 세션 시작 시 테스트 DB에 `alembic upgrade head`를 한 번 적용 (마이그레이션 자체도 검증됨)
- 각 테스트는 연결 단위 트랜잭션 안에서 돌고 끝나면 롤백 (`join_transaction_mode="create_savepoint"`)
- API 테스트는 `httpx.AsyncClient` + `ASGITransport`, `get_session`을 테스트 세션으로 override
- 테스트 폴더도 컨텍스트별로 나눈다: `tests/{catalog,storefront,owner_ops,supply,platform}/`
- 테스트 함수 docstring에 `[capability] Requirement / Scenario`를 적어 스펙 추적
- 대안: testcontainers → 별도 Docker 제어와 시작 시간이 늘어 이번 단계에선 기각.

### 10. 시드 데이터
`scripts/seed.py`는 `Faker("ko_KR")`와 고정 seed로 결정적 데이터를 만든다. 도서 제목은 Faker에 책 제목 생성기가 없어 단어 조합 목록으로 만들고, ISBN은 `979-11-` 접두 + 임의 9자리 + 계산한 체크 디지트로 생성한다. 정가는 1,000원 단위 8,000~35,000원. 재고는 50권 중 35권 정도에 수량 0~5로 만들어 품절·미보유 케이스를 둘 다 둔다. 기관은 학교·어린이집·동사무소 3곳.

시드는 catalog와 supply 데이터를 만들므로 각 컨텍스트의 시드 함수(`catalog` 도서·재고, `supply` 기관)를 따로 두고 `scripts/seed.py`가 순서대로 부른다. 시드도 경계 규칙을 따라 다른 컨텍스트의 모델을 직접 섞어 쓰지 않는다.

반복 실행은 "있으면 건너뛰기"로 처리한다: books·store_inventory는 ISBN 기준 `INSERT ... ON CONFLICT DO NOTHING`, institutions는 같은 이름이 있으면 건너뛴다. 데이터를 지우는 TRUNCATE는 쓰지 않는다 (사장님이 손으로 넣은 개발 데이터를 지우지 않기 위해).

시드 로직은 `scripts/seed.py`가 호출하는 함수로 분리해 테스트에서 테스트 DB에 직접 실행한다.

**전제 조건 확인과 종료 코드.** 데이터를 쓰기 전에 다음 순서로 확인하고, 실패하면 아무것도 쓰지 않고 stderr에 한 줄 메시지를 출력한 뒤 `sys.exit(1)`로 끝낸다. 예외는 `main()`에서 잡아 메시지로 바꾸고 트레이스백은 출력하지 않는다.
1. 연결: `connect_args={"timeout": 5}`로 연결해 DB가 꺼져 있을 때 오래 기다리지 않게 한다. 연결 오류(`OSError`, asyncpg 연결 예외)는 `URL.render_as_string(hide_password=True)`에서 뽑은 호스트·포트·DB 이름과 `docker compose up -d db` 안내로 바꾼다.
2. 마이그레이션: `alembic_version`의 현재 리비전을 읽고 `ScriptDirectory.get_current_head()`와 비교한다. 테이블이 없거나 리비전이 다르면 `uv run alembic upgrade head` 안내를 출력한다. 테이블 존재 여부만 보는 방식은 컬럼이 추가된 이후 리비전을 놓치므로 쓰지 않는다.

종료 코드는 원인과 상관없이 1로 통일한다 (원인은 메시지로 구분). 시드가 쓰는 작업은 하나의 트랜잭션으로 묶어 중간 실패 시 부분 데이터가 남지 않게 한다.

테스트: 마이그레이션 미적용·뒤처짐은 롤백되는 테스트 트랜잭션 안에서 `alembic_version`을 비우거나 바꾼 뒤 확인 함수를 호출한다 (PostgreSQL DDL/DML이 트랜잭션에 묶이므로 테스트 DB가 오염되지 않는다). 연결 실패는 쓰이지 않는 포트를 가리키는 `DATABASE_URL`로 `scripts/seed.py`를 subprocess로 실행해 종료 코드와 stderr를 확인한다.

### 11. Docker Compose
`postgres:16` 서비스 하나, 볼륨 `pgdata`, 포트 5432, healthcheck(`pg_isready`). `docker/postgres/init/01-create-test-db.sql`로 테스트 DB를 만든다. 앱은 호스트에서 `uv run`으로 실행한다.

## Risks / Trade-offs

- [컨텍스트 경계가 실제 업무와 어긋날 수 있음 (예: B가 storefront 데이터를 자주 바꿔야 함)] → 경계를 넘는 쓰기는 소유 컨텍스트의 service 함수로만 한다. 그런 호출이 많아지면 테이블 소유를 옮기는 change를 따로 연다.
- [다른 컨텍스트에서 오는 books 참조는 삭제 시점에야 409로 드러남] → 도서 삭제는 드문 관리 작업이라 받아들인다. 응답 메시지에 "다른 데이터가 참조 중"이라고 적는다.
- [11개 테이블 뼈대를 미리 확정하면 이후 change에서 바뀔 수 있음] → API가 없는 테이블은 최소 컬럼만 두고, 변경은 각 컨텍스트 change에서 새 마이그레이션으로 한다. 스펙에는 상태 값과 제약만 넣고 컬럼 전체 목록은 넣지 않는다.
- [ISBN 자연키 PK는 ISBN 없는 도서(오래된 책, 비매품)를 담을 수 없음] → book_requests·order_items는 ISBN을 nullable로 두고 원문 필드를 따로 저장한다. books에는 ISBN 있는 책만 둔다.
- [실제 PostgreSQL 테스트는 Docker가 떠 있어야 함] → `README.md`와 `CLAUDE.md`의 명령으로 안내하고, DB가 없으면 conftest가 명확한 메시지로 실패하게 한다.
- [Faker로 만든 ISBN은 실제 도서와 겹칠 수 있음] → 데모용임을 README에 적고, 외부 API 연동 change에서 시드를 실제 ISBN으로 바꿀지 다시 판단한다.

## Migration Plan

첫 스키마이므로 기존 데이터 이전은 없다. 롤백은 `alembic downgrade base`.
