## 0. 시작 전 기준

- [x] 0.1 `uv run pytest`, `uv run ruff check .`, `uv run python -m evals.catalog_search`, similar·history 기준 실행(`evals.recommendation similar --split all --variants sim-vec,sim-rrf,sim-best`, `history`의 `hist-mean`)을 돌려 run 이름과 수치를 design "결과"에 적는다(확인: 직전 실행 `20261117-143256`·`143307`·`123751`과 `results.json`이 같음)

## 1. 미룬 일 중 정보나루가 필요 없는 것 (`add-loan-signals` D.3·D.4에서 옮김)

D.1(남은 11회, 인기 기간)과 D.2(`s10`을 넣어 함께 대출 변형 다시 재기)는 정보나루가 필요해 대출 테이블 change(가칭 `add-loan-signal-store`, 약관 확인 뒤)로 다시 옮겼다(design 결정 2). 이 change에서는 정보나루를 부르지 않는다.

- [x] 1.1 (D.3) 남겨 둔 분야 실행(`--holdout`, 정해 둔 변형 `current`·`hybrid-k60` / `sim-vec`·`sim-rrf`·`sim-best` / `hist-mean`·`hist-best`, `sim-best` = `sim-rrf`, `hist-best` = `hist-mean`). 새 주제 질의 8개를 인코딩할 때만 임베딩 서버를 띄우고(백그라운드) 끝나면 내린다 → 라벨을 `/home/pollux/chaekbang-backups/labels-<시각>-before-holdout-supplement/`에 백업하고 경로를 알림 → 보충 라벨 → 표본 검수 ②(20건, `review --holdout --sample`, 30% 이상 고치면 멈춤) → 같은 명령으로 최종 두 번(확인: 두 실행이 같음, 표본 일치율과 "방향이 같음 / 반대 / 차이 없음"을 결과에 적음, 이 결과로 기본값을 바꾸지 않음)
- [x] 1.2 (D.4) 결과 문서는 8절에서 함께 쓴다: `add-loan-signals`의 남은 9.1(CLAUDE.md 현재 단계, docs/design.md 결과 한 줄·주차 표, README 결과 표)과 9.2·9.3(시나리오 점검, pytest, ruff). D.1·D.2를 `add-loan-signal-store`로 옮겼다는 것과 그 호출 수(11회)·대상 ISBN을 CLAUDE.md 현재 단계와 보고서 9절에 적는다(확인: 8.1·8.4가 끝나면 체크)

## 2. 제품 service와 근거

- [x] 2.1 `related.py`에 벡터 근거만 있는 책의 최소 유사도(`SimilarSettings.min_vector_similarity`, 기본 `None`)를 더한다. 규칙 근거가 있는 책은 빼지 않고 뺀 자리를 채우지 않는다(확인: 스펙 "벡터 근거만 있는 책의 최소 유사도" 시나리오 셋의 테스트, 기본값에서 기존 테스트와 기준 실행 결과가 같음)
- [x] 2.2 근거 코드와 문구 함수(코드 → 문구, 시리즈 → 지은이 → 분류 → 내용 → 인기 순, 두 개 상한, 분류는 표시 KDC 세목)를 만든다(확인: 스펙 "근거 문구" 시나리오 넷의 테스트)
- [x] 2.3 `app/library/hooks.py`에 관련 책 범위 제공자 등록(`related_scope`)을 더한다. 등록된 조건을 모두 AND로 건다(확인: 스펙 "관련 책의 기관 개별 범위" 시나리오 둘의 테스트, 제공자 없을 때 범위를 더하지 않음)
- [x] 2.4 `app/library/services/related.py`: `similar_for_book`(찾을 수 있는 기준 책만, 설정 모델 이름, 대출 신호 공급 없음, 범위 훅 + `within`)과 `related_for_session`(세션의 책 → `find_from_history`, 인기는 우리 도서관만)을 만들고, 결과를 요약(`build_summaries`와 같은 값) + 근거로 바꾼다(확인: 스펙 "제품 경로의 설정" 시나리오 셋, 다른 기관 기준 책·추천할 수 없는 기준 책 404, 결과의 기관 분리 테스트, `find_similar` 기본 설정과 같은 순서)
- [x] 2.5 `app/library/README.md`의 비슷한 책·최근 기록 절과 구성 표를 고친다("REST와 tool에는 아직 잇지 않았다" 문장, `services/related.py`, 범위 훅, 문턱 설정)(확인: 문서에 남은 "아직 잇지 않았다"가 주제로 찾기·`similar_books` 설명뿐임)

