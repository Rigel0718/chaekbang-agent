# CLAUDE.md

## 프로젝트 개요

사서가 없는 작은도서관을 위한 AI 사서 웹 서비스. 도서관 PC 브라우저에 로그인해 켜 두면 이용자는 AI 사서에게 추천·큐레이션을 받고 대출하며, 관리자는 운영 에이전트로 장서·대출 현황을 분석하고 초안을 승인한다.

- **이용자 화면 – AI 사서 에이전트**: 소장 도서 검색, 추천, 큐레이션, 대출, 희망도서 신청
- **관리자 화면 – 운영 에이전트**: 자연어 SQL 분석, 장서 가져오기·등록, 큐레이션·연체 안내·보충 구매 요청서 초안. 확정은 모두 승인 후

MVP 대상은 작은도서관이다. 독립서점은 2단계 '모드'(대출 대신 서가 안내·구매 문의)로 추가한다. 이 프로젝트의 핵심 성과 지표는 **추천 품질**이다.

포지션은 '기존 시스템 위에 얹는 AI 사서'다. 장서는 기관이 이미 쓰는 대출 프로그램의 엑셀·CSV 내보내기를 가져오는 것이 기본이고, 자체 대출은 대출 프로그램이 없는 기관과 데모용이다.

자세한 설계는 `docs/design.md`(전체 그림)와 그 문서가 가리키는 주제별 문서를 참고한다. 설계와 다르게 구현해야 할 이유가 생기면 먼저 물어본다.

## 현재 단계

<!-- 이 절은 세 줄까지만. 결정·수치·미룬 일은 docs/roadmap.md에 쓴다. -->
진행 중: 없음(직전 `add-admin-agent` archive 끝) · 다음: `add-approval-flow`
change 순서와 상태, 확정된 기본값(임베딩 텍스트, 주제로 찾기, 비슷한 책, 최근 기록), 미룬 일은 `docs/roadmap.md`에 있다.

## OpenSpec 작업 규칙

이 프로젝트는 OpenSpec으로 스펙 기반 개발(SDD)을 한다. 모든 기능 작업은 change 단위로 진행한다.

**문서 역할**

| 위치 | 역할 |
| --- | --- |
| `docs/design.md` | 왜 만드는지, 전체 그림. 배경 참고용이며 요구사항의 기준은 아니다. 주제별 문서(`recommendation`, `data-sources`, `roadmap`, `backlog`, `glossary`)는 같은 `docs/`에 있다 |
| `app/*/README.md` | 패키지별 역할과 규칙. 패키지 파일을 다루면 그 패키지의 `CLAUDE.md`(`@README.md` 한 줄)가 불러온다. 새 패키지에 README를 두면 같은 `CLAUDE.md`도 둔다 |
| `api-guides/` | 외부 API 문서. YES24(`yes24-open-api-guide/`), 도서관 정보나루(`data4library.md` 원본, `data4library_project.md` 이 프로젝트에 쓰는 부분, `data4library_ideas.md` 확장 아이디어), 카카오 책 검색(`kakao_search_api_guide.md`). 문서와 실제 응답이 다른 곳이 있어 새 필드는 실제 응답으로 확인한다 |
| `CLAUDE.md` | 코딩 규칙과 설계 원칙. 모든 change에 적용된다 |
| `openspec/specs/` | 기능별 요구사항. 현재 시스템이 실제로 하는 일의 기준(source of truth) |
| `openspec/changes/<change-id>/` | 진행 중인 변경 하나: proposal, 스펙 변경분(delta), design, tasks |

**진행 순서** (Claude Code 명령: `/opsx:propose` → `/opsx:apply` → `/opsx:archive`, 아이디어 정리는 `/opsx:explore`)

1. **제안**: 새 기능은 코드를 쓰기 전에 change를 만든다. proposal(왜, 무엇을), 스펙 delta(요구사항 + 시나리오), tasks를 작성한다. 기술 결정이 있으면 design도 쓴다.
2. **검토 후 멈춤**: change를 만든 뒤 `openspec validate`로 형식을 확인하고, **사람이 승인할 때까지 구현을 시작하지 않는다.**
3. **구현**: tasks.md 순서대로 구현하고, 끝난 태스크는 바로 체크한다. 태스크에 없는 작업이 필요하면 먼저 tasks.md에 추가하고 알린다.
4. **검증**: 모든 시나리오가 테스트로 확인되는지 점검한다. 테스트와 린트가 통과해야 완료다.
5. **archive**: 사람이 확인한 뒤 change를 archive해서 `openspec/specs/`에 반영한다.

