# Design

## Context

**지금 코드에 있는 것** (1주차 `add-core-domain`, 무인 서점 방향)
- 도메인 컨텍스트 4개(catalog / storefront / owner_ops / supply)로 나눈 11개 테이블과 그 모델·service·API
- 시드와 테스트, 컨텍스트 경계 검사
- 공통 인프라: FastAPI, async SQLAlchemy, Alembic, 실제 PostgreSQL 테스트(savepoint 롤백), 시드 실행기의 전제 조건 확인, `Page[T]`, `PatchModel`, 도메인 예외 → HTTP 상태 변환

방향 전환의 이유와 범위는 proposal.md를 참고한다. 이번 change는 **공통 인프라는 그대로 두고 도메인만 바꾼다.**

## Goals / Non-Goals

**Goals:**
- 기관 분리를 세 곳에서 강제한다. 하나가 빠져도 다른 기관 데이터가 새지 않게 하기 위해서다.
  - 인증 토큰 → 현재 기관
  - service 쿼리 → `library_id` 필터
  - DB → 같은 기관끼리만 참조하는 복합 외래 키
- REST와 이후 에이전트 tool이 같은 service 함수를 쓰도록, service는 HTTP를 모르고 `library_id`를 명시적으로 받는다.
- 이후 change(가져오기, 에이전트, 승인)가 테이블을 다시 만들지 않고 컬럼이나 테이블을 더하는 식으로 갈 수 있게 사본·도서 모델을 잡는다.

**Non-Goals:**
- 기관 생성·삭제 API, 기관을 넘나드는 운영자(super admin)
- 비밀번호 재설정 메일, 로그인 시도 제한, 2단계 인증
- 장서 가져오기, 어린이 도서 자동 분류, 임베딩, 이후 단계 테이블 (큐레이션, 희망도서, 구매 요청서, 대화, 에이전트 실행 기록)
- 연체 알림, 대출 연장·예약

## Decisions

### 1. 이전 도메인 정리와 마이그레이션 재작성

이전 초기 리비전(`896d5140154e`)을 지우고, 새 도메인 기준의 초기 리비전 하나를 새로 만든다.

- **이유**
  - 배포한 적이 없고, 이전 테이블 11개를 지우는 리비전과 새 테이블을 만드는 리비전을 이어 붙이면 이력만 길어진다.
  - 방향 전환의 기록은 git과 OpenSpec archive에 남는다.
- **순서가 중요하다.** 리비전 파일을 지우기 전에 로컬 개발 DB와 테스트 DB를 `alembic downgrade base`로 내린다. 지운 뒤에는 Alembic이 DB에 남은 리비전을 찾지 못한다.
- **대안: 이전 테이블을 지우는 새 리비전 추가** → 이력은 보존되지만, 새로 받은 사람도 이전 도메인 스키마를 한 번 만들었다 지우게 된다. 얻는 것이 없어 기각했다.

지우는 것:
- 컨텍스트별 models·services·api·seed
- 관련 테스트
- `tests/platform/test_boundaries.py`
- `CONTEXT_TABLES`

`app/matching/isbn.py`는 `app/core/isbn.py`로 옮긴다. ISBN 규칙은 도서 스키마와 이후 장서 가져오기가 함께 쓰는 공통 규칙이고, `matching/` 패키지는 새 구조에 없다.

### 2. 모듈 구성

`CLAUDE.md`의 계층(api → services → models, schemas)을 따르고, 파일은 도메인 묶음으로 나눈다. 컨텍스트 경계 검사는 두지 않는다. 대신 기관 분리 테스트가 핵심 검사가 된다.

```
app/core/
├── config.py      # + 토큰 만료 시간, 기관 시간대, 시드 비밀번호
├── db.py
├── isbn.py        # (이동) ISBN 정규화·검증
├── security.py    # 비밀번호 해시(scrypt), 토큰 생성·해시
├── deps.py        # CurrentStaff(토큰 → 직원·기관), require_admin
└── clock.py       # 기관 시간대 기준 오늘 (테스트에서 바꿔 끼운다)
app/models/
├── base.py
├── library.py     # Library, StaffUser, StaffSession
├── catalog.py     # Book, Holding
└── circulation.py # Member, Loan
app/services/      # auth.py, library.py, staff.py, books.py, holdings.py, members.py, loans.py
app/api/           # auth.py, library.py, staff.py, books.py, holdings.py, members.py, loans.py
app/seed/          # library.py, catalog.py, circulation.py, runner.py
```

