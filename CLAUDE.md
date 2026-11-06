# CLAUDE.md

## 프로젝트 개요

사서가 없는 작은도서관을 위한 AI 사서 웹 서비스. 도서관 PC 브라우저에 로그인해 켜 두면 이용자는 AI 사서에게 추천·큐레이션을 받고 대출하며, 관리자는 운영 에이전트로 장서·대출 현황을 분석하고 초안을 승인한다.

- **이용자 화면 – AI 사서 에이전트**: 소장 도서 검색, 추천, 큐레이션, 대출, 희망도서 신청
- **관리자 화면 – 운영 에이전트**: 자연어 SQL 분석, 장서 가져오기·등록, 큐레이션·연체 안내·보충 구매 요청서 초안. 확정은 모두 승인 후

MVP 대상은 작은도서관이다. 독립서점은 2단계 '모드'(대출 대신 서가 안내·구매 문의)로 추가한다. 이 프로젝트의 핵심 성과 지표는 **추천 품질**이다.

포지션은 '기존 시스템 위에 얹는 AI 사서'다. 장서는 기관이 이미 쓰는 대출 프로그램의 엑셀·CSV 내보내기를 가져오는 것이 기본이고, 자체 대출은 대출 프로그램이 없는 기관과 데모용이다.

자세한 설계는 `docs/design.md`를 참고한다. 설계와 다르게 구현해야 할 이유가 생기면 먼저 물어본다.

## 현재 단계

**2주차: 장서 가져오기** (OpenSpec change: `add-holdings-import`).
기존 대출 프로그램의 엑셀·CSV 가져오기, 제적, 입수 구분 `unknown`, 파일 근거 어린이 도서 분류, 가져오기 평가.
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

**MVP change 순서** (8주)

1. `add-library-core-domain` – 이전 도메인 정리, 모델, 기관 분리, 인증, 장서·대출 CRUD, 시드 데이터
2. `add-holdings-import` – 기존 시스템 엑셀·CSV 장서 가져오기, 파일 근거 어린이 도서 분류
3. `add-book-enrichment` – YES24 연동, 서지정보 채움, 외부 분류 근거
4. `add-librarian-agent` – AI 사서 v1, 조회 tool, tool calling 루프, 스트리밍, 추천 노출 기록
5. `add-recommendation-evals` – 평가 세트, 규칙 검사, LLM 채점, 임베딩 검색 비교
6. `add-admin-agent` – 운영 에이전트, 자연어 SQL 분석과 안전장치, 장서 등록
7. `add-approval-flow` – 초안 → 승인 → 실행, 서버 재시작 후에도 재개
8. `add-web-ui` – 이용자·관리자 화면
9. `add-observability-deploy` – Langfuse, 배포, README, 데모

**스펙 작성 규칙**

- change id는 동사로 시작하는 kebab-case로 짓는다. 이미 archive된 id(`add-core-domain`)는 다시 쓰지 않는다.
- 요구사항은 SHALL/MUST로 쓰고, 요구사항마다 시나리오를 최소 1개 둔다 (WHEN … THEN …).
- **시나리오 하나 = 테스트 하나 이상.** 테스트 이름이나 docstring에 해당 요구사항을 적어 추적할 수 있게 한다.
- 에이전트 동작에 대한 시나리오(예: "어린이 추천 요청에는 어린이 도서로 분류된 소장 도서만 추천한다")는 pytest 대신 `evals/` 시나리오로 만든다.
- change 하나는 1주 이내 분량으로 작게 유지한다. 커지면 나눈다.
- 스펙 본문은 한국어로 쓰되, 요구사항 키워드(SHALL, MUST, WHEN, THEN)와 change id는 영어로 쓴다.

**하지 말 것**

- change 없이 기능 코드를 추가하지 않는다. 오타 수정, 리팩터링, 의존성 업데이트는 예외.
- 구현 중에 스펙과 다르게 만들어야 하면 코드부터 바꾸지 말고, 스펙 delta를 먼저 고친 뒤 알린다.
- 진행 중인 change를 동시에 여러 개 열지 않는다.

## 기술 스택