## 3. 비슷한 책 API

- [x] 3.1 `GET /catalog/books/{library_book_id}/similar`와 응답 스키마(`RelatedBook`: 찾기 결과 항목 + `basis`, `basis_text`)를 만든다. 라우터는 service만 부른다(확인: 스펙 "비슷한 책 API" 시나리오 여섯과 "비슷한 책 API는 기록하지 않음"의 테스트, Swagger에 보임)

## 4. 실행 값과 대화 세션의 책

- [x] 4.1 `ToolContext.values`(읽기 전용, 기본 빈 값)와 `run(..., tool_values=...)`를 더한다. 실행 기록에 남기지 않는다(확인: 스펙 "실행 값 주입" 시나리오 넷의 테스트, 기존 runner 테스트 통과)
- [x] 4.2 `app/agent/README.md`에 실행 값을 적는다(확인: 실행기가 값의 뜻을 모른다는 규칙이 적힘)
- [x] 4.3 개발 DB를 `pg_dump`로 `/home/pollux/chaekbang-backups/chaekbang-<시각>-before-related-books.dump`에 백업한다(명령은 `&&`로 잇는다). 그 뒤 `chat_messages.library_book_ids integer[] NOT NULL DEFAULT '{}'` 마이그레이션과 모델 칸을 만든다(확인: upgrade·downgrade·다시 upgrade, autogenerate 차이 없음, 스펙 database-schema "대화 메시지의 책 id 칸" 테스트, 백업 경로를 알림)
- [x] 4.4 `services/chat.py`가 이용자 행에 고른 책·찾은 책 id를, 답 행에 카드가 된 추천 책 id를 쓰고, 세션의 책(최신 순 서로 다른 3권, 이번 턴 포함, 그 세션·그 기관만)을 골라 실행 값으로 넘긴다(확인: 스펙 chat-sessions "저장 내용" 시나리오 다섯, librarian "대화 세션의 책" 시나리오 다섯의 테스트, 세션 삭제 뒤 행이 없음)

## 5. AI 사서 tool

- [x] 5.1 `app/library/tools.py`에 `related_tool` factory와 `FIND_RELATED_BOOKS`(입력 `library_book_id: int | None`, `record_fields=("library_book_id",)`, 결과는 `search_result` + `basis_text`, 빈 결과면 note)를 만든다(확인: 스펙 "관련 책 tool" 시나리오 여섯의 테스트, 가짜 LLM으로 tool 호출)
- [x] 5.2 `build_librarian_profiles`에 tool을 더하고 BASE_PROMPT에 관련 책 문구(비슷한 거 → id, 아무거나 → 비움, 이유는 `basis_text`와 소개만)를 넣고 `PROFILE_VERSION`을 올린다(확인: 스펙 librarian "조회 tool"의 "프로필의 관련 책 tool" 테스트, 프롬프트 스냅샷 테스트가 있으면 갱신)
- [x] 5.3 `app/library/README.md`의 AI 사서 절에 tool과 세션의 책을 적는다(확인: tool 목록과 구성 표가 코드와 같음)

## 6. 어린이 기능

- [x] 6.1 `app/features/children/tools.py`에 `find_related_children_books`(같은 factory, 범위만 어린이 도서)를 더하고, 어린이 요청 판단의 tool 이름을 집합으로 바꾸고, 프롬프트 문구에 어린이 "비슷한 거"를 더한다(확인: 스펙 children "어린이 관련 책 tool" 시나리오 셋, "어린이 요청 판단"의 새 시나리오와 기존 시나리오 테스트)
- [x] 6.2 어린이 범위 제공자(기준 책이 모두 그 기관의 어린이 도서이면 어린이 도서로)를 만들어 `app/main.py`에서 등록하고, 서버를 거치지 않는 진입점(`evals/librarian`)에도 같은 등록을 넣는다(확인: 스펙 "어린이 기준 책의 관련 책 범위" 시나리오 넷의 테스트, 평가 진입점의 등록 테스트)
- [x] 6.3 `app/features/README.md`에 어린이 관련 책 tool과 범위 제공자를 적는다(확인: 문서와 등록 코드가 같음)

