# CLAUDE.md

## 프로젝트 개요

작은 책방을 위한 AI 에이전트 백엔드. 사장님이 배달로 자리를 비워도 매장이 돌아가고, 실제 매출원인 기관 도서 납품 업무를 돕는 것이 목표다.

- **A. 매장 큐레이터 에이전트 (손님용)**: 도서 검색, 작가 정보, 오늘의 추천과 글귀, 주문 요청
- **B. 사장님 운영 에이전트 (관리자용)**: 신간 큐레이션, 추천 카드 초안, 손님 질문 요약. 모두 승인 후 게시
- **C. 기관 납품 에이전트**: 도서 목록 업로드 → ISBN 매칭 → 애매한 건 확인 요청 → 견적서 초안

자세한 설계는 `docs/design.md`를 참고한다. 설계와 다르게 구현해야 할 이유가 생기면 먼저 물어본다.

## 현재 단계

**1주차: 백엔드 기본** (OpenSpec change: `add-core-domain`).
모델, CRUD API, Alembic 마이그레이션, 시드 데이터, Docker Compose.
에이전트(LLM 호출, tool 루프)는 아직 만들지 않는다.

## OpenSpec 작업 규칙

이 프로젝트는 OpenSpec으로 스펙 기반 개발(SDD)을 한다. 모든 기능 작업은 change 단위로 진행한다.

**문서 역할**

| 위치 | 역할 |
| --- | --- |
| `docs/design.md` | 왜 만드는지, 전체 그림. 배경 참고용이며 요구사항의 기준은 아니다 |
| `CLAUDE.md` | 코딩 규칙과 설계 원칙. 모든 change에 적용된다 |
| `openspec/specs/` | 기능별 요구사항. 현재 시스템이 실제로 하는 일의 기준(source of truth) |
| `openspec/changes/<change-id>/` | 진행 중인 변경 하나: proposal, 스펙 변경분(delta), design, tasks |

**진행 순서** (Claude Code 명령: `/opsx:propose` → `/opsx:apply` → `/opsx:archive`, 아이디어 정리는 `/opsx:explore`)

1. **제안**: 새 기능은 코드를 쓰기 전에 change를 만든다. proposal(왜, 무엇을), 스펙 delta(요구사항 + 시나리오), tasks를 작성한다. 기술 결정이 있으면 design도 쓴다.
2. **검토 후 멈춤**: change를 만든 뒤 `openspec validate`로 형식을 확인하고, **사람이 승인할 때까지 구현을 시작하지 않는다.**
3. **구현**: tasks.md 순서대로 구현하고, 끝난 태스크는 바로 체크한다. 태스크에 없는 작업이 필요하면 먼저 tasks.md에 추가하고 알린다.
4. **검증**: 모든 시나리오가 테스트로 확인되는지 점검한다. 테스트와 린트가 통과해야 완료다.
5. **archive**: 사람이 확인한 뒤 change를 archive해서 `openspec/specs/`에 반영한다.

**스펙 작성 규칙**

- change id는 동사로 시작하는 kebab-case로 짓는다. 예: `add-core-domain`, `add-store-curator-agent`, `add-approval-flow`, `add-institution-order-matching`, `add-observability-evals`
- 요구사항은 SHALL/MUST로 쓰고, 요구사항마다 시나리오를 최소 1개 둔다 (WHEN … THEN …).
- **시나리오 하나 = 테스트 하나 이상.** 테스트 이름이나 docstring에 해당 요구사항을 적어 추적할 수 있게 한다.
- 에이전트 동작에 대한 시나리오(예: "추천 요청 시 매장 재고를 먼저 조회한다")는 pytest 대신 `evals/` 시나리오로 만든다.
- change 하나는 1주 이내 분량으로 작게 유지한다. 커지면 나눈다.
- 스펙 본문은 한국어로 쓰되, 요구사항 키워드(SHALL, MUST, WHEN, THEN)와 change id는 영어로 쓴다.

**하지 말 것**

- change 없이 기능 코드를 추가하지 않는다. 오타 수정, 리팩터링, 의존성 업데이트는 예외.
- 구현 중에 스펙과 다르게 만들어야 하면 코드부터 바꾸지 말고, 스펙 delta를 먼저 고친 뒤 알린다.
- 진행 중인 change를 동시에 여러 개 열지 않는다.

## 기술 스택

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL, SQLAlchemy 2.0 (async), Alembic
- 패키지 관리: uv / 린트·포맷: ruff / 테스트: pytest, pytest-asyncio, httpx
- 로컬 실행: Docker Compose
- (이후 단계) Langfuse 트레이싱, sqlglot

