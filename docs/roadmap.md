# 로드맵

change 순서와 상태, 실험으로 확정된 기본값, 미룬 일을 한곳에 둔다. change를 archive할 때 이 문서를 고친다(상태, 확정된 기본값, 미룬 일). `CLAUDE.md`의 "현재 단계"는 세 줄만 두고 이 문서를 가리킨다.

수치의 근거는 각 change의 `design.md` "결과"에 있다. 경로가 `archive/`인 것은 `openspec/changes/archive/<날짜>-<change>/design.md`다. 추천 실험의 라벨은 Claude가 초안을 달고 사람이 일부만 검수한 것이라, 수치는 방식끼리의 상대 비교에만 쓴다. 전체 흐름은 `docs/reports/search-recommendation-strategy.md`에 정리돼 있다.

## change 순서와 상태

MVP는 약 8주다. 이전 방향(무인 서점)의 1주차 결과는 저장소 기록에 남기고, 새 1주차 change에서 모델과 스펙을 새 도메인으로 정리했다. 원래 한 주에 change 하나였지만 나눠지면서 주차 숫자는 다시 정한다. 2주차는 외부 API 정보와 구조 변경 때문에 넷, 3주차는 분량 때문에 둘, 4주차는 검색과 추천을 나누면서 넷이 됐다. 2026-11-12에는 `add-related-books` 앞에 추천 실험의 바탕(저장 구조와 정규화, 실험, 출처 일반화)을 두었다.

