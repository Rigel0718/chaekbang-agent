# chaekbang-agent

작은 책방을 위한 AI 에이전트 백엔드. 매장 큐레이터(손님용), 사장님 운영, 기관 납품 세 에이전트가 같은 도메인 데이터를 나눠 쓴다. 배경과 전체 설계는 [docs/design.md](docs/design.md), 코딩 규칙은 [CLAUDE.md](CLAUDE.md)를 참고한다.

현재 단계: 1주차 백엔드 기본 (모델, 마이그레이션, 도서·재고·기관 CRUD API, 시드 데이터). 에이전트 기능은 아직 없다.

## 도메인 컨텍스트

| 컨텍스트 | 에이전트 | 테이블 | API |
| --- | --- | --- | --- |
| catalog | 공유 | books, store_inventory | `/books`, `/inventory` |
| storefront | A 매장 큐레이터 | chat_logs, owner_messages, book_requests | (이후 단계) |
| owner_ops | B 사장님 운영 | curations, quotes(글귀) | (이후 단계) |
| supply | C 기관 납품 | institutions, institution_orders, order_items, quote_drafts(견적서) | `/institutions` |

A·B·C 컨텍스트는 catalog만 참조하고 서로 직접 참조하지 않는다. 자세한 규칙은 CLAUDE.md의 "도메인 컨텍스트"를 본다.

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
- 시드는 여러 번 실행해도 중복되지 않는다 (이미 있는 ISBN·기관명은 건너뜀). 마이그레이션 전이거나 DB가 꺼져 있으면 안내 메시지와 함께 종료 코드 1로 끝난다.
- 시드의 도서·ISBN·출판사는 Faker로 만든 데모용 가짜 데이터다. 체크 디지트는 맞지만 실제 도서와 우연히 겹칠 수 있다.

## 테스트와 린트

테스트는 실제 PostgreSQL(`TEST_DATABASE_URL`)에서 돈다. DB 컨테이너가 떠 있어야 한다.

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

## 개발 흐름

기능 작업은 OpenSpec change 단위로 한다 (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`). 규칙은 CLAUDE.md의 "OpenSpec 작업 규칙"을 따른다.