`app/models/__init__.py`에는 `SHARED_TABLES = {"libraries", "books"}`와 `TENANT_TABLES`를 둔다. 스키마 테스트가 이 두 묶음으로 "기관 데이터 테이블 구분"을 검사한다.

### 3. 기관 분리를 강제하는 방식

**토큰 → 기관**
- `CurrentStaff` 의존성은 bearer 토큰으로 `staff_sessions`를 찾는다.
- 결과로 `StaffContext(staff_id, library_id, role)`를 돌려준다.
- 요청 본문·쿼리의 `library_id`는 스키마에 아예 두지 않는다. Pydantic 기본 설정이 모르는 필드를 무시하므로 본문에 넣어 보내도 쓰이지 않는다.

**service → 필터**
- 기관 데이터를 다루는 모든 service 함수는 `(session, library_id, ...)`를 받는다.
- 단건 조회는 공통 헬퍼 `get_owned(session, Model, library_id, id)`로 한다. 다른 기관의 행이면 `NotFoundError`를 올린다.
- 목록은 항상 `where(Model.library_id == library_id)`로 시작한다.

**DB → 복합 외래 키**
- holdings와 members에 `UNIQUE (library_id, id)`를 둔다.
- loans는 `(library_id, holding_id) → holdings(library_id, id)`, `(library_id, member_id) → members(library_id, id)`로 참조한다.
- staff_sessions도 `(library_id, staff_user_id) → staff_users(library_id, id)`로 참조한다.
- service에 버그가 있어도 다른 기관 사본으로 대출하는 행은 DB가 거부한다.

**대안: PostgreSQL Row Level Security** → 가장 강하지만 세션마다 `SET app.library_id`가 필요하고, 테스트·Alembic·이후 자연어 SQL용 읽기 전용 role 설계와 얽힌다. 자연어 SQL change(5주차)에서 분석용 view와 함께 다시 검토한다.

### 4. 인증

**비밀번호**
- 표준 라이브러리 `hashlib.scrypt`를 쓴다 (n=2^14, r=8, p=1, 16바이트 salt).
- 저장 형식: `scrypt$n$r$p$salt$hash` (base64)
- 비교는 `hmac.compare_digest`로 한다.
- 없는 아이디일 때도 더미 해시를 한 번 검증해, 응답 시간으로 아이디 존재 여부가 드러나지 않게 한다.
- 대안
  - passlib + bcrypt → passlib은 유지보수가 멈췄고 의존성이 늘어 기각했다.
  - argon2-cffi → 좋은 선택이지만, 지금 요구에는 표준 라이브러리로 충분하다.

**토큰**
- `secrets.token_urlsafe(32)`로 만든 불투명 토큰을 발급한다.
- DB(`staff_sessions`)에는 원문이 아니라 SHA-256 해시를 저장한다. 함께 저장하는 것: 만료 시각, 로그아웃 시각.
- 요청마다 다음을 모두 확인하고, 하나라도 아니면 401이다.
  - 해시로 찾은 세션이 있음
  - 로그아웃하지 않음
  - 만료되지 않음
  - 계정이 사용 중임
- 대안: JWT → 서버 저장이 필요 없지만, 로그아웃과 계정 사용 중지를 즉시 반영하려면 결국 차단 목록이 필요하다. 공용 PC 키오스크 토큰은 즉시 끊을 수 있어야 해서 기각했다.

**만료 시간** (`.env`)
- `ADMIN_TOKEN_HOURS=12`
- `KIOSK_TOKEN_HOURS=720` (도서관 PC에 켜 두는 화면이라 길게)

**역할 검사**: `require_admin` 의존성이 키오스크면 403을 돌려준다.
- 역할은 토큰에 넣지 않고 요청마다 `staff_users`에서 읽는다 (세션 조회와 같은 쿼리로 JOIN). 역할 변경이 바로 반영된다.
- 비밀번호를 바꾸면 그 계정의 열린 세션 전부에 `revoked_at`을 기록한다.
- 401·403은 인증 계층(HTTP)의 관심사라 `deps.py`에서 HTTPException으로 올린다.
- service는 계속 HTTP를 모른다.

### 5. 테이블

모든 테이블에 `created_at`, `updated_at`을 둔다. 상태 값은 `StrEnum` + `VARCHAR`·`CHECK`(1주차 방식 유지)로 저장한다. 외래 키는 모두 `ON DELETE RESTRICT`다.