| # | change | 내용 | 완료 기준 | 상태 |
| --- | --- | --- | --- | --- |
| 1 | `add-library-core-domain` | 이전 도메인 정리, 모델, 기관 분리, 관리자·키오스크 인증, 장서·대출 CRUD, 시드 데이터 | Swagger에서 대출·반납 동작, 다른 기관 데이터가 보이지 않음 | 끝남 |
| 2 | `add-holdings-import` | 기존 시스템 엑셀·CSV 장서 가져오기, 파일 근거 어린이 도서 분류 | 가상 내보내기 파일로 장서가 채워지고 어린이 분류 결과가 나옴 | 끝남 |
| 3 | `add-library-catalog-layer` | 공식 서지와 기관 도서 분리, 기관별 어린이 구분 | 한 기관의 수정이 다른 기관에 영향을 주지 않음 | 끝남 |
| 4 | `add-book-enrichment` | YES24 연동, 운영자의 공식 서지 채움, 기관의 외부 분류 근거 | 소장 도서의 소개·표지가 채워짐 | 끝남 |
| 5 | `refactor-layer-packages` | 운영자·기관 공통·기관 개별 패키지 분리, 어린이 기능 분리 | 의존 방향을 테스트가 강제하고, 어린이 기능 없이 공통이 동작함 | 끝남 |
| 6 | `add-agent-runner` | 공통 실행기, tool 계약, 프로필, LLM 접점, 실행 기록, 최종 검사 자리 | 가짜 LLM으로 루프와 검사가 동작하고 기관 패키지 없이 불러짐 | 끝남 |
| 7 | `add-librarian-agent` | AI 사서 v1: 조회 tool, 어린이 검사, 대화 API와 SSE, 추천 노출 기록 | "공룡 책 추천해줘"에 소장 도서로 답함 | 끝남 |
| 8 | `add-catalog-search` | 서명·저자 찾기(오타 허용), 자동완성, 검색 API, 대화와 잇기(고른 책, 찾은 책 카드), 검색 평가 | 오타 질의도 5위 안에 찾고, 고른 책은 LLM 없이 카드가 나옴 | 끝남 |
| 9 | `add-library-guide` | 도서관 안내 정보(운영 시간, 휴관일, 대표 연락처, 시설 위치, 이용 규칙), 반납 예정일 계산, 안내 tool | 등록된 안내로만 답하고 날짜는 코드가 계산함 | 끝남 |
| 10 | `add-book-embeddings` | 도서 임베딩 파이프라인: pgvector, 로컬 임베딩 서버(TEI), 인코더 접점, 임베딩 텍스트, 전체·증분 적재 CLI | 표본 87권이 적재되고 증분 재실행은 0건, 질의의 상위 5권이 나옴 | 끝남 |
| 11 | `add-book-contributors` | 정규화 통일(저장용·비교용, 이름·역할·KDC·시리즈명), 공식 서지 기여자 표, 기관 도서 저자 키, YES24·기관 파일 저자 해석기 | 표본 87권의 저자 표기가 역할별로 풀리고, 모든 쓰기 경로가 저자 키를 채움 | 끝남 |
| 12 | `add-official-book-embeddings` | 벡터 두 층(공식 서지 벡터, 기관 도서 벡터), 실험 장서(YES24 525권과 가상 기관), 적재 배치 기본값 | 두 층으로 적재·조회가 되고 개발 DB에 실험 장서와 텍스트 버전 2 임베딩이 있음 | 끝남 |
| 13 | `add-recommendation-experiments` | 추천 실험: 실험 틀, 평가 세트와 라벨(초안+검수), 주제로 찾기 변형 비교, 임베딩 텍스트 종류 비교와 기본 확정 | 주제로 찾기의 변형 점수표와 기본 설정, 임베딩 텍스트 기본 확정 | 끝남 |
| – | `fix-korean-title-order` | 서명 가나다순 정렬(`korean_order`) | 서명 정렬이 가나다순 | 끝남 |
| 14 | `add-related-book-experiments` | 비슷한 책(같은 저자·시리즈·분류·벡터 이웃)과 아무 조건 없음의 신호와 변형 비교, 두 세트의 라벨 | 두 요청 종류의 변형 점수표와 기본 설정 | 끝남 |
| 15 | `add-bibliographic-sources` | 카카오·정보나루 연동: 세 출처의 필드별 기준 출처, 채움 일반화, 부가기호 어린이 근거, 실험 장서 다시 채우기, 같은 ISBN 다른 메타데이터 비교 | 세 출처와 YES24 뺀 상태의 점수 비교 | 끝남 |
| 16 | `add-loan-signals` | 정보나루 대출 신호: 같은 KDC 세목 실측, 함께 대출, 인기 대출, 빈 기록의 "아무거나", 남겨 둔 분야 비교 | 대출 신호의 변형 점수표 | 끝남(D.1·D.2는 미룸) |
| 17 | `add-related-books` | 이긴 설정을 제품에 내보내기: 찾은 책 카드 아래 비슷한 책(LLM 없음), AI 사서 tool, REST. 미룬 일 D.3·D.4 | 찾은 책 아래 비슷한 책이 LLM 없이 나옴 | 끝남 (issue #41) |
| 18 | `add-topic-search-tool` | 주제로 찾기(`hybrid-k60`)를 AI 사서에 잇기: 서비스 중 임베딩 서버, 꺼졌을 때 키워드 검색, LLM 평가 전후 비교 | 주제 요청이 키워드+벡터 순위로 답하고 평가가 나빠지지 않음 | 끝남 (issue #44) |
| 19 | `add-recommendation-evals` | 대화 추천 평가(LLM 포함): 실험 장서 60항목을 실제 대화로, 기존 어울림 라벨로 카드 Hit@5·Recall@5·nDCG@5(묶음별), 실행 사이 비교, 실제 LLM 낱말 다시 보기, `related-anything` 판정. MVP 우선으로 어린이 지표 둘·모델 비교 등은 뺌(아래 미룬 일). LLM 채점은 최종 서비스 테스트에서 | 버전별 점수표 | 끝남 (issue #46) |
| 20 | `add-admin-agent` | 운영 에이전트, 자연어 SQL 분석과 안전장치, 장서 등록 | 분석 질문 정답률 측정 | **다음** |
| 21 | `add-approval-flow` | 큐레이션·연체 안내·구매 요청서 초안 → 승인 → 실행 | 서버 재시작 후에도 승인 이어짐 | |
| 22 | `add-librarian-actions` | 대출·반납·희망도서 tool, 회원번호 입력, 운영 방식에 따른 tool 끄기 | 회원번호가 대화 기록과 LLM에 남지 않고 대출됨 | |
| 23 | `add-web-ui` | 이용자·관리자 화면 | 이용자 대화에서 추천·대출까지, 관리자 승인까지 화면으로 동작 | |
| 24 | `add-observability-deploy` | Langfuse 트레이싱, 배포, README, 데모 | 데모 영상과 평가 결과표 | |
| – | `add-loan-signal-store` (가칭) | 함께 대출·정보나루 인기의 운영자 층 테이블과 갱신 실행, 제품의 대출 신호 공급, 미룬 일 D.1·D.2 | | 정보나루 약관 확인 뒤, 순서 미정 |

**2단계**: 독립서점 모드(대출 대신 서가 안내·구매 문의), 시즌 큐레이션 제안, 대출 이력 기반 개인화(동의한 회원만). 그 밖의 메모는 `docs/backlog.md`.

## 확정된 기본값

제품과 실험이 따르는 설정이다. 바꾸려면 같은 실험 틀에서 채택 규칙을 넘어야 한다.

| 항목 | 기본값 | 근거 |
| --- | --- | --- |
| 검색과 추천 | 나눈다. 아는 책 찾기(오타 허용, 자동완성)는 LLM 없이 코드로 하고, LLM은 자연어로 책을 찾는 대화와 도서관 안내를 맡는다 | `add-catalog-search` |
| 서명 정렬 | 가나다순. DB 기본 collation(`en_US.utf8`)은 그대로 두고 정렬 키에만 ICU `ko-x-icu`를 건다(`app/core/text.py`의 `korean_order`) | `archive/…-fix-korean-title-order` |
| 임베딩 텍스트 | 텍스트 버전 2, 종류 `full`: 저자를 뺀 서명·분류·소개. 저자는 기여자·저자 키와 서명·저자 찾기가 맡는다. 저자 넣기(`with_author`), 소개만, 필드별 벡터는 이기지 못했다(2026-11-16 확정) | `archive/…-add-recommendation-experiments` |
| 임베딩 실행 | ONNX 변환본, 적재 배치 기본값 4(32에서 내림). 서비스 중 질의 인코딩은 시간 제한 2초, 실패 뒤 30초 쉬기, 처음 한 번 모델 확인(`GuardedEmbedder`). 서버가 없으면 AI 사서 검색은 키워드 순위로 내려간다 | `app/central/README.md`, `archive/…-add-book-embeddings` Open Questions, `add-official-book-embeddings`, `archive/…-add-topic-search-tool` |
| 주제로 찾기 | `hybrid-k60`: 키워드 순위와 벡터 순위를 RRF(k 60, 1:1)로 합친다. 조정 nDCG@5 0.410 → 0.517. 서명 가나다순 뒤 기준은 0.453 → 0.519. 남겨 둔 분야 +0.097(4·3·1). **벡터 질의는 LLM 낱말**(`hybrid-best`): 합친 순위에서 문장과 차이 없음(세 출처 조정 -0.027, 4·7·9, -0.078 ~ +0.024)이고 여러 턴·다시 찾기 때문에 골랐다(2026-11-17). **실제 LLM 낱말로 다시 쟀다**(대화 평가가 받은 낱말, 조정 +0.034, 7·7·6, -0.009 ~ +0.081, 확인 +0.039, 9·0·1): 차이 없음이라 낱말 그대로(2026-11-17). 시리즈 묶기·MMR은 끈다(LLM이 10권 중 고른다). 결과를 비우는 문턱 없이, 키워드 순위가 비면 `note`로 알린다. 제품에 이었다: AI 사서 `search_collection`·`search_children_books`(`services/topic.py`), 평가 전후 나빠지지 않음 | `archive/…-add-recommendation-experiments`, `archive/…-add-related-book-experiments`, `archive/…-add-topic-search-tool`, `archive/…-add-recommendation-evals` |
| 비슷한 책 | `sim-rrf`: 기준 책의 저장된 벡터로 찾는 벡터 이웃(`full`)에 같은 시리즈·같은 저자·같은 KDC 세목 신호를 RRF 1:1로 합친다. KDC 세목 신호가 들어오면서 처음 채택 규칙을 넘었다(세 출처 +0.052, 대출 신호 때 +0.053). 시리즈·저자 신호는 품질이 같아도 근거 표시를 위해 둔다(사용자 결정). 시리즈 묶기, MMR, 같은 외부 분류로 좁히기, KDC 세 자리·계층 단위, 세목 안 벡터 순, 함께 대출(+0.017)은 쓰지 않는다. 남겨 둔 분야는 -0.004(차이 없음, KDC 세목 신호가 거의 없음) | `archive/…-add-related-book-experiments`, `archive/…-add-bibliographic-sources`, `archive/…-add-loan-signals` |
| 최근 기록 | `hist-mean`: 기록 책 벡터의 평균. 책별 순위를 RRF로 합친 것을 모든 기록에서 이겼다(조정 nDCG@5 0.694 대 0.334). KDC·저자·함께 대출 신호는 넘지 못했다 | `archive/…-add-related-book-experiments`, `archive/…-add-loan-signals` |
| 최소 유사도 | 벡터 근거만 있는 책에 문턱을 두지 않는다(0·2 라벨의 코사인이 겹침) | `archive/…-add-related-books` |
| 시리즈 | 상한 1을 켜지 않는다. 시리즈 다음 권(권차)은 미룬다 | `add-related-books` |
| 아무 조건 없음 | 대화 세션의 책 최신 3권으로 `hist-mean`. 세션에 책이 없으면 우리 도서관 인기. 대출 신호 공급이 없어서 지금은 우리 도서관 인기에서 끝난다 | `add-related-books` |
| 공식 서지 출처 | 정보나루·카카오·YES24를 필드별 순서로 합친다(`app/central/sources.py`의 `merge`). YES24를 빼면 대체로 낮다(최근 기록 조정 -0.224). 순서는 `docs/data-sources.md` | `archive/…-add-bibliographic-sources` |

## 미룬 일

- **D.1** (`add-loan-signals`에서 미룸, `add-loan-signal-store` tasks 맨 앞): 정보나루가 막혀 받지 못한 남은 11회. 이용 분석 `9791199489509`·`9791199491717`(조정 기준 책 `s10`)·`9791199509009`와 인기 8조건으로, 하루 500건의 2.2%다. 인기 기간도 함께 정한다. 부르기 전에 호출 수를 세어 사용자 승인을 받는다. change의 끝을 외부 API가 풀리는 때에 묶지 않으려고 나눴다(2026-11-17 사용자 요청).
- **D.2** (같은 곳): `s10`을 넣어 함께 대출 변형을 다시 잰다.
- D.3(남겨 둔 분야 실행)과 D.4(결과 문서)는 `add-related-books`에서 했다.
- 함께 대출은 제품 신호 코드(`co_loan`), 정보나루 인기 채우기, 빈 기록 규칙만 있다. 제품 테이블은 약관 확인 뒤에 만든다.
- 시리즈 묶기(주제로 찾기)는 `add-topic-search-tool`에서 끄기로 정했다. 같은 시리즈만 추천하는 답이 대화 추천 평가에서 문제로 나오면 다시 연다.
- `add-recommendation-evals`에서 끝낸 것: 실제 LLM 낱말로 벡터 질의 입력 다시 보기(낱말 그대로), `related-anything` 검사 판정(아무거나 뒤 검색 허용). 기준 점수는 프로필 v6, `gpt-6-luna`에서 카드 nDCG@5 0.578·0.575, Hit@5 0.783·0.800(`archive/…-add-recommendation-evals/design.md` 결과). 비슷한 책·아무거나는 카드가 tool 앞 5권보다 낮다(LLM이 3권쯤 냄). 카드 수를 바꿀지는 정하지 않았다.
- **MVP 뒤**(2026-11-17 사용자 결정, MVP 출시가 우선이라 `add-recommendation-evals`에서 뺌)
  - 어린이 지표 둘: 책 분류(어린이로 분류한 책의 정밀도·놓친 비율, 장서 쪽)와 요청 판단(어린이 요청을 맞게 판단한 비율, 어른 요청을 어린이로 좁힌 오판 비율). 섞인 기록(어린이 + 일반)에 어린이 조건을 걸지(보고서 OQ3). 근거는 `openspec/changes/archive/2026-11-10-add-librarian-agent/tasks.md` 끝
  - 모델 비교(`LLM_PRICES`의 다른 모델), 사람만 단 라벨 표본으로 Claude 라벨과의 일치도
  - 소장 도서가 없는 주제 세트와 빈 결과 규칙(보고서 OQ1. 대화 평가 두 실행에서 키워드 순위가 빈 검색은 0번)
  - 비슷한 책 API 노출 기록의 출처 칸, 평가 표본 87권의 세 출처 전환(보고서 OQ6)
  - 테스트 DB 실험 장서(어린이 169권)와 개발 DB 실험 기관(152권)의 어린이 구분 차이: 개발 DB는 세 출처를 합치기 전에 넣은 책의 어린이 구분을 고치지 않았다. 어린이 구분 지표를 만들 때 본다