- Python 3.12, FastAPI, Pydantic v2
- PostgreSQL (+ pgvector), SQLAlchemy 2.0 (async), Alembic
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
├── core/         # config(설정), db(세션), security(비밀번호·토큰), deps(현재 직원·기관, 역할),
│                 # clock(기관 시간대 오늘), isbn(정규화·검증), migrations
├── api/          # 라우터: auth, library, staff, books, holdings, members, loans (이후 curations, requests ...)
├── services/     # 비즈니스 로직 (REST API와 에이전트 tool이 함께 사용). tenancy.get_owned로 기관 범위 강제
├── models/       # SQLAlchemy 모델: library(기관·직원·세션), catalog(도서·사본), circulation(회원·대출)
├── schemas/      # Pydantic 스키마
├── seed/         # 시드 데이터 생성 (scripts/seed.py가 실행)
├── importing/    # (2주차) 장서 가져오기: 엑셀·CSV 파싱, 머리글 인식, ISBN 정규화, 어린이 도서 분류
├── external/     # (이후 단계) 외부 API: yes24(엔드포인트·필드 정의를 한곳에), 도서관 정보나루
├── agents/       # (이후 단계)
│   ├── librarian/    # 이용자용 AI 사서: tool, 프롬프트
│   ├── admin/        # 관리자용 운영 에이전트: tool, 프롬프트, sql_guard
│   └── runtime/      # tool calling 루프, 승인 대기·재개, 실행 기록
└── recommendation/   # (이후 단계) 후보 검색(키워드·임베딩), 규칙 필터(소장·어린이 도서)
migrations/       # Alembic
scripts/seed.py   # 더미 데이터 (Faker)
evals/            # (이후 단계) 추천·장서 가져오기·에이전트 평가 시나리오와 채점
tests/
docs/design.md
openspec/
├── specs/        # 기능별 현재 스펙 (archive된 change가 여기에 반영됨)
└── changes/      # 진행 중인 change
```

## 설계 원칙 (반드시 지킬 것)

1. **라우터는 얇게, 로직은 services에.** REST API와 에이전트 tool이 같은 service 함수를 호출한다. 라우터에 비즈니스 로직을 넣지 않는다.
2. **기관 데이터는 항상 분리한다.** 모든 기관 데이터는 `library_id`로 나눈다. 조회·쓰기·에이전트 tool·자연어 SQL 모두 현재 로그인한 기관 범위를 코드에서 강제한다. 요청 값으로 받은 library_id를 그대로 믿지 않는다.
3. **확정 작업은 승인 흐름을 거친다.** 큐레이션 게시, 연체 안내, 구매 요청서 확정은 `draft → pending_approval → approved → (published | confirmed)` 상태를 따른다. 승인 대기 상태는 DB에 저장한다. 이용자 쪽 쓰기는 대출·반납과 희망도서 신청만 허용한다.
4. **소장 도서만 추천한다.** 추천 결과는 항상 해당 기관의 holdings에 있는 책이다. 대출 중이면 표시하고, 없으면 희망도서 신청으로 연결한다. 어린이 요청에는 어린이 도서(`audience = children`)로 분류된 책만 추천하고, 분류가 확실하지 않은 책은 일반 도서로 둔다. 이 규칙은 LLM이 아니라 코드(필터)로 강제한다.
5. **기존 시스템 위에 얹는다.** 장서는 기존 대출 프로그램에서 가져오는 것을 기본으로 하고, 담당자가 같은 정보를 두 번 입력하게 만들지 않는다. 가져오기 기관(`loan_mode = imported`)에서는 대출 쓰기 tool을 끄고, 대출 상태에는 마지막 갱신 시각을 함께 보여 준다.
6. **책 정보는 데이터로만 답한다.** 줄거리·저자 정보는 DB나 외부 API 결과를 근거로 하고, LLM이 인용문이나 정보를 지어내지 않게 한다.
7. **LLM이 할 일과 코드가 할 일을 나눈다.** 금액 계산, 권차 변환, 텍스트·ISBN 정규화, 어린이 도서 분류, 소장 필터는 결정적인 코드로 처리한다. LLM은 의도 파악, 후보 선택과 설명, 애매한 매칭 판단에 쓴다.
8. **개인정보는 최소한으로.** 이용자 대화에서 이름·연락처를 묻지 않고, 대화 기록에 개인정보를 남기지 않는다. 회원번호는 대출과 희망도서 신청에만 쓴다.

## 코딩 규칙

- 모든 DB 접근은 async. 세션은 의존성 주입(`Depends`)으로 받는다.
- 요청·응답은 항상 Pydantic 스키마로 정의한다. ORM 모델을 그대로 반환하지 않는다.
- 금액은 `int`(원 단위)로 다룬다. float 금지.
- ISBN은 하이픈 없는 13자리 문자열로 저장한다.
- 상태 값은 `StrEnum`으로 정의한다.
- 외부 API 키, DB URL은 `.env`에서 읽고 코드에 하드코딩하지 않는다. `.env.example`을 함께 관리한다.
- 외부 도서 API의 표지 이미지는 저장하지 않고 원본 URL로만 표시하며, 출처를 함께 보여준다.
- 새 service 함수에는 테스트를 같이 작성한다. 기관 분리(다른 기관 데이터가 보이지 않는지) 테스트를 빠뜨리지 않는다.

## 도메인 용어

- **작은도서관**: 주민센터·아파트 등에 있는 소규모 도서관. 전담 사서가 없고 담당자나 자원봉사자가 운영하는 경우가 많다.
- **장서 / 소장 사본(holding)**: 같은 책(book)이라도 여러 권을 가질 수 있다. 대출은 사본 단위로 한다.
- **등록번호(accession number)**: 도서관이 사본마다 붙이는 고유 번호. 장서 가져오기에서 사본을 식별하는 기준이다. 필드 이름은 `accession_number`.
- **청구기호(call number)**: 서가에서 책을 찾는 주소(분류기호·저자기호·권차, 예: `813.7-한232ㅊ`). 같은 책의 복본은 같은 값일 수 있다. 사본 식별에는 쓰지 않는다. 필드 이름은 `call_number`.
- **입수 구분(acquisition type)**: 사본이 들어온 경로. `purchased`(매입·공식 납품, 구입가와 ISBN 필수), `donated`(기증, 기증처만 선택으로 기록), `unknown`(가져온 파일에 정보가 없음)이다. 가져온 매입 사본은 구입가나 ISBN이 없어도 오류가 아니라 빠진 정보(`missing_fields`)로 표기한다. 같은 책이라도 사본마다 다를 수 있어 사본에 둔다. 필드 이름은 `acquisition_type`, `purchase_price`, `donor`.
- **제적(withdrawn)**: 장서에서 빠진 사본. 가져온 파일에서 사라지면 이 상태가 되고, 추천·소장 권수에서 빠지며 대출 기록은 남는다.
- **회원번호(member number)**: 기관이 이용자에게 붙이는 번호. 대출과 희망도서 신청에만 쓴다. 필드 이름은 `member_number`.
- **운영 방식(loan_mode)**: `imported`는 기존 대출 프로그램의 내보내기를 가져와 쓰는 기관, `internal`은 AI 사서가 대출까지 처리하는 기관.
- **어린이 도서(audience)**: 책을 `children`(어린이 도서)과 `general`(일반 도서)로만 나눈다. 나이를 세밀하게 나누지 않는다. 근거(관리자 지정, 별치기호·자료실·부가기호, 외부 API 분류)를 함께 저장한다.
- **별치기호**: 일반 자료와 따로 배가하는 자료에 붙이는 기호. 아동 자료 표시가 어린이 도서 분류 근거가 된다.
- **희망도서**: 이용자가 도서관에 구입을 요청한 책.
- **보충 구매 요청서**: 관리자가 납품처(동네 책방)에 보낼 구매 목록. 금액은 코드로 계산한다.
- **권차 / 판본**: 시리즈 순서 표기("2권", "Ⅱ", "하")와 개정판·리커버 같은 판본 차이. 장서 등록 시 정규화 대상이다.

## 하지 말 것

- 결제, POS 연동, MARC 편목은 만들지 않는다 (범위 밖).
- 본격 대출 관리(예약, 연장, 연체료, 상호대차)는 만들지 않는다. 빌림·반납·대출 중 표시까지만.
- 기존 대출 프로그램과의 실시간 연동(API 동기화)은 만들지 않는다. 파일 가져오기까지만.
- 독립서점 모드, 시즌·이벤트 큐레이션, 개인화 추천, 세밀한 연령 구분은 아직 만들지 않는다 (2단계).
- 요청받지 않은 범위까지 한 번에 구현하지 않는다. change의 tasks가 끝나면 무엇을 했는지 요약하고 멈춘다.