| 테이블 | 구분 | 주요 컬럼 |
| --- | --- | --- |
| libraries | 공통 | id, name, type(small_library/bookstore), loan_mode(imported/internal), default_loan_days(>=1) |
| staff_users | 기관 | id, library_id, login_id(전역 UNIQUE), password_hash, role(admin/kiosk), is_active |
| staff_sessions | 기관 | id, library_id, staff_user_id, token_hash(UNIQUE), expires_at, revoked_at? |
| books | 공통 | id PK, isbn?(UNIQUE, 값이 있을 때만 CHECK 13자리), title, author, publisher?, published_date?, list_price?(>=0), kdc?, audience(children/general, 기본 general), audience_source(default/manual, 기본 default), cover_url?, description? |
| holdings | 기관 | id, library_id, book_id → books, accession_number, call_number?, shelf_location?, status(available/on_loan/lost/damaged), acquisition_type(purchased/donated), purchase_price?(>=0), donor?, source(manual/imported), last_synced_at?; CHECK(purchased면 purchase_price NOT NULL·donor NULL, donated면 purchase_price NULL); UNIQUE(library_id, accession_number), UNIQUE(library_id, id) |
| members | 기관 | id, library_id, member_number, name; UNIQUE(library_id, member_number), UNIQUE(library_id, id) |
| loans | 기관 | id, library_id, holding_id, member_id?, loaned_on, due_on, returned_on?; 부분 UNIQUE(holding_id) WHERE returned_on IS NULL; CHECK(due_on >= loaned_on); CHECK(returned_on IS NOT NULL OR member_id IS NOT NULL) |

- 필드 이름은 도서관 업무 용어를 따른다: 등록번호는 `accession_number`, 청구기호는 `call_number`, 회원번호는 `member_number`. API 요청·응답 필드도 같은 이름을 쓴다.
- **도서는 내부 id로 식별하고, ISBN은 비어 있을 수 있다.** 작은도서관 장서에는 ISBN이 없는 책(오래된 책, 기증 도서, 지역 자료, 비매품)이 있어서, ISBN을 PK로 두면 2주차 가져오기에서 이런 행을 저장할 수 없다. FK를 나중에 바꾸는 것보다 지금 바꾸는 편이 싸다.
  - ISBN이 있으면 UNIQUE다. PostgreSQL UNIQUE는 NULL을 여러 개 허용하므로 ISBN 없는 책은 여러 권 있을 수 있다.
  - API 경로는 `/books/{id}`이고, ISBN으로 찾을 때는 `GET /books?isbn=`을 쓴다 (정규화 후 일치).
  - ISBN 없는 책끼리의 중복(같은 제목·저자)은 이번에 막지 않는다. 2주차 가져오기의 매칭 규칙에서 다룬다.
- **입수 구분은 사본에 둔다.** 기증 도서와 매입·납품 도서는 관리 기준이 다르다.
  - 매입·납품(`purchased`): 구입가와 ISBN이 필수다. 회계·보충 구매에 쓰이는 책이라 정확한 식별과 금액이 필요하다.
  - 기증(`donated`): 제목·저자와 기증처 정도만 있으면 된다. ISBN과 가격은 없어도 된다.
  - 도서(books)는 기관 공통이라 같은 책이 한 기관에서는 기증, 다른 기관에서는 매입일 수 있다. 그래서 입수 구분·구입가·기증처는 holdings 컬럼이다.
  - 구입가(`purchase_price`)는 실제로 산 가격이라 도서의 정가(`list_price`)와 다를 수 있다 (도서정가제 할인 등). 그래서 둘을 따로 둔다.
- **입수 구분 규칙을 지키는 곳**
  - 구입가·기증처 조합: holdings의 CHECK 제약으로 DB가 강제한다.
  - "매입 사본은 ISBN 있는 도서만": 테이블을 넘는 조건이라 CHECK로 못 건다. 사본 등록·수정 service와 도서 수정 service(매입 사본이 있으면 ISBN 비우기 거부)에서 확인한다. 트리거는 쓰지 않는다.
