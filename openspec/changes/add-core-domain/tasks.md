# Tasks

## 1. 프로젝트와 로컬 DB 준비

- [ ] 1.1 `uv init`으로 Python 3.12 프로젝트를 만들고 런타임 의존성(fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, faker)과 dev 의존성(pytest, pytest-asyncio, httpx, ruff)을 추가한다. `uv sync`가 성공하는지 확인한다
- [ ] 1.2 `pyproject.toml`에 ruff(line-length, import 정렬)와 pytest(`asyncio_mode = "auto"`, testpaths) 설정을 추가하고 `uv run ruff check .`이 통과하는지 확인한다
- [ ] 1.3 `docker-compose.yml`(postgres:16, 볼륨, healthcheck)과 테스트 DB를 만드는 `docker/postgres/init/01-create-test-db.sql`을 작성한다. `docker compose up -d db` 후 `chaekbang`, `chaekbang_test` DB가 둘 다 있는지 `psql`로 확인한다
- [ ] 1.4 `.env.example`(`DATABASE_URL`, `TEST_DATABASE_URL`)과 `.gitignore`(`.env`, `.venv`, `__pycache__`)를 추가한다
- [ ] 1.5 `app/core/config.py`(Settings), `app/core/db.py`(engine, `get_session`), `app/main.py`(FastAPI 앱, 도메인 예외 → 404/409 핸들러)와 `app/services/errors.py`를 만든다. `uv run uvicorn app.main:app`이 뜨고 `/docs`가 열리는지 확인한다

## 2. 컨텍스트별 모델과 마이그레이션

- [ ] 2.1 `app/models/base.py`에 공통 `Base`와 created_at/updated_at mixin을 만들고, `app/models/__init__.py`가 네 컨텍스트 모듈을 import하게 한다
- [ ] 2.2 `app/models/catalog.py`에 Book, StoreInventory를 PK·CHECK(ISBN 정규식, 정가 >= 0, 수량 >= 0)·FK RESTRICT와 함께 작성한다
- [ ] 2.3 `app/models/storefront.py`에 ChatLog, OwnerMessage, BookRequest와 상태 StrEnum을 design.md 5·6번 표대로 작성한다
- [ ] 2.4 `app/models/owner_ops.py`에 Curation, Quote(글귀)와 StrEnum을 작성한다
- [ ] 2.5 `app/models/supply.py`에 Institution, InstitutionOrder, OrderItem, QuoteDraft(견적서)와 StrEnum을 작성한다 (quotes/quote_drafts docstring에 글귀/견적서 구분 명시)
- [ ] 2.6 Alembic을 async 템플릿으로 초기화하고 `env.py`를 Settings·`Base.metadata`에 연결한다. 초기 리비전을 autogenerate한 뒤 CHECK 제약과 server default가 들어갔는지 검토한다. `uv run alembic upgrade head`가 dev DB에 성공하는지 확인한다
- [ ] 2.7 `tests/conftest.py`에 테스트 DB 마이그레이션 적용, 테스트별 savepoint 롤백 세션, `get_session` override한 `httpx.AsyncClient` fixture를 만든다. DB에 연결할 수 없으면 안내 메시지와 함께 실패하게 한다
- [ ] 2.8 `tests/platform/test_database_schema.py`에 platform/database-schema 시나리오(컨텍스트별 테이블 소유, 외래 키 방향, 빈 DB upgrade 11개 테이블, downgrade 후 재적용, autogenerate diff 없음)를 테스트로 작성하고 통과시킨다
- [ ] 2.9 `tests/platform/test_boundaries.py`에 AST 기반 import 경계 검사(catalog는 다른 컨텍스트를 import하지 않음, storefront·owner_ops·supply는 서로의 models·services를 import하지 않음)를 작성하고 통과시킨다
- [ ] 2.10 `tests/storefront/test_schema.py`, `tests/owner_ops/test_schema.py`, `tests/supply/test_schema.py`에 storefront/customer-interactions, owner-ops/curation-content, supply/order-lists, supply/quote-drafts의 저장 제약 시나리오를 DB 직접 쓰기 테스트로 작성하고 통과시킨다

## 3. catalog: 도서 (catalog/books)

- [ ] 3.1 `app/matching/isbn.py`에 ISBN 정규화·체크 디지트 검증 함수를 만들고 `tests/matching/test_isbn.py`로 하이픈 제거, 자릿수 오류, 체크 디지트 오류를 검증한다
- [ ] 3.2 `app/schemas/common.py`(`Page[T]`)와 `app/schemas/catalog.py`의 BookCreate, BookUpdate, BookRead를 작성한다. ISBN 필드는 3.1 함수를 validator로 쓰고 정가는 `int >= 0`
- [ ] 3.3 `app/services/catalog/books.py`에 create/get/list/update/delete를 작성한다 (중복 ISBN → ConflictError, 재고 참조 → 사전 확인 ConflictError, 다른 컨텍스트 참조 → IntegrityError를 ConflictError로 변환). `tests/catalog/test_books_service.py`로 검증한다
- [ ] 3.4 `app/api/catalog.py`에 `/books` 라우터를 작성하고 경로의 ISBN도 정규화한다. `tests/catalog/test_books_api.py`에 catalog/books의 API 시나리오(등록, 필수 필드 누락, 정가 오류, 하이픈 입력·조회, 자릿수·체크 디지트 오류, 중복 409, 단건·404, 페이지네이션, limit 상한, 부분 수정·404, 삭제 204, 재고 참조 409, 다른 컨텍스트 참조 409)를 작성하고 통과시킨다
- [ ] 3.5 `tests/catalog/test_schema.py`에 catalog/books 저장 제약 시나리오(잘못된 ISBN·음수 정가 직접 저장, 참조된 도서 직접 삭제)를 작성하고 통과시킨다

