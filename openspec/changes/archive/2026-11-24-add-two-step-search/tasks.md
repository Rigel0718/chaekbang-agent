순서: 1은 서버(주제 검색 REST), 2~4는 화면(갈림과 두 단계 블록, 소스 검사, 모양과 문서), 5는 통합 확인이다. 스키마와 추천 기준값은 바꾸지 않는다. 설계와 다르게 만들어야 하면 멈추고 스펙 delta부터 고친 뒤 알린다(MVP 우선, 범위를 늘리지 않음).

모델 분리: **1·2·5는 Opus**(서버 경계와 기관 분리, 화면 갈림·비동기 순서, curl 확인), **0·3·4는 Sonnet**(기준 측정, 소스 검사, CSS·문서). 넘칠 때 나누는 경계는 1과 2 사이다(1만으로 REST가 닫힌다).

## 0. 시작 전 기준 (Sonnet)

- [x] 0.1 `uv run pytest`, `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 1. 주제 검색 REST (Opus, design 결정 1·4)

- [x] 1.1 `app/library/services/topic.py`에 질의 글을 공백으로 나눠 낱말로 만들고, 정리 뒤 낱말이 없으면 인코더를 부르지 않고 빈 결과, 아니면 `search_by_topic`을 그대로 부르는 함수를 더한다(확인: service 테스트 — 여러 공백으로 나뉜 질의가 낱말 목록으로 넘어감, 공백·문장부호만이면 빈 결과와 인코더 호출 0번)
- [x] 1.2 `app/library/api/catalog.py`에 `GET /catalog/topic`(`QueryText`, `CurrentStaff`, `QueryEncoder`, 응답 `list[BookSummary]`, `build_summaries`)을 더한다. docstring에 LLM 없음·기록 없음·내려가기를 적는다(확인: 1.3의 테스트)
- [x] 1.3 새 `tests/library/test_topic_api.py`: 스펙 "주제로 찾기 API"의 시나리오 6개(제품 경로와 같은 결과 — 같은 `FakeEmbedder`, 인코더 실패 — `EmbeddingError` 가짜 인코더, 낱말 없음, 토큰 없음 401, 잘못된 질의 422, 요청의 기관 값 무시)와 "주제로 찾기 API는 기록을 남기지 않음"(세 테이블 행 수)을 테스트로 둔다. 인코더는 `get_query_encoder` 덮어쓰기로 바꾼다(확인: `uv run pytest tests/library/test_topic_api.py` 통과)
- [x] 1.4 `app/library/README.md`: 구성 표 `api/catalog.py` 행에 `GET /catalog/topic`, `services/topic.py` 행에 새 함수, "주제로 찾기 > 제품 경로"에 REST도 이 함수를 감싼다는 줄(낱말은 공백으로 나눔, 빈 낱말이면 빈 목록)을 더한다(확인: 문서의 경로·함수 이름이 코드와 같음)

## 2. Enter 갈림과 두 단계 블록 (Opus, design 결정 2·3)

- [x] 2.1 `shared/api.js`에 `topic: (q, signal) => query("/catalog/topic", q, signal)`을 더한다(확인: 3.1의 경로 테스트)
- [x] 2.2 `librarian/chat.js`에 두 단계 블록(위 단 상수 2권, 아래 단 "관련된 책을 찾는 중…" → 주제 결과에서 위 단 id 제외, 비거나 실패면 제목째 지움, 401은 `onUnauthorized`, `summary` 카드, 저절로 펼치지 않음, [사서에게 물어보기]는 `sendText`가 받아들이면 꺼짐)을 더하고 내보낸다(확인: 3.1의 권수 테스트, B1·B2·B5·B9·B12는 5.3에서)
- [x] 2.3 `librarian/main.js`의 `submit()`을 갈림으로 바꾼다: 100자 초과면 바로 `sendText`, 아니면 `/catalog/search` → 1권 이상이면 두 단계 블록, 0권·실패(401 빼고)면 `sendText`, 401이면 로그인 화면. 찾기 요청 중에는 Enter를 무시한다. `suggest.js` 머리 주석의 Enter 설명을 고친다(확인: 3.1의 상한 테스트, 기존 web-ui 테스트 통과, B3·B4·B6·B10·B11·B13은 5.3에서)

## 3. 화면 소스 검사 (Sonnet, design 결정 4)

- [x] 3.1 `tests/platform/test_web_ui.py`: `ALLOWED_CALLS`에 `/catalog/topic`을 더하고(스펙 "화면이 부르는 경로"), 두 단계 상한 상수가 `app.library.api.catalog.MAX_QUERY_LENGTH`와 같은지(스펙 "긴 입력"), 위 단 권수 상수가 2인지(스펙 "위 단 권수") 보는 테스트를 더한다(확인: `uv run pytest tests/platform/test_web_ui.py` 통과)

## 4. 모양과 문서 (Sonnet)

- [x] 4.1 `librarian/librarian.css`에 두 단 제목, 단 사이 간격, [사서에게 물어보기] 모양을 기존 `.results` 블록에 맞춰 더한다(확인: B1에서 두 단이 구분돼 보임)
- [x] 4.2 `app/web/README.md`: 구성 표의 `chat.js` 설명에 두 단계 블록, 규칙의 경로 목록에 주제 검색 `/catalog/topic`, 새 규칙 한 줄(Enter는 서명·저자 찾기 먼저, 1권 이상이면 두 단계, 0권·100자 초과·실패면 AI 사서), 시험 절의 B 목록 change에 `add-two-step-search`를 더한다(확인: 문서의 경로·파일 이름이 코드와 같음)

## 5. 통합 확인 (Opus)

- [x] 5.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` 통과를 design "결과"에 적는다(확인: 0.1보다 테스트 수가 늘고 실패 없음)
- [x] 5.2 curl(design 결정 5): 실험 기관 키오스크 토큰으로 `GET /catalog/topic?q=채식`이 200이고 채식주의자를 포함하는지 임베딩 서버를 켠 상태·끈 상태 둘 다, 토큰 없이 401을 확인해 "결과"에 적는다. LLM·외부 API 호출 0회(확인: 기록한 응답)
- [x] 5.3 사용자에게 B1~B13(design "사용자 확인 항목")을 넘기고 결과를 "결과"에 적는다. 바꾼 곳이 있으면 해당 B를 다시 확인받는다(확인: 사용자 확인 끝)

## Workflow follow-up

- 사용자가 확인한 뒤 커밋은 요청받을 때 하고, PR은 제목·본문 텍스트만 준다(push 안 함).
- archive 전에 `docs/roadmap.md`를 고친다: 24d 상태 끝, "화면 확인에서 나온 개선 사항" 첫 줄에 24d에서 해결 표시, 새 절 "`add-two-step-search`에서 미룸"(design의 미룰 것 8가지, Playwright는 기존 줄에 합침).
- `CLAUDE.md` "현재 단계"를 다음 24e `add-member-login`으로 고친다.
- 메모리 `two-step-search-plan`에 archive 결과를 적는다.