- **정가(`list_price`)는 선택이다.** 서지정보로서의 정가이고, 기증 도서나 오래된 책은 모르는 경우가 많다. 6주차 보충 구매 요청서는 새로 살 책의 정가(외부 API 결과)를 쓰고, 정가가 없으면 금액을 비워 두고 관리자가 채운다 (코드가 추정하지 않는다).
- **기증처(`donor`)는 자유 텍스트다.** 관리자 화면에만 보이고 이용자 화면과 AI 사서에는 내보내지 않는다. 개인 기증자는 이름 대신 "주민 기증"처럼 적도록 화면 안내를 둔다 (7주차).
- 2주차 가져오기에서 내보내기 파일에 입수 구분(수입구분)이 없으면 어떻게 둘지 정한다. 필요하면 그때 `unknown` 값을 추가한다. `audience_source`처럼 이번에는 쓰는 값만 둔다.
- **청구기호(`call_number`)와 서가 위치(`shelf_location`)는 다르다.** 청구기호는 분류기호·저자기호·권차로 된 서가 주소(예: `813.7-한232ㅊ`)로, 대출 프로그램 내보내기에 거의 항상 있고 AI 사서가 "어느 서가에 있는지" 안내할 때 쓴다. 서가 위치는 "어린이 자료실"처럼 사람이 붙이는 대략적인 위치다. 청구기호는 문자열 그대로 저장하고 해석하지 않는다.
- `audience_source`와 `holdings.source`에는 이번에 쓰는 값만 둔다. 2주차 가져오기 change가 값을 추가한다 (`import_label`, `external_category`, `imported` 사용 시작).
- `kdc`(분류기호)는 문자열로만 둔다. 분야별 장서 통계(5주차)와 어린이 분류 근거(2주차)에서 쓴다.

### 6. 대출 처리

- **사본 잠금:** 대출 시 `SELECT ... FOR UPDATE`로 사본을 잠그고 상태를 확인한다. 동시에 두 요청이 와도 부분 UNIQUE 인덱스가 두 번째를 막고, 이 위반은 `ConflictError`(409)로 바꾼다.
- **오늘 날짜:** "오늘"은 `clock.today()`(설정의 기관 시간대 `Asia/Seoul`)로 구한다. 테스트는 이 함수를 바꿔 끼워 연체 시나리오를 만든다.
- **연체 여부:** 저장하지 않고 조회할 때 계산한다 (`returned_on IS NULL AND due_on < today`). 날짜가 바뀌면 자동으로 맞아야 하기 때문이다.
- **반납은 등록번호로 한다** (`POST /loans/return`). 키오스크와 관리자가 같은 엔드포인트를 쓴다. 등록번호로 사본을 찾고(다른 기관이면 404), 그 사본의 미반납 대출을 잠근 뒤 반납한다. 미반납 대출이 없으면 409다. 대출 id로 반납하는 경로는 두지 않는다.
- **회원 삭제와 대출 기록:** 반납된 대출만 있는 회원은 삭제하면서 그 기록의 `member_id`를 NULL로 바꾼다 (같은 트랜잭션). `loans.member_id`는 NULL을 허용하고, 복합 FK `(library_id, member_id)`는 기본 `MATCH SIMPLE`이라 NULL이면 검사하지 않는다. 미반납 대출은 CHECK로 회원이 반드시 있다.
- **가져오기 기관:** 대출·반납 service는 `loan_mode`가 `imported`면 `ConflictError`("대출은 데스크에서 해 주세요")를 올린다.

### 7. 도서 목록의 기관별 소장 정보

도서는 공통이지만 목록에는 현재 기관의 소장 권수와 대출 가능 권수를 붙인다.
- holdings를 `library_id`로 거른 집계 서브쿼리를 LEFT JOIN한다.
- `held=true`면 소장 권수가 1 이상인 것만 남긴다.
- 이후 AI 사서의 `search_collection`이 이 service를 그대로 쓴다.

### 8. 시드

| 대상 | 내용 |
| --- | --- |
| 기관 | "햇살 작은도서관"(`internal`, 14일), "푸른숲 작은도서관"(`imported`) |
| 계정 | `sunny-admin`, `sunny-kiosk`, `forest-admin`, `forest-kiosk`. 비밀번호는 `.env`의 `SEED_ADMIN_PASSWORD`, `SEED_KIOSK_PASSWORD` (`.env.example`에 개발용 값) |
| 도서 50권 | 기존 생성기(고정 seed, 체크 디지트)를 재사용한다. 어린이 도서 약 15권은 어린이 책다운 제목 목록에서 만들고 `audience=children`, `audience_source=manual`로 둔다. 약 5권은 ISBN·정가 없는 기증 도서로 만든다 |
| 사본 | 기관마다 도서 약 35권, 그중 일부는 2~3권. 분실·훼손 사본을 섞는다. 약 70%는 매입·납품(구입가는 정가의 90%), 나머지는 기증(ISBN 없는 도서는 모두 기증)이다. 가져오기 기관의 사본도 출처는 `manual`이다 (가져오기는 2주차) |
| 회원 | 기관마다 10명 |
| 대출 | 햇살 작은도서관에만 만든다: 반납 5건, 대출 중 5건, 연체 3건 |

