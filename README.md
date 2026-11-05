# chaekbang-agent

사서가 없는 작은도서관을 위한 AI 사서 웹 서비스의 백엔드. 도서관 PC에 켜 둔 화면에서 이용자는 AI 사서에게 추천을 받고 대출하며, 관리자는 운영 에이전트로 장서·대출 현황을 다룬다. 배경과 전체 설계는 [docs/design.md](docs/design.md), 코딩 규칙은 [CLAUDE.md](CLAUDE.md)를 참고한다.

현재 단계: 1주차 백엔드 기본 (기관 분리, 관리자·키오스크 인증, 도서·사본·회원·대출 API, 시드 데이터). 에이전트 기능은 아직 없다.

## 도메인

| 구분 | 테이블 | API |
| --- | --- | --- |
| 기관과 인증 | libraries, staff_users, staff_sessions | `/auth`, `/library`, `/staff` |
| 장서 | books(기관 공통), holdings(소장 사본) | `/books`, `/holdings` |
| 대출 | members, loans | `/members`, `/loans` |

- **기관 분리**: books·libraries를 뺀 모든 테이블은 `library_id`를 가진다. 기관은 로그인 토큰으로 정해지고, 다른 기관의 데이터는 404로 응답한다.
- **도서와 사본**: 도서는 내부 id로 식별하고 ISBN은 선택이다. 사본은 등록번호(`accession_number`), 청구기호(`call_number`), 입수 구분(매입·납품은 구입가와 ISBN 필수, 기증은 기증처 선택)을 가진다.
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
- 시드의 도서·ISBN·출판사·회원 이름은 Faker로 만든 데모용 가짜 데이터다. 체크 디지트는 맞지만 실제 도서와 우연히 겹칠 수 있다.

### 시드 데이터와 계정

| 기관 | 운영 방식 | 관리자 | 키오스크 |
| --- | --- | --- | --- |
| 햇살 작은도서관 | `internal` (대출 14일, 대출·연체 데이터 있음) | `sunny-admin` | `sunny-kiosk` |
| 푸른숲 작은도서관 | `imported` | `forest-admin` | `forest-kiosk` |

비밀번호는 `.env`의 `SEED_ADMIN_PASSWORD`, `SEED_KIOSK_PASSWORD`다 (`.env.example`의 개발용 값).

### 인증 사용법

1. `POST /auth/login`에 `{"login_id": "sunny-kiosk", "password": "..."}`를 보내 토큰을 받는다.
2. 이후 요청에 `Authorization: Bearer <토큰>` 헤더를 붙인다. Swagger에서는 오른쪽 위 **Authorize**에 토큰을 넣는다.
3. 키오스크(도서관 PC)는 기관 정보·도서·사본 조회와 대출·반납만 할 수 있다. 나머지는 관리자만 할 수 있고, 키오스크가 부르면 403이다.
4. 토큰 만료: 관리자 12시간, 키오스크 30일 (`ADMIN_TOKEN_HOURS`, `KIOSK_TOKEN_HOURS`). `POST /auth/logout`으로 끊고, 비밀번호를 바꾸면 그 계정의 기존 토큰이 모두 끊긴다.

### 이전 스키마(무인 서점)에서 넘어올 때

초기 마이그레이션을 새 도메인으로 다시 만들었다. 이전 리비전(`896d5140154e`)이 적용된 로컬 DB는 **이전 코드가 있는 커밋에서** 먼저 내린 뒤 새 코드로 올린다.

```bash
uv run alembic downgrade base
```

이미 새 코드로 바꿨다면 DB 볼륨을 지우고 다시 만드는 편이 간단하다 (`docker compose down -v` 후 `docker compose up -d db`). 로컬 데이터가 모두 지워진다.

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