## 4. catalog: 매장 재고 (catalog/store-inventory)

- [ ] 4.1 `app/schemas/catalog.py`에 InventoryCreate, InventoryUpdate, InventoryRead(도서 제목·저자 포함)를 추가한다
- [ ] 4.2 `app/services/catalog/inventory.py`에 create/get/list(in_stock 필터)/update/delete를 작성한다 (없는 도서 → NotFoundError, 중복 → ConflictError). `tests/catalog/test_inventory_service.py`로 검증한다
- [ ] 4.3 `app/api/catalog.py`에 `/inventory` 라우터를 추가하고 `tests/catalog/test_inventory_api.py`에 catalog/store-inventory의 모든 시나리오(등록, 없는 ISBN 404, 중복 409, 음수 422, 단건·404, in_stock 필터, 수량 수정, 음수 수정 422, 삭제 후 재고 404·도서 200)를 작성하고 통과시킨다

## 5. supply: 기관 (supply/institutions)

- [ ] 5.1 `app/schemas/supply.py`에 InstitutionCreate, InstitutionUpdate, InstitutionRead를 작성한다. 기관명은 빈 문자열 불가, 유형은 StrEnum
- [ ] 5.2 `app/services/supply/institutions.py`에 create/get/list(type 필터)/update/delete를 작성한다 (주문 목록·견적서가 참조하면 ConflictError). `tests/supply/test_institutions_service.py`로 검증한다
- [ ] 5.3 `app/api/supply.py`에 `/institutions` 라우터를 작성하고 `tests/supply/test_institutions_api.py`에 supply/institutions의 모든 시나리오(등록, 잘못된 유형, 기관명 누락, 단건·404, 유형 필터, 담당자 수정, 삭제 204, 주문 목록 있을 때 409)를 작성하고 통과시킨다

## 6. 시드 데이터 (platform/dev-seed-data)

- [ ] 6.1 컨텍스트별 시드 함수를 작성한다: catalog(고정 seed 도서 50권, 재고 약 35건·수량 0~5), supply(기관 3곳: school, daycare, community_center). 이미 있는 데이터는 건너뛴다
- [ ] 6.2 시드 실행 전 확인 함수(DB 연결 5초 타임아웃, `alembic_version`과 head 비교)를 작성한다. 실패 시 데이터를 쓰지 않고 비밀번호 없는 한 줄 안내 메시지를 stderr로 출력하게 한다 (design.md 10번)
- [ ] 6.3 `scripts/seed.py` 진입점을 만들어 확인 → 시드(단일 트랜잭션) 순서로 실행하고, 실패 시 종료 코드 1, 성공 시 생성·건너뛴 건수 출력과 종료 코드 0을 내게 한다. dev DB에서 `uv run python scripts/seed.py; echo $?`로 확인하고, DB를 끈 상태에서도 실행해 안내 메시지와 종료 코드 1이 나오는지 확인한다
- [ ] 6.4 `tests/platform/test_seed.py`에 dev-seed-data 생성 시나리오(건수, 기관 유형 3가지, ISBN 체크 디지트·정가 규칙, 두 번 실행 시 건수 불변)를 작성하고 통과시킨다
- [ ] 6.5 `tests/platform/test_seed.py`에 실행 전제 조건 시나리오(마이그레이션 전 실행, 리비전 뒤처짐, DB 연결 불가 subprocess, 정상 실행 종료 코드 0)를 작성하고, 실패 케이스마다 데이터가 생기지 않았는지까지 확인해 통과시킨다

## 7. 문서와 최종 점검

- [ ] 7.1 `CLAUDE.md` 디렉터리 구조에 컨텍스트별 하위 구조(design.md 2번)와 경계 규칙 3가지(design.md 1번)를 추가한다
- [ ] 7.2 `README.md`에 로컬 실행 순서(DB 실행 → 마이그레이션 → 시드 → 서버 → 테스트)와 컨텍스트 구분 표를 쓰고, 빈 환경에서 그 순서대로 실행해 확인한다
- [ ] 7.3 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`이 모두 통과하는지 확인하고, 9개 capability의 각 시나리오가 최소 하나의 테스트 docstring에 연결돼 있는지 점검한다

## Workflow follow-up

- 사람이 결과를 확인한 뒤 `/opsx:archive`로 change를 archive해 `openspec/specs/`에 반영한다