- **반복 실행:** 자연키로 "있으면 건너뛰기"를 한다.
  - 기관 이름, 로그인 아이디, 도서 ISBN(ISBN 없는 도서는 제목+저자), (기관, 등록번호), (기관, 회원번호)
  - 대출은 그 기관에 대출이 하나도 없을 때만 만든다.
- **대출 날짜:** 시드를 실행한 날 기준으로 만든다. 연체 대출이 항상 연체 상태로 보이게 하기 위해서다. 그래서 날짜를 뺀 나머지 데이터가 seed마다 같다.
- **전제 조건 확인:** DB 연결과 마이그레이션 head 확인, 종료 코드 규칙은 그대로 둔다.

### 9. 테스트

**기반 유지**
- 실제 PostgreSQL에서 돈다.
- 세션 시작 시 downgrade base → upgrade head를 한다.
- 테스트마다 savepoint 롤백을 한다.

**새 fixture**
- `library_a`(internal), `library_b`(imported)
- 기관별 `admin_client`, `kiosk_client` (토큰을 헤더에 넣은 httpx 클라이언트)

**폴더**: `tests/{library,catalog,circulation,platform}/`

**모든 기관 데이터 API에 기관 분리 테스트를 둔다** (CLAUDE.md 코딩 규칙).
- 다른 기관의 id로 단건 조회·수정·삭제하면 404
- 목록에 다른 기관 데이터가 없음

**스펙 추적**: 테스트 docstring에 `[capability] 요구사항 / 시나리오`를 적는다 (1주차 방식 유지).

## Risks / Trade-offs

- **[도서가 기관 공통이라 한 기관 관리자의 수정이 다른 기관에도 보임]** 특히 어린이/일반 구분이 그렇다.
  - 1주차에는 받아들인다.
  - 2주차 어린이 자동 분류에서 "기관별 지정 값"을 둘지 정한다. 그 전까지 도서 수정은 관리자만 할 수 있다.
- **[키오스크 대출에 본인 확인이 없음]** 다른 사람의 회원번호를 알면 그 이름으로 빌릴 수 있다.
  - 작은도서관 MVP에서는 받아들인다. 비밀번호·PIN은 최소 정보 원칙과 맞지 않고, 대출 기록은 관리자가 볼 수 있다.
  - 실제 문제가 되면 회원별 간단한 확인 수단을 그때 검토한다.
- **[매입 사본은 ISBN 필수라 잡지(ISSN)를 매입으로 등록할 수 없음]** 정기간행물은 2주차 가져오기에서 실제 데이터를 보고 다시 정한다.
- **[키오스크 토큰이 30일 유효]** 공용 PC에서 토큰이 새면 오래 쓰일 수 있다.
  - 키오스크는 조회와 대출만 할 수 있다.
  - 관리자가 계정을 사용 중지하면 즉시 끊긴다.
  - 이용자 화면 쪽 보호(입력 없으면 대화 초기화 등)는 7주차 UI에서 다룬다.
- **[scrypt 파라미터가 로그인 응답 시간에 영향]** n=2^14면 해시 한 번에 수십 ms 수준이다.
  - 테스트에서 계정을 많이 만들면 느려지므로, 테스트 설정에서만 n을 낮출 수 있게 한다.
- **[마이그레이션 재작성으로 로컬 DB를 수동으로 내려야 함]** 태스크 첫 단계에 넣고 README에도 적는다.
  - 잊고 진행해서 리비전을 찾지 못하면 `docker compose down -v`로 처음부터 만든다.
- **[날짜가 실행일 기준인 시드]** 같은 seed라도 날짜는 실행일마다 다르다. 스펙의 "같은 데이터"는 날짜를 뺀 내용으로 해석하고, 테스트도 그 기준으로 비교한다.

## Migration Plan

1. 로컬 개발 DB와 테스트 DB를 `uv run alembic downgrade base`로 내린다. 이전 리비전 파일이 있을 때 해야 한다.
2. 이전 리비전 파일과 이전 도메인 코드를 지운다.
3. 새 모델로 초기 리비전을 autogenerate하고 검토한 뒤 `alembic upgrade head`를 실행한다.
4. 시드를 실행한다.

되돌리기는 `alembic downgrade base`다. 운영 데이터가 없으므로 이전 데이터 이전은 하지 않는다.
