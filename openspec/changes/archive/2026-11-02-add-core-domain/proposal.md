# Proposal

## Why

A(매장 큐레이터), B(사장님 운영), C(기관 납품) 에이전트는 모두 같은 도메인 데이터(도서, 매장 재고, 기관, 승인 상태)를 읽고 쓴다. 에이전트를 만들기 전에 이 데이터를 담을 스키마와, REST API와 이후 에이전트 tool이 함께 쓸 service 계층의 기본 틀을 먼저 세워야 한다. 1주차는 그 바닥을 까는 단계다.

## What Changes

- uv 기반 Python 3.12 프로젝트 초기화 (FastAPI, SQLAlchemy 2.0 async, Alembic, pydantic-settings, ruff, pytest)
- `docker-compose.yml`로 로컬 PostgreSQL 실행 (개발 DB + 테스트 DB)
- `docs/design.md` 데이터 모델 중 MVP 테이블 11개를 세 에이전트에 맞춘 도메인 컨텍스트로 나눠 모델과 Alembic 초기 마이그레이션을 만든다
  - **catalog** (공유): books, store_inventory
  - **storefront** (A 매장 큐레이터): chat_logs, owner_messages, book_requests
  - **owner-ops** (B 사장님 운영): curations, quotes(글귀)
  - **supply** (C 기관 납품): institutions, institution_orders, order_items, quote_drafts(견적서)
  - 컨텍스트끼리는 catalog만 참조할 수 있고, A·B·C 테이블은 서로 직접 참조하지 않는다. 코드(models, services, api)도 같은 경계로 나눈다
- CRUD REST API 3종: books, store_inventory, institutions (라우터는 얇게, 로직은 services에)
- 시드 스크립트: 도서 50권, 그중 일부의 매장 재고, 기관 3곳
- `.env.example`, `README.md`에 로컬 실행 방법 정리

**범위 밖 (이번 change에서 하지 않음)**

- LLM 호출, tool 루프 등 에이전트 기능
- curations, quotes, chat_logs, owner_messages, book_requests, institution_orders, order_items, quote_drafts의 API (테이블만 만든다)
- 승인 흐름의 상태 전이 로직 (상태 값과 제약만 스키마에 둔다. 전이는 `add-approval-flow`에서)
- 외부 도서 API 연동, ISBN 매칭, 견적 계산
- 인증·권한

## Capabilities

### New Capabilities

스펙도 컨텍스트별 폴더로 나눈다.

- `platform/database-schema`: 컨텍스트별 테이블 소유, 컨텍스트 간 참조 방향, 마이그레이션 적용·되돌리기
- `platform/dev-seed-data`: 로컬 개발·데모용 더미 데이터 생성과 실행 전제 조건
- `catalog/books`: 도서 정보의 등록·조회·수정·삭제, ISBN 형식 규칙, 저장 제약
- `catalog/store-inventory`: 매장에 있는 도서의 수량과 서가 위치 관리
- `storefront/customer-interactions`: 손님 대화 기록, 사장님께 넘긴 문의, 주문 요청의 저장 규칙
- `owner-ops/curation-content`: 추천·추천 카드의 승인 상태, 사장님이 등록한 글귀
- `supply/institutions`: 납품 대상 기관의 등록·조회·수정·삭제
- `supply/order-lists`: 기관 도서 목록과 행별 원문·매칭 상태
- `supply/quote-drafts`: 견적서 초안의 승인 상태와 금액 형식

### Modified Capabilities

(없음. `openspec/specs/`가 비어 있는 첫 change다.)

## Impact

- 새 코드: `app/` (main, core, 그리고 api·services·models·schemas 아래 컨텍스트별 모듈), `migrations/`, `scripts/seed.py`, `tests/`
- `CLAUDE.md` 디렉터리 구조에 컨텍스트별 하위 구조와 경계 규칙을 추가한다
- 새 설정 파일: `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `alembic.ini`, `.env.example`
- 의존성: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, faker / dev: pytest, pytest-asyncio, httpx, ruff
- 로컬 실행에 Docker가 필요하다
