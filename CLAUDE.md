# CLAUDE.md

## 프로젝트 개요

사서가 없는 작은도서관을 위한 AI 사서 웹 서비스. 도서관 PC 브라우저에 로그인해 켜 두면 이용자는 AI 사서에게 추천·큐레이션을 받고 대출하며, 관리자는 운영 에이전트로 장서·대출 현황을 분석하고 초안을 승인한다.

- **이용자 화면 – AI 사서 에이전트**: 소장 도서 검색, 추천, 큐레이션, 대출, 희망도서 신청
- **관리자 화면 – 운영 에이전트**: 자연어 SQL 분석, 장서 가져오기·등록, 큐레이션·연체 안내·보충 구매 요청서 초안. 확정은 모두 승인 후

MVP 대상은 작은도서관이다. 독립서점은 2단계 '모드'(대출 대신 서가 안내·구매 문의)로 추가한다. 이 프로젝트의 핵심 성과 지표는 **추천 품질**이다.

포지션은 '기존 시스템 위에 얹는 AI 사서'다. 장서는 기관이 이미 쓰는 대출 프로그램의 엑셀·CSV 내보내기를 가져오는 것이 기본이고, 자체 대출은 대출 프로그램이 없는 기관과 데모용이다.

자세한 설계는 `docs/design.md`를 참고한다. 설계와 다르게 구현해야 할 이유가 생기면 먼저 물어본다.

## 현재 단계