## 7. 문턱 진단과 평가 시나리오

- [x] 7.1 문턱 진단 스크립트(`evals/recommendation`의 하위 명령 또는 모듈): `sim-rrf` 상위 10권 중 벡터 근거만 있는 책의 코사인을 라벨 등급별로 세고, 0.30~0.80(0.01 간격)에서 design 결정 10의 규칙(조정에서 0 라벨 절반 이상 뺌, 2 라벨 5% 이하만 뺌, 확인 세트 같은 방향)을 본다. 새 라벨은 달지 않는다(확인: 진단 표를 design "결과"에 적음, 테스트 DB의 작은 세트로 규칙 함수 테스트)
- [x] 7.2 7.1에서 문턱이 정해지면 기본값으로 두고 비슷한 책 세트를 같은 명령으로 짝 비교해 nDCG@5가 떨어지지 않는지 본 뒤, 스펙 delta "벡터 근거만 있는 책의 최소 유사도"의 기본값을 고치고 알린다. 정해지지 않으면 `None` 그대로 적는다(확인: 결과에 적음)
- [x] 7.3 `evals/librarian`에 시나리오 넷(고른 책 → 비슷한 거, 아무거나, 어린이 그림책 → 비슷한 그림책, 근거를 지어내지 않음)과 채점(tool 이름·입력, 추천이 tool 결과 안, 어린이 도서만)을 더한다(확인: 가짜 LLM으로 시나리오 틀과 채점 함수 테스트)
- [x] 7.4 시나리오를 실제 LLM으로 돌릴지 묻는다: 호출 수(시나리오 수 × 반복 × 턴당 평균 LLM 호출)와 예상 비용(`LLM_PRICES`, 기본 `gpt-6-luna`)을 세어 알리고, 승인을 받은 뒤에만 돌린다. 승인이 없으면 돌리지 않았다고 결과에 적는다(확인: 결과에 적음)

## 8. 문서와 마지막 점검

- [x] 8.1 `CLAUDE.md`(현재 단계, MVP 순서에 `add-topic-search-tool`을 `add-related-books`와 `add-recommendation-evals` 사이에, 약관 확인 뒤 항목으로 `add-loan-signal-store`(대출 테이블, D.1·D.2)를 더함, 디렉터리 구조, 명령), `docs/design.md`(결과 한 줄, 주차 표), `evals/recommendation/README.md`(미룬 일 결과 표, 문턱 진단), `docs/reports/search-recommendation-strategy.md`(1절 제품 연결, 9절 남은 일)를 고친다(확인: 문서의 기본값·명령이 코드와 같음)
- [x] 8.2 모든 스펙 시나리오가 테스트(또는 `evals/` 시나리오)로 확인되는지 점검한다. 테스트 이름이나 docstring에 요구사항을 적는다(확인: 시나리오 → 테스트 목록을 design "결과"에 적음)
- [x] 8.3 대량 삽입·롤백을 한 테스트가 있으면 테스트 DB `VACUUM ANALYZE` 뒤 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `openspec validate add-related-books --strict`(확인: 모두 통과)
- [x] 8.6 (구현 중 더함) 찾기 속도 테스트(`tests/library/test_book_lookup_speed.py`)가 전체 실행에서만 실패했다(같은 앞 테스트들이 `main`에서는 42초에 통과, 이 브랜치에서는 속도 테스트 하나가 78초). 앞선 테스트의 롤백 뒤 자동 ANALYZE가 빈 표를 통계로 남긴 것으로 보고, 테스트가 넣은 행 뒤에 `ANALYZE library_books, holdings, books`를 부른다(확인: 같은 묶음 1148 통과, 44초)
- [x] 8.4 `uv run python -m evals.catalog_search`와 similar·history 기준 실행을 다시 돌려 0.1과 같은지 본다. 7.2에서 기본값을 바꿨으면 바꾼 변형 말고는 같아야 한다(확인: run 이름을 결과에 적음)
- [x] 8.5 무엇을 했는지 요약하고 멈춘다. PR 제목·본문 텍스트를 준다(push·PR 생성은 하지 않음)

## Workflow follow-up

- 구현 전에 issue 제목·본문(design 요약)을 텍스트로 주고 issue 번호를 받는다.
- 커밋은 사용자가 말할 때만 한다.
- 사용자가 확인한 뒤 `/opsx:archive`로 archive한다.