## 자주 쓰는 명령

```bash
docker compose up -d db                      # DB 실행
uv run alembic upgrade head                  # 마이그레이션 적용
uv run alembic revision --autogenerate -m "" # 마이그레이션 생성
uv run python scripts/seed.py                # 시드 데이터
uv run uvicorn app.main:app --reload         # 서버 (Swagger: /docs)
uv run pytest                                # 테스트
uv run ruff check . && uv run ruff format .  # 린트·포맷
```

## 디렉터리 구조

```
app/
├── main.py
├── core/         # 설정(pydantic-settings), DB 세션
├── api/          # 라우터: books, inventory, curations, quotes, institutions, orders ...
├── services/     # 비즈니스 로직 (REST API와 에이전트 tool이 함께 사용)
├── models/       # SQLAlchemy 모델
├── schemas/      # Pydantic 스키마
├── agent/        # (이후 단계) tool calling 루프, tool 정의, 프롬프트
├── matching/     # (C) 제목·작가·권차 정규화, ISBN 매칭
└── pricing/      # (C) 견적·할인 계산
migrations/       # Alembic
scripts/seed.py   # 더미 데이터 (Faker)
evals/            # (이후 단계) 에이전트 평가 시나리오
tests/
docs/design.md
openspec/
├── specs/        # 기능별 현재 스펙 (archive된 change가 여기에 반영됨)
└── changes/      # 진행 중인 change
```

## 설계 원칙 (반드시 지킬 것)

1. **라우터는 얇게, 로직은 services에.** REST API와 에이전트 tool이 같은 service 함수를 호출한다. 라우터에 비즈니스 로직을 넣지 않는다.
2. **쓰기 작업은 승인 흐름을 거친다.** 게시·발주·견적 확정처럼 밖으로 나가는 작업은 `draft → pending_approval → approved → (published | sent)` 상태를 따른다. 승인 대기 상태는 DB에 저장한다.
3. **LLM이 할 일과 코드가 할 일을 나눈다.** 금액·할인 계산, 권차 변환("Ⅱ", "2권", "하" → 숫자), 텍스트 정규화는 결정적인 코드로 처리한다. LLM은 "두 책이 같은 책인가" 같은 애매한 판단에만 쓴다.
4. **책 정보는 데이터로만 답한다.** 줄거리·작가 정보는 DB나 외부 API 결과를 근거로 한다. 글귀는 사장님이 등록한 것만 쓰고, LLM이 인용문을 지어내지 않게 한다.
5. **매장 재고를 먼저.** 추천과 검색은 `store_inventory`를 먼저 조회하고, 없을 때 외부 검색으로 넘어간다.

## 코딩 규칙

- 모든 DB 접근은 async. 세션은 의존성 주입(`Depends`)으로 받는다.
- 요청·응답은 항상 Pydantic 스키마로 정의한다. ORM 모델을 그대로 반환하지 않는다.
- 금액은 `int`(원 단위)로 다룬다. float 금지.
- ISBN은 하이픈 없는 13자리 문자열로 저장한다.
- 상태 값은 `StrEnum`으로 정의한다.
- 외부 API 키, DB URL은 `.env`에서 읽고 코드에 하드코딩하지 않는다. `.env.example`을 함께 관리한다.
- 새 service 함수에는 테스트를 같이 작성한다.

## 도메인 용어

- **기관 납품**: 학교·어린이집·동사무소·군 서점에 도서를 공급하는 일. 이 책방의 주 수입원이다.
- **권차**: 1권, 2권 같은 시리즈 순서. 출판사마다 표기가 다르다("2권", "Ⅱ", "II", "제2권", "상/하").
- **개정판 / 리커버 / 신장판 / 재출간**: 같은 작품의 다른 판본. 대개 ISBN이 다르다.
- **재정가**: 발행 12개월 이후 정가를 바꾸는 것. ISBN은 같고 가격만 바뀐다.
- **도서정가제**: 가격 할인 최대 10% + 적립 등 간접 할인 5%. 회원 적립은 2%다.

## 하지 말 것

- 회원 가입, 결제, POS 연동은 만들지 않는다 (범위 밖).
- 이벤트·시즌 알림은 아직 만들지 않는다 (나중에 추가할 기능).
- 요청받지 않은 범위까지 한 번에 구현하지 않는다. change의 tasks가 끝나면 무엇을 했는지 요약하고 멈춘다.