**4주차: 검색과 안내** (진행 중인 change는 `add-related-books`다(issue #41, 구현 끝, archive 전). `add-loan-signals`는 2026-11-17에 archive했다. 정보나루가 막혀 남은 11회를 받지 못해 미룬 일 D.1~D.4 중, 정보나루가 필요 없는 D.3(남겨 둔 분야 실행)·D.4(결과 문서)는 `add-related-books`에서 했다. 정보나루가 필요한 D.1(남은 11회: 이용 분석 `9791199489509`·`9791199491717`(조정 기준 책 `s10`)·`9791199509009`, 인기 8조건. 하루 500건의 2.2%. 인기 기간 정하기)과 D.2(`s10`을 넣어 함께 대출 변형 다시 재기)는 약관 확인 뒤의 대출 테이블 change `add-loan-signal-store`(가칭) tasks 맨 앞으로 다시 옮겼다(2026-11-17 사용자 요청). 2026-11-16에 원래의 `add-bibliographic-sources`를 둘로 나눴다).
AI 사서 v1(`add-librarian-agent`), 서명·저자 찾기(`add-catalog-search`), 도서관 안내(`add-library-guide`), 도서 임베딩 파이프라인(`add-book-embeddings`), 정규화와 기여자 표(`add-book-contributors`)는 끝났고, 벡터 두 층과 실험 장서(`add-official-book-embeddings`)는 끝났고, 추천 실험(`add-recommendation-experiments`)도 끝났다. 검색과 추천을 나눈다. 이용자는 대부분 제목이나 저자를 알고 오므로, 아는 책 찾기(오타 허용, 자동완성)를 LLM 없이 코드로 먼저 갖추고 대화와 잇는다. LLM은 자연어로 책을 찾는 대화와 도서관 안내를 맡는다. 2026-11-12에 `add-related-books` 앞에 추천 실험의 바탕을 먼저 두기로 했다. 순서는 정규화와 기여자 표(`add-book-contributors`, 끝남), 벡터 두 층과 실험 장서(`add-official-book-embeddings`, 끝남), 주제로 찾기 실험(`add-recommendation-experiments`, 끝남), 비슷한 책·아무 조건 없음 실험(`add-related-book-experiments`, 2026-11-15에 나눔), 카카오·도서관 정보나루 연동과 일반화(`add-bibliographic-sources`)이고, 그 뒤에 이긴 설정을 제품에 내보내는 `add-related-books`, 대화 추천 평가(`add-recommendation-evals`)가 온다. 서명 정렬은 2026-11-16부터 가나다순이다(`fix-korean-title-order`). DB 기본 collation(`en_US.utf8`)은 그대로 두고 정렬 키에만 ICU `ko-x-icu`를 건다(`app/core/text.py`의 `korean_order`). 서명으로 줄 세우는 새 코드도 이 도우미를 쓴다. 임베딩 텍스트의 기본은 2026-11-15부터 저자를 뺀 서명·분류·소개(텍스트 버전 2)다. 저자는 고유명사라 기여자·저자 키와 서명·저자 찾기가 맡는다. `add-recommendation-experiments`에서 "저자 넣기"(v1과 같은 필드), 소개만, 필드별 벡터(종류 `kind`)를 비교했고 어느 것도 기본을 이기지 못해 2026-11-16에 기본(`full`)을 확정했다. 주제로 찾기는 키워드 순위와 벡터 순위를 RRF(k 60, 1:1)로 합친 순위가 지금 키워드 검색을 이겼다(조정 nDCG@5 0.410 → 0.517). 제품에는 아직 잇지 않았고(`app/library/recommendation/topic.py`), `add-topic-search-tool`(가칭)이 잇는다. 요청마다 임베딩 서버가 필요하고 AI 사서 행동이 바뀌어 LLM 평가 전후 비교가 필요해서 `add-related-books`에서 나눴다(2026-11-17 사용자 결정). 시리즈 묶기는 품질은 같고 겹침만 줄어 그때 다시 정한다. 서명 가나다순 뒤의 topic 기준은 조정 nDCG@5 0.453 → 0.519다(`add-related-book-experiments`에서 보충 라벨을 달고 다시 잼). 비슷한 책과 최근 기록은 2026-11-16에 쟀다(`add-related-book-experiments`, `app/library/recommendation/related.py`. 제품에는 `add-related-books`가 기본 설정 그대로 이었다). 비슷한 책은 기준 책의 저장된 벡터로 찾는 벡터 이웃(`full`)을 어떤 변형도 채택 규칙으로 넘지 못했다. 같은 시리즈·같은 저자 신호를 RRF로 합쳐도 품질은 같고(근거만 붙는다), 근거 표시를 위해 기본값은 RRF 1:1로 두기로 했다(사용자 결정) 시리즈 묶기·MMR·같은 외부 분류로 좁히기는 쓰지 않는다. 최근 기록은 기록 책 벡터의 평균이 책별 순위 RRF를 이겼다. 같은 KDC 세목과 우리 도서관 인기는 실험 장서에 값이 없어 코드와 테스트만 있다. 두 세트의 라벨은 Claude가 달고 사람은 고정 표본만 본다. 결과 표는 `openspec/changes/archive/2026-11-16-add-related-book-experiments/design.md`의 "결과"에 있다. 평가 라벨은 Claude가 초안을 달고 사람이 검수한 것이라 수치는 방식끼리의 상대 비교에만 쓴다. 결과 표는 `openspec/changes/archive/2026-11-16-add-recommendation-experiments/design.md`의 "결과"에 있다. 실험 장서는 YES24 카테고리 스테디셀러 525권(19개 분야, 2026-11-15에 한 번 받음)이고 개발 DB의 `실험용 가상 작은도서관`이 소장한다. 종교·예술·건강 취미·여행 50권은 남겨 둔 분야라 조정에 쓰지 않는다. 근거 수치는 `openspec/changes/archive/2026-11-11-add-book-embeddings/design.md`의 Open Questions에 있다. CPU 적재 속도는 ONNX 변환본으로 바꿔 줄였고 측정은 `app/central/README.md`에 있다. 적재 배치 기본값은 4다(`add-official-book-embeddings`에서 32에서 내림). 평가에서 넘겨받은 항목(어린이 지표를 책 분류와 요청 판단으로 나누기 등)은 `openspec/changes/archive/2026-11-10-add-librarian-agent/tasks.md`의 끝에 있다. 공식 서지의 출처는 2026-11-17부터 셋이다(`add-bibliographic-sources`): 도서관 정보나루(KDC, KDC 분류명, 부가기호, 권, 출판사), YES24(서명·부제·저자, 소개, 목차, 시리즈, 분류 원문, 표지·상품 링크), 카카오(정가, 출간일, 다른 출처에 없는 책). 필드마다 정한 순서로 합치고(`app/central/sources.py`의 `merge`) 필드별 출처를 `books.field_sources`에 남긴다. YES24는 버리지 않고 세 출처 중 하나로 쓴다(사용자 결정). 서명·저자를 YES24 먼저 쓰는 이유는 정보나루 서명이 권차를 빼고 대등 서명을 붙여 와 YES24와 67%(정리 규칙 뒤 85%)만 맞았기 때문이다. 정보나루 키는 쿼리 파라미터로만 보내므로 https로 부르고 URL을 로그에 남기지 않는다. 하루 500건을 넘게 부르려면 정보나루에 서버 IP를 등록한다. 실험 장서를 세 출처로 다시 채워 쟀다(A 세 출처, B YES24 뺌): A에서 topic `hybrid-k60`, history `hist-mean`은 그대로이고, 비슷한 책 `sim-rrf`는 정보나루 KDC로 같은 KDC 세목 신호가 14권에서 값을 가지면서 처음으로 채택 규칙을 넘었다(조정 +0.052). B는 대체로 낮다(최근 기록 조정 -0.224). 결과 표는 `openspec/changes/archive/2026-11-17-add-bibliographic-sources/design.md`의 "결과"에 있다. 대출 신호(`add-loan-signals`)는 정보나루 이용 분석(함께 대출·마니아·다독자)과 연령 묶음별 인기를 실험 장서에 받아(469권 중 466권) 쟀다. 같은 KDC 세목의 몫은 다시 확인됐고(조정 +0.053), 세 자리·계층 단위, 세목 안 벡터 순, 함께 대출(+0.017, 5·5·4), 최근 기록의 KDC·저자·함께 대출 신호는 어느 것도 채택 규칙을 넘지 못해 기본값은 그대로다(`sim-rrf`, `hist-mean`, `s10` 다시 재기 전). 함께 대출은 제품 신호 코드(`co_loan`)와 정보나루 인기 채우기·빈 기록 규칙만 있고 제품 테이블은 약관 확인 뒤다. 결과 표는 `openspec/changes/archive/2026-11-17-add-loan-signals/design.md`의 "결과"에 있다. `add-related-books`는 이긴 설정을 제품에 이었다: 비슷한 책 API(`GET /catalog/books/{id}/similar`, LLM 없음, 근거 코드와 문구), AI 사서 tool `find_related_books`(책 id면 비슷한 책, 비우면 대화 세션의 책 최신 3권으로 `hist-mean`, 세션에 책이 없으면 우리 도서관 인기), 어린이 관련 책 tool과 어린이 기준 책의 범위 제공자(`hooks.register_related_scope`), 실행 값 주입(`run(tool_values=…)`), `chat_messages.library_book_ids`. 대출 신호 공급은 없어서 "아무거나"는 우리 도서관 인기에서 끝난다. 남겨 둔 분야(확인 전용) 결과는 주제로 찾기 `hybrid-k60` +0.097(4·3·1, 방향 같음), 비슷한 책 `sim-rrf` -0.004(차이 없음, 남겨 둔 분야에 KDC 세목 신호가 거의 없음), 최근 기록 같은 설정이다. 벡터 근거만 있는 책의 최소 유사도는 진단 결과 문턱 없음이다(0·2 라벨의 코사인이 겹침). 시리즈 상한 1은 켜지 않고, 시리즈 다음 권(권차)은 미룬다. 결과 표는 `openspec/changes/add-related-books/design.md`의 "결과"에 있다. 다음은 `add-topic-search-tool`이다.

## OpenSpec 작업 규칙

이 프로젝트는 OpenSpec으로 스펙 기반 개발(SDD)을 한다. 모든 기능 작업은 change 단위로 진행한다.

**문서 역할**

| 위치 | 역할 |
| --- | --- |
| `docs/design.md` | 왜 만드는지, 전체 그림. 배경 참고용이며 요구사항의 기준은 아니다 |
| `app/*/README.md` | 패키지별 역할과 규칙. 패키지를 고칠 때 먼저 읽는다 |
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

**MVP change 순서** (8주)

1. `add-library-core-domain` – 이전 도메인 정리, 모델, 기관 분리, 인증, 장서·대출 CRUD, 시드 데이터
2. `add-holdings-import` – 기존 시스템 엑셀·CSV 장서 가져오기, 파일 근거 어린이 도서 분류
3. `add-library-catalog-layer` – 공식 서지와 기관 도서 분리, 기관별 어린이 구분
4. `add-book-enrichment` – YES24 연동, 공식 서지 채움, 외부 분류 근거
5. `refactor-layer-packages` – 운영자·기관 공통·기관 개별 패키지 분리, 어린이 기능 분리
6. `add-agent-runner` – 공통 실행기, tool 계약, 프로필, LLM 접점, 실행 기록, 최종 검사 자리
7. `add-librarian-agent` – AI 사서 v1, 조회 tool, 어린이 검사, 대화 API와 SSE, 추천 노출 기록
8. `add-catalog-search` – 서명·저자 찾기(오타 허용)와 자동완성, 검색 API, 대화와 잇기(고른 책, 찾은 책 카드), 검색 평가
9. `add-library-guide` – 도서관 안내 정보(운영 시간, 휴관일, 대표 연락처, 시설 위치, 이용 규칙), 반납 예정일 계산, 안내 tool
10. `add-book-embeddings` – 도서 임베딩 파이프라인: pgvector, 로컬 임베딩 서버(TEI), 인코더 접점, 임베딩 텍스트, `book_embeddings`, 전체·증분 적재 CLI
11. `add-book-contributors` – 정규화 통일(저장용·비교용, 이름·역할·KDC·시리즈명), 공식 서지 기여자 표, 기관 도서 저자 키, YES24·기관 파일 저자 해석기
12. `add-official-book-embeddings` – 벡터 두 층(공식 서지 벡터는 운영자 층·공식 값만으로, 기관 도서 벡터는 공식 서지 없는 책만), 실험 장서(YES24 약 500권을 공식 서지로 적재하고 가상 기관이 소장), 적재 배치 기본값
13. `add-recommendation-experiments` – 추천 실험(YES24 조정): 실험 틀, 평가 세트와 라벨(초안+검수), 주제로 찾기의 단계별 변형 비교, 임베딩 텍스트 종류 비교와 기본 확정
14. `add-related-book-experiments` – 비슷한 책(같은 저자·시리즈·분류·벡터 이웃)과 아무 조건 없음의 신호와 변형 비교, 두 세트의 라벨
15. `add-bibliographic-sources` – 카카오 도서 검색·도서관 정보나루 연동: 세 출처(정보나루·카카오·YES24)의 필드별 기준 출처, 채움 일반화, 어린이 근거(부가기호), 실험 장서를 세 출처로 다시 채우기, 같은 ISBN 다른 메타데이터 비교
16. `add-loan-signals` – 정보나루 대출 신호와 일반화: 같은 KDC 세목 실측, 함께 대출된 책, 인기 대출, 빈 기록의 "아무거나", 다른 분야(남겨 둔 50권) 비교, 비슷한 책 기본값 다시 보기
17. `add-related-books` – 실험에서 이긴 설정을 제품에 내보내기: 찾은 책 카드 아래 비슷한 책(LLM 없음), AI 사서 tool, REST
18. `add-topic-search-tool` – 주제로 찾기(`hybrid-k60`)를 AI 사서에 잇기: 서비스 중 임베딩 서버, 꺼졌을 때 키워드 검색, LLM 평가 전후 비교
19. `add-recommendation-evals` – 대화 추천 평가(LLM 포함): 어울림 라벨, Hit Rate·Recall, 어린이 지표 둘, 모델 비교. LLM 채점은 최종 서비스 테스트에서
20. `add-admin-agent` – 운영 에이전트, 자연어 SQL 분석과 안전장치, 장서 등록
21. `add-approval-flow` – 초안 → 승인 → 실행, 서버 재시작 후에도 재개
22. `add-librarian-actions` – 대출·반납·희망도서 tool, 회원번호 입력, 운영 방식에 따른 tool 끄기
23. `add-web-ui` – 이용자·관리자 화면
24. `add-observability-deploy` – Langfuse, 배포, README, 데모
- (정보나루 약관 확인 뒤, 순서 미정) `add-loan-signal-store` – 함께 대출·정보나루 인기의 운영자 층 테이블과 갱신 실행, 제품의 대출 신호 공급, `add-loan-signals` 미룬 일 D.1·D.2

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
uv run python scripts/enrich_books.py        # 운영자: 공식 서지 채움, 정보나루·카카오·YES24 세 키 필요 (--limit, --retry-failed)
uv run python -m evals.catalog_search        # 서명·저자 찾기 평가 (표본 필요, LLM 없음)
docker compose --profile embedding up -d embedder      # 임베딩 서버 (메모리 약 4GB, 처음에 모델 2.3GB 내려받기)
uv run python scripts/embed_books.py --incremental     # 운영자: 두 층 임베딩 적재 (--full, --layer official|library, --library-id, --batch-size, --kind)
uv run python scripts/embedding_search.py "질의" --sample  # 임베딩 확인: 표본 적재 후 상위 5권 (--library-id N)
uv run python scripts/rebuild_contributors.py         # 운영자: 기여자·저자 키를 지금 규칙으로 (--check는 차이만)
uv run python -m evals.collection.fetch --dry-run     # 실험 장서 받기 미리 보기 (실제 받기는 한 번만, 파일이 있으면 멈춤)
uv run python -m evals.collection.sources --dry-run  # 실험 장서의 정보나루·카카오 값 받기 미리 보기 (출처마다 이어 받기, 다 받으면 멈춤)
uv run python -m evals.collection.compare            # 실험 장서의 출처끼리 같은 ISBN 비교 (건수만)
uv run python -m evals.collection.loans --dry-run    # 실험 장서의 정보나루 대출 신호(이용 분석·인기) 받기 미리 보기 (이어 받기, 다 받으면 멈춤. --overlap은 소장 겹침만)
uv run python scripts/seed_experiment.py             # 운영자: 실험 장서를 개발 DB의 가상 기관에 넣기 (다시 돌려도 같음. --purge 지우기, --sources 합칠 출처 고르기)
uv run python -m evals.recommendation topic --split all --variants current,vec-text,hybrid   # 추천 실험: 주제로 찾기 (LLM 없음, 질의 벡터 캐시)
uv run python -m evals.recommendation similar --split all --variants sim-vec,sim-rrf,sim-best   # 추천 실험: 비슷한 책 (history도. 저장된 벡터만 써서 임베딩 서버 필요 없음. 함께 대출 변형은 대출 신호 파일을 읽음(--loan-signals), --holdout은 남겨 둔 분야 세트와 정해 둔 변형만)
uv run python -m evals.recommendation compare <기준 실행> <새 실행>   # 추천 실험: 같은 세트의 두 실행을 지금 라벨로 짝 비교 (장서 값을 바꾸기 전후)
uv run python -m evals.recommendation.threshold <비슷한 책 실행>   # 벡터 근거만 있는 책의 최소 유사도 진단 (라벨 등급별 코사인, 결과는 실행 폴더의 threshold.md)
uv run python -m evals.recommendation.review topic    # 라벨 검수 화면 http://127.0.0.1:8765 (similar·history도. --sample은 고정 표본만, --since <백업 라벨 파일>은 그 뒤 보충 라벨만, --size는 표본 수, --holdout은 남겨 둔 분야 라벨. 초안은 draft, 직접 달기는 label)
uv run uvicorn app.main:app --reload         # 서버 (Swagger: /docs)
uv run pytest                                # 테스트
uv run ruff check . && uv run ruff format .  # 린트·포맷
```

## 디렉터리 구조

```
app/
├── main.py       # 조립: 라우터 포함, 기관 개별 기능 등록
├── models.py     # 조립: 모든 모델 등록, Base, 테이블 구분 (Alembic·테스트용)
├── core/         # config(설정), db(세션), security(비밀번호·토큰), clock(기관 시간대 오늘), holidays(공휴일),
│                 # isbn(정규화·검증), text(저장용·비교용·이름 맞춤 정규화, 자모 규칙, KDC 키, 서명 정렬 순서),
│                 # contributors(역할 표, 기관 파일 저자 해석, 저자 키), embedding_text(임베딩 텍스트 조립 규칙·버전·종류),
│                 # kdc(KDC 주류 이름), migrations, model_base, errors, tenancy, schemas(페이지)
├── central/      # 운영자 층: 공식 서지와 외부 연동. 기관 모델을 모른다
│   ├── models.py     # Book, BookContributor(공식 서지 기여자), OfficialBookEmbedding(공식 서지 벡터)
│   ├── enrichment.py # 서지 채움 실행, 접점(EnrichmentTargets)
│   ├── sources.py    # 출처 중립 값(OfficialValues), 세 출처를 필드별 기준 출처로 합치기(merge)
│   ├── official_books.py # 공식 서지를 만드는 함수(create_official: 기여자, 시리즈 키, 필드별 출처)
│   ├── contributors.py # 출처별 저자 해석기, 기여자 저장(sync_contributors)
│   ├── embedding.py  # 임베딩 인코더 접점(Embedder: 문서·질의 인코딩), 두 층의 배치 흐름(run_layer)
│   ├── embedding_text.py # 공식 서지 벡터의 텍스트(공식 값만)
│   ├── official_embeddings.py # 공식 서지 벡터 적재
│   └── external/     # 외부 API: http(출처 공통 호출 간격·중단), values(응답 값 읽기 공통),
│                     # data4library(정보나루: 키는 쿼리로만, 서명 정리), kakao(책 검색: ISBN 분해, 저자 배열 잇기),
│                     # yes24(엔드포인트·필드 정의를 한곳에, 저자 해석, 카테고리는 실험 장서 받기 전용), tei(임베딩 서버 어댑터)
├── library/      # 기관 공통
│   ├── api/      # 라우터: auth, library, guide(안내·휴관일), staff, library_books, catalog(찾기·자동완성·비슷한 책),
│   │             # holdings, members, loans, librarian
│   │             # (이후 curations, requests ...)
│   ├── services/ # 비즈니스 로직 (REST API와 에이전트 tool이 함께 사용). related: 관련 책 제품 경로(비슷한 책, 대화 세션의 책)
│   ├── models/   # library(기관·직원·세션), catalog(기관 도서·사본), circulation(회원·대출), guide(안내),
│   │             # embedding(기관 도서 벡터: 공식 서지 없는 책만)
│   ├── schemas/  # Pydantic 스키마
│   ├── importing/ # 장서 가져오기: 엑셀·CSV 파싱, 머리글 인식, ISBN 정규화
│   ├── recommendation/ # 서명·저자 찾기와 자동완성(lookup), 주제 검색(search), 소장 검사, 카드, 노출 기록.
│   │                   # 주제로 찾기 순위(topic: 키워드+벡터 RRF, 제품에는 아직 잇지 않음), 순위 함수(ranking: RRF, 시리즈 묶기, MMR).
│   │                   # 비슷한 책·최근 기록·우리 도서관 인기(related: 같은 시리즈·저자·KDC 세목·벡터 이웃, 판본 제외, 최소 유사도), 근거 코드·문구(basis).
│   │                   # 기관 도서 벡터의 텍스트(embedding_text), 기관 도서 벡터 적재와 두 층 유사도 조회·저장된 벡터로 이웃 조회(embeddings),
│   │                   # 같은 저자(authors).
│   │                   # 어린이 필터는 기능에 둔다.
│   ├── deps.py   # 현재 직원·기관, 역할
│   ├── hooks.py  # 기관 개별 기능 접점(사건, 관련 책 범위 제공자)
│   └── enrichment_targets.py # 운영자 접점 구현, 처리 현황
├── features/     # 기관 개별 기능 (패키지마다 README.md가 있다)
│   └── children/ # 어린이 구분: 규칙, 저장소, service, 훅, API
├── seed/         # 조립: 시드 데이터 생성 (scripts/seed.py가 실행), 실험 장서 적재(experiment, scripts/seed_experiment.py가 실행)
└── agent/        # 공통 실행기: tool calling 루프, 최종 검사, 실행 기록, (이후) 승인 대기·재개.
                  # 어떤 tool이 있는지 모른다. tool은 패키지별 tools.py가 내놓고 main.py가 조립한다
migrations/       # Alembic
scripts/seed.py   # 더미 데이터 (Faker)
scripts/enrich_books.py  # 운영자용 공식 서지 채움
scripts/embed_books.py   # 운영자용 두 층 임베딩 적재
scripts/seed_experiment.py  # 운영자용 실험 장서 적재(개발 DB)
scripts/embedding_search.py  # 임베딩 확인용 유사도 조회
scripts/rebuild_contributors.py  # 운영자용 기여자·저자 키 다시 만들기
docker/embedder/start.sh # 임베딩 서버 시작(모델 받기, 입력 한도 낮추기)
evals/            # 장서 가져오기·AI 사서·찾기 평가, 실험 장서 받기(collection: YES24 원본, 정보나루·카카오 값, 출처 비교, 정보나루 대출 신호), 추천 실험(recommendation: 세트 셋과 남겨 둔 분야 세트, 라벨 초안·검수·고정 표본, 변형, 지표, 대출 신호 파일 읽기), (이후 단계) 대화 추천 평가와 채점
tests/
docs/design.md
openspec/
├── specs/        # 기능별 현재 스펙 (archive된 change가 여기에 반영됨)
└── changes/      # 진행 중인 change
```

## 설계 원칙 (반드시 지킬 것)

1. **라우터는 얇게, 로직은 service에.** REST API와 에이전트 tool이 같은 service 함수를 호출한다. 라우터에 비즈니스 로직을 넣지 않는다. 패키지마다 같다.
2. **기관 데이터는 항상 분리한다.** 모든 기관 데이터는 `library_id`로 나눈다. 조회·쓰기·에이전트 tool·자연어 SQL 모두 현재 로그인한 기관 범위를 코드에서 강제한다. 요청 값으로 받은 library_id를 그대로 믿지 않는다. 공식 서지(`books`)는 기관이 쓸 수 없고, 기관의 판단과 입력 값은 기관 도서(`library_books`)에 둔다. 의존 방향은 `features → library → central → core`이고 테스트가 강제한다. 운영자 층(`app/central/`)은 기관 모델과 어린이 구분을 모른다. 어린이 구분은 MVP 작은도서관에 필요한 기관 개별 기능(`app/features/children/`)이고, 공통 코드는 훅으로 사건만 알린다.
3. **확정 작업은 승인 흐름을 거친다.** 큐레이션 게시, 연체 안내, 구매 요청서 확정은 `draft → pending_approval → approved → (published | confirmed)` 상태를 따른다. 승인 대기 상태는 DB에 저장한다. 이용자 쪽 쓰기는 대출·반납과 희망도서 신청만 허용한다.
4. **소장 도서만 추천한다.** 추천 결과는 항상 해당 기관의 holdings에 있는 책이다. 대출 중이면 표시하고, 없으면 희망도서 신청으로 연결한다. 어린이 요청에는 그 기관에서 어린이 도서로 분류된 책(`library_book_audiences`의 `children`)만 추천하고, 분류가 확실하지 않은 책은 일반 도서로 둔다. 이 규칙은 LLM이 아니라 코드(필터)로 강제한다.
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
- 공식 서지는 소장 도서의 ISBN만 채운다. YES24 이용 조건이 전체 도서 정보의 축적과 재배포를 금지하므로 미리 대량으로 받아 두지 않는다. 평가 표본 약 100권(`evals/librarian/data/`)과 실험 장서 525권(`evals/collection/data/`, 개발 DB의 가상 기관에만)만 예외이고, 둘 다 한 번만 받고 저장소에 넣지 않는다. 실험 장서는 `add-bibliographic-sources`에서도 지우지 않았고, 같은 ISBN의 정보나루·카카오 값을 따로 받은 파일(`sources_collection.json`, 출처마다 이어 받기)을 함께 쓴다. `add-loan-signals`부터 같은 ISBN의 정보나루 대출 신호(함께 대출·마니아·다독자 ISBN 순위, 연령 묶음별 인기 ISBN 순위와 대출 수)를 받은 파일(`loan_signals.json`)도 쓴다. ISBN 순위와 수만 남기고 서명·표지는 남기지 않는다. 카카오 판매가·판매 상태와 정보나루 표지(비영리 화면 표시만 허용)는 저장하지 않는다.
- 에이전트는 공통 실행기 하나에 프로필(프롬프트, tool 묶음, 권한)만 바꿔 쓴다. tool은 같은 프로세스에서 service를 감싸고, 이름·설명·JSON Schema로 정의한다. `library_id`는 실행기가 코드로 주입하고 LLM이 정하지 않는다.
- 기관 개별 기능의 값은 공통 테이블과 공통 API에 넣지 않는다. 기능은 `app/main.py`에서 등록하고, 서버를 거치지 않는 새 진입점을 만들면 등록을 함께 챙긴다.
- 새 service 함수에는 테스트를 같이 작성한다. 기관 분리(다른 기관 데이터가 보이지 않는지) 테스트를 빠뜨리지 않는다.

## 도메인 용어

- **작은도서관**: 주민센터·아파트 등에 있는 소규모 도서관. 전담 사서가 없고 담당자나 자원봉사자가 운영하는 경우가 많다.
- **운영자 층 / 기관 공통 / 기관 개별**: 코드의 세 층. 운영자 층은 어느 기관에도 속하지 않는 공식 서지와 외부 연동, 기관 공통은 모든 기관이 쓰는 기능, 기관 개별은 기관 유형에 따라 필요한 기능(어린이 구분)이다.
- **공식 서지(book)**: 서비스 운영자 층의 서지정보. ISBN이 있는 책만 두고 세 출처(정보나루·카카오·YES24)의 값을 필드별 기준 출처로 합쳐 공식으로 본다. 기관은 쓸 수 없다.
- **필드별 출처(field sources)**: 공식 서지의 필드마다 어느 출처에서 왔는지(`books.field_sources`, 열 이름 → `data4library`·`kakao`·`yes24`). 서명·저자의 출처는 `external_source`다. 출처 표시(표지 출처 등)가 이것을 읽는다.
- **부가기호(addition symbol)**: ISBN 부가기호 5자리. 첫 자리가 독자 대상이고 6(초등 학습참고서)·7(아동)이 어린이 도서 근거다. 기관 파일의 부가기호와 공식 서지의 부가기호(정보나루)가 같은 규칙을 쓴다. 필드 이름은 `addition_symbol`.
- **기여자(contributor)**: 공식 서지 저자 원문을 역할별로 푼 사람. 역할은 `author`(글·지은이), `illustrator`(그림), `translator`(옮김), `editor`(엮음), `supervisor`(감수), `original`(원저·원작), `other`(기획·사진 등)이다. 원문은 그대로 두고 표시는 원문으로 한다. 테이블 `book_contributors`.
- **시리즈 키(series keys)**: 공식 서지의 시리즈마다 이름 맞춤 키를 둔 목록. 외부 응답의 시리즈 목록에서 만든다(이은 표시용 `series_name`에서는 만들지 않는다). 필드 이름은 `series_keys`.
- **공식 서지 벡터 / 기관 도서 벡터**: 임베딩 벡터의 두 층. 공식 서지에 연결된 책은 공식 서지 벡터(`official_book_embeddings`, 운영자 층, 공식 값만, 여러 기관이 함께 씀), 연결되지 않은 책(ISBN 없음, 못 찾음)은 기관 도서 벡터(`book_embeddings`)를 쓴다. 책 하나는 한 층에만 속한다. 벡터마다 텍스트 버전과 종류(`kind`)가 있다. 제품은 `full`만 쓰고, `with_author`·`description`·`title`·`category`는 실험 비교용이다.
- **실험 장서(experiment collection)**: 추천 실험용 525권(YES24 카테고리 스테디셀러로 고른 ISBN, 같은 ISBN의 정보나루·카카오 값을 더 받음). 세 출처를 합쳐 공식 서지로 만들고 개발 DB의 `실험용 가상 작은도서관`이 소장한다. 서비스 데이터가 아니다.
- **저자 키(author keys)**: 기관 도서의 저자 원문에서 지은이(`author`·`original`)만 뽑은 이름 맞춤 키 목록. 공식 서지가 없는 책의 "같은 저자"에 쓴다. 필드 이름은 `author_keys`.
- **이름 맞춤 키(name key)**: 사람·단체 이름과 시리즈명을 맞춰 보는 값. 공백·문장부호를 지우고 소문자로 바꾼다(`J.K. Rowling` → `jkrowling`). 다른 음역과 동명이인은 풀지 않는다.
- **기관 도서(library book)**: 이 도서관의 그 책. 파일·입력 값과 ISBN 없는 책이 여기 있다. ISBN이 같은 공식 서지가 있으면 연결하고, 표시할 때 공식 값을 먼저 쓴다. 필드 이름은 `library_book_id`.
- **장서 / 소장 사본(holding)**: 같은 기관 도서라도 여러 권을 가질 수 있다. 대출은 사본 단위로 한다.
- **등록번호(accession number)**: 도서관이 사본마다 붙이는 고유 번호. 장서 가져오기에서 사본을 식별하는 기준이다. 필드 이름은 `accession_number`.
- **청구기호(call number)**: 서가에서 책을 찾는 주소(분류기호·저자기호·권차, 예: `813.7-한232ㅊ`). 같은 책의 복본은 같은 값일 수 있다. 사본 식별에는 쓰지 않는다. 필드 이름은 `call_number`.
- **입수 구분(acquisition type)**: 사본이 들어온 경로. `purchased`(매입·공식 납품, 구입가와 ISBN 필수), `donated`(기증, 기증처만 선택으로 기록), `unknown`(가져온 파일에 정보가 없음)이다. 가져온 매입 사본은 구입가나 ISBN이 없어도 오류가 아니라 빠진 정보(`missing_fields`)로 표기한다. 같은 책이라도 사본마다 다를 수 있어 사본에 둔다. 필드 이름은 `acquisition_type`, `purchase_price`, `donor`.
- **제적(withdrawn)**: 장서에서 빠진 사본. 가져온 파일에서 사라지면 이 상태가 되고, 추천·소장 권수에서 빠지며 대출 기록은 남는다.
- **회원번호(member number)**: 기관이 이용자에게 붙이는 번호. 대출과 희망도서 신청에만 쓴다. 필드 이름은 `member_number`.
- **운영 방식(loan_mode)**: `imported`는 기존 대출 프로그램의 내보내기를 가져와 쓰는 기관, `internal`은 AI 사서가 대출까지 처리하는 기관.
- **어린이 도서(audience)**: 영유아·초등학생 대상 도서. 책을 `children`(어린이 도서)과 `general`(일반 도서)로만 나눈다. 나이를 세밀하게 나누지 않는다. 기관 개별 기능이고, 기관 도서마다 근거(`manual` 관리자 지정, `import_label` 별치기호·자료실·부가기호, `external_category` 공식 서지의 외부 근거: 분류 원문이나 부가기호)를 함께 저장한다. 같은 책이라도 기관마다 다를 수 있다.
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