**change 순서**는 `docs/roadmap.md`에 있다. archive할 때 그 문서의 상태와 확정된 기본값을 고친다.

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
- PostgreSQL 16 (+ fuzzystrmatch, pgvector. 이미지 `pgvector/pgvector`), SQLAlchemy 2.0 (async), Alembic
- 임베딩: 로컬 Text Embeddings Inference(TEI) 컨테이너, 기본 모델 `dragonkue/snowflake-arctic-embed-l-v2.0-ko`(1024차원, 입력 512토큰). 서버는 같은 가중치의 ONNX 변환본(`TEI_MODEL_ID`)으로만, ONNX 실행기로 띄운다. 다른 모델은 먼저 ONNX로 변환한다. 앱에는 torch를 넣지 않고 `httpx`로 부른다
- 패키지 관리: uv / 린트·포맷: ruff / 테스트: pytest, pytest-asyncio, httpx
- 로컬 실행: Docker Compose
- LLM: OpenAI Responses API (기본 `gpt-6-luna`, 모델별 가격은 `app/core/config.py`의 `LLM_PRICES`)
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
uv run python scripts/enrich_books.py        # 운영자: 공식 서지 채움, 정보나루·카카오·YES24 세 키 필요 (--limit, --retry-failed)
docker compose --profile embedding up -d embedder      # 임베딩 서버 (메모리 약 4GB, 처음에 모델 2.3GB 내려받기). AI 사서 주제 검색의 벡터에도 쓰고, 없으면 키워드로 내려간다
uv run python scripts/embed_books.py --incremental     # 운영자: 두 층 임베딩 적재 (--full, --layer official|library, --library-id, --batch-size, --kind)
uv run python scripts/embedding_search.py "질의" --sample  # 임베딩 확인: 표본 적재 후 상위 5권 (--library-id N)
uv run python scripts/rebuild_contributors.py         # 운영자: 기여자·저자 키를 지금 규칙으로 (--check는 차이만)
uv run python -m evals.catalog_search        # 서명·저자 찾기 평가 (표본 필요, LLM 없음)
uv run python -m evals.conversation           # 대화 추천 평가 (LLM 호출, 승인 먼저. 실험 장서·임베딩 서버 필요)
uv run python -m evals.admin_agent            # 운영 에이전트 분석 질문 평가 (LLM 호출, 승인 먼저. 가상 기관, 임베딩 서버 없음)
```

추천 실험과 실험 장서 명령은 `evals/recommendation/README.md`, `evals/collection/README.md`에 있다.

## 디렉터리 구조

코드 배치는 저장소를 읽어 확인한다. 패키지마다 `README.md`(역할과 규칙)가 있고, 그 패키지 파일을 다루면 패키지의 `CLAUDE.md`가 README를 불러온다. 코드만 봐서는 알기 어려운 것만 적는다.

- `app/central/`(운영자 층), `app/library/`(기관 공통), `app/features/`(기관 개별), `app/agent/`(공통 실행기), `app/core/`(공통 도구). 조립은 `app/main.py`(라우터, 기능 등록, 프로필)와 `app/models.py`(모든 모델 등록, Alembic·테스트용)다.
- `app/agent/`는 어떤 tool이 있는지 모른다. tool은 패키지별 `tools.py`가 내놓고 `app/main.py`가 조립한다.
- 어린이 필터는 기능(`app/features/children/`)에 두고, 공통의 추천 코드(`app/library/recommendation/`)는 훅(`app/library/hooks.py`)으로만 부른다.
- 운영자 실행은 `scripts/`(채움, 임베딩 적재, 기여자 다시 만들기, 실험 장서 적재)에 있고 기관 API에는 실행 경로가 없다.
- `evals/`는 평가와 추천 실험이다. 받은 원본과 라벨(`evals/*/data/`)은 저장소에 넣지 않는다.

## 설계 원칙 (반드시 지킬 것)

1. **라우터는 얇게, 로직은 service에.** REST API와 에이전트 tool이 같은 service 함수를 호출한다. 라우터에 비즈니스 로직을 넣지 않는다. 패키지마다 같다.
2. **기관 데이터는 항상 분리한다.** 모든 기관 데이터는 `library_id`로 나눈다. 조회·쓰기·에이전트 tool·자연어 SQL 모두 현재 로그인한 기관 범위를 코드에서 강제한다. 요청 값으로 받은 library_id를 그대로 믿지 않는다. 공식 서지(`books`)는 기관이 쓸 수 없고, 기관의 판단과 입력 값은 기관 도서(`library_books`)에 둔다. 의존 방향은 `features → library → central → core`이고 테스트가 강제한다. 운영자 층(`app/central/`)은 기관 모델과 어린이 구분을 모른다. 어린이 구분은 MVP 작은도서관에 필요한 기관 개별 기능(`app/features/children/`)이고, 공통 코드는 훅으로 사건만 알린다.
3. **확정 작업은 승인 흐름을 거친다.** 큐레이션 게시, 연체 안내, 구매 요청서 확정은 `draft → pending_approval → approved → (published | confirmed)` 상태를 따른다. 승인 대기 상태는 DB에 저장한다. 이용자 쪽 쓰기는 대출·반납과 희망도서 신청만 허용한다.
4. **소장 도서만 추천한다.** 추천 결과는 항상 해당 기관의 holdings에 있는 책이다. 대출 중이면 표시하고, 없으면 희망도서 신청으로 연결한다. 어린이 요청에는 그 기관에서 어린이 도서로 분류된 책(`library_book_audiences`의 `children`)만 추천하고, 분류가 확실하지 않은 책은 일반 도서로 둔다. 이 규칙은 LLM이 아니라 코드(필터)로 강제한다.
5. **기존 시스템 위에 얹는다.** 장서는 기존 대출 프로그램에서 가져오는 것을 기본으로 하고, 담당자가 같은 정보를 두 번 입력하게 만들지 않는다. 외부 대출 기관(`loan_mode = external`)에서는 대출 쓰기 tool을 끄고, 대출 상태에는 마지막 갱신 시각을 함께 보여 준다.
6. **책 정보는 데이터로만 답한다.** 줄거리·저자 정보는 DB나 외부 API 결과를 근거로 하고, LLM이 인용문이나 정보를 지어내지 않게 한다.
7. **LLM이 할 일과 코드가 할 일을 나눈다.** 금액 계산, 권차 변환, 텍스트·ISBN 정규화, 어린이 도서 분류, 소장 필터는 결정적인 코드로 처리한다. LLM은 의도 파악, 후보 선택과 설명, 애매한 매칭 판단에 쓴다.
8. **개인정보는 최소한으로.** 이용자 대화에서 이름·연락처를 묻지 않고, 대화 기록에 개인정보를 남기지 않는다. 회원번호는 대출과 희망도서 신청에만 쓴다.

## 코딩 규칙

- 모든 DB 접근은 async. 세션은 의존성 주입(`Depends`)으로 받는다.
- 요청·응답은 항상 Pydantic 스키마로 정의한다. ORM 모델을 그대로 반환하지 않는다.
- 금액은 `int`(원 단위)로 다룬다. float 금지.
- ISBN은 하이픈 없는 13자리 문자열로 저장한다.
- 상태 값은 `StrEnum`으로 정의한다.
- 서명으로 줄 세우는 코드는 `app/core/text.py`의 `korean_order`(ICU `ko-x-icu`)를 쓴다. DB 기본 collation은 바꾸지 않는다.
- 외부 API 키, DB URL은 `.env`에서 읽고 코드에 하드코딩하지 않는다. `.env.example`을 함께 관리한다.
- 외부 도서 API의 표지 이미지는 저장하지 않고 원본 URL로만 표시하며, 출처를 함께 보여준다.
- 공식 서지는 소장 도서의 ISBN만 채운다. YES24 이용 조건이 전체 도서 정보의 축적과 재배포를 금지하므로 미리 대량으로 받아 두지 않는다. 받은 원본은 저장소에 넣지 않는다. 예외(평가 표본, 실험 장서, 출처 값, 대출 신호 파일)와 저장하지 않는 값(카카오 판매가·판매 상태, 정보나루 표지)은 `docs/data-sources.md`에 있다.
- 에이전트는 공통 실행기 하나에 프로필(프롬프트, tool 묶음, 권한)만 바꿔 쓴다. tool은 같은 프로세스에서 service를 감싸고, 이름·설명·JSON Schema로 정의한다. `library_id`는 실행기가 코드로 주입하고 LLM이 정하지 않는다.
- 기관 개별 기능의 값은 공통 테이블과 공통 API에 넣지 않는다. 기능은 `app/main.py`에서 등록하고, 서버를 거치지 않는 새 진입점을 만들면 등록을 함께 챙긴다.
- 새 service 함수에는 테스트를 같이 작성한다. 기관 분리(다른 기관 데이터가 보이지 않는지) 테스트를 빠뜨리지 않는다.

## 도메인 용어

세부 규칙과 저장 위치는 `docs/glossary.md`에 있다.

- **운영자 층 / 기관 공통 / 기관 개별**: 코드의 세 층(`central` / `library` / `features`).
- **공식 서지(book)**: 운영자 층의 서지. ISBN이 있는 책만, 세 출처를 필드별로 합친 값. 기관은 쓸 수 없다. 필드마다 출처를 `books.field_sources`에 둔다.
- **기관 도서(library book)**: 이 도서관의 그 책. 파일·입력 값과 ISBN 없는 책. 공식 서지가 있으면 연결하고 공식 값을 먼저 쓴다.
- **사본(holding)**: 기관 도서의 한 권. 대출 단위. 등록번호(`accession_number`)로 식별하고 청구기호(`call_number`)로는 식별하지 않는다.
- **제적(withdrawn)**: 장서에서 빠진 사본. 추천·소장 권수에서 빠지고 대출 기록은 남는다.
- **입수 구분(acquisition type)**: `purchased`·`donated`·`unknown`. 가져온 매입 사본의 빠진 값은 오류가 아니라 `missing_fields`다.
- **어린이 도서(audience)**: `children` / `general` 둘만. 근거(`manual` > `import_label` > `external_category`)를 함께 저장하고, 확실하지 않으면 `general`.
- **부가기호(addition symbol)**: ISBN 부가기호 5자리. 첫 자리 6·7이 어린이 도서 근거다.
- **기여자(contributor) / 저자 키 / 이름 맞춤 키 / 시리즈 키**: 저자 원문을 역할별로 푼 사람(`book_contributors`), 기관 도서의 지은이 키(`author_keys`), 공백·문장부호를 지우고 소문자로 바꾼 맞춤 값, 시리즈마다의 맞춤 키(`series_keys`).
- **공식 서지 벡터 / 기관 도서 벡터**: 임베딩 두 층. 책 하나는 한 층에만 속한다. 제품은 종류 `full`만 쓴다.
- **운영 방식(loan_mode)**: `external`(외부 대출: 기존 프로그램에서 대출) / `internal`(자체 대출: AI 사서가 대출 처리). 그 방식을 쓰는 기관은 외부 대출 기관 / 자체 대출 기관.
- **회원번호(member number)**: 대출과 희망도서 신청에만 쓴다.
- **실험 장서**: 추천 실험용 525권. 개발 DB의 `실험용 가상 작은도서관`만 소장하고 서비스 데이터가 아니다.

## 하지 말 것

- 결제, POS 연동, MARC 편목은 만들지 않는다 (범위 밖).
- 본격 대출 관리(예약, 연장, 연체료, 상호대차)는 만들지 않는다. 빌림·반납·대출 중 표시까지만.
- 기존 대출 프로그램과의 실시간 연동(API 동기화)은 만들지 않는다. 파일 가져오기까지만.
- 독립서점 모드, 시즌·이벤트 큐레이션, 개인화 추천, 세밀한 연령 구분은 아직 만들지 않는다 (2단계).
- 요청받지 않은 범위까지 한 번에 구현하지 않는다. change의 tasks가 끝나면 무엇을 했는지 요약하고 멈춘다.
