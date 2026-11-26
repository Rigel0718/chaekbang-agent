## Context

- 공통 실행기(`app/agent/runner.py`)는 `StatusEvent`, `AnswerEvent`, `DoneEvent`만 낸다. tool 결과는 `ToolResult`로 LLM에게만 가고, 러너 스펙이 결과를 사건에 넣는 것을 막는다.
- `app/agent/`는 어떤 tool이 있는지 모른다. tool이 고르고 실행기는 따르는 선례로 `Tool.record_fields`(기록에 남길 입력)와 `AnswerTool.record_fields`가 있다.
- 분석 tool 넷(`app/library/analytics_tools.py`)은 service 결과 모델(`schemas/analytics.py`, 필드 허용 목록 테스트 있음)을 `model_dump(mode="json")`한 dict를 돌려준다. 초안 tool 셋은 id·상태·안내 문구(`note`)를 돌려준다.
- `services/admin_chat.py`의 `stream_admin_turn`은 실행 사건을 SSE `session`, `status`, `answer`, `done`으로 옮기고, `chat_messages`에는 가린 질문과 답 문장만 둔다. AI 사서 대화(`services/chat.py`)도 같은 실행기 사건을 `isinstance`로 고른다. 평가 러너(`evals/admin_agent/runner.py`)는 SSE 사건을 이름별 dict로 모은다.
- 관리자 화면 `admin/chat.js`는 답 문장만 그린다. `admin/main.js`는 주소 hash가 탭 이름과 같을 때만 그 탭을 열고, `admin/approvals.js`는 펼친 줄을 `open = {kind, id}`로 기억하지만 불러올 때마다 비운다.

## Goals / Non-Goals

**Goals:** 실행기는 tool을 모르는 채로 tool이 고른 화면용 값만 통과한 답과 함께 내보낸다. 화면은 일반 모양 둘(표, 초안)만 안다.

**Non-Goals:** 지금 분석 결과 모델과 분석 service의 변경, 프롬프트 변경(v4 유지), DB 스키마 변경, 새 REST, 차트 라이브러리, AI 사서 쪽 동작 변경.

## Decisions

### 1. 보일 결과(탐색 결정 1)
분석 tool 넷과 초안 tool 셋만 변환을 고른다. 연체 목록은 [오늘의 연체] 탭이 있고, 구매 후보는 구조가 네 갈래라 크며, 소장 도서 검색은 초안 링크로 충분해서 미룬다. 장서·대출 묶음만 막대를 그린다.

### 2. 실행기: `Tool.present`와 모아서 내기(탐색 결정 2)
- `Tool`에 선택 칸 `present: Callable[[ToolInput, Any], BaseModel | None] | None = None`을 둔다. 입력은 검증한 tool 입력과 handler 반환값이다. 입력을 함께 받는 이유는 분야 필터(`fields`)가 결과 모델에 없고 입력에만 있기 때문이다.
- `runner.py`에 `ResultEvent(value)`를 더하고 `RunEvent`에 넣는다. `run_tool`이 성공하면 `present`를 불러, 없음이 아니면 실행 안 목록에 쌓는다. 도메인 오류·입력 검증 오류로 끝난 호출은 부르지 않는다.
- `end(answer, status)`는 상태가 `completed`나 `repaired`일 때만 쌓인 값을 `ResultEvent`로 낸 뒤 `AnswerEvent`, `DoneEvent`를 낸다. 고정 답·실패·거절·중단이면 내지 않는다. 기록을 끝낸 뒤 내보내는 지금 순서(소비자가 멈춰도 중단으로 남지 않음)는 그대로다.
- `present`가 예외를 내면 tool 예외와 같이 실행을 실패로 끝내고 고정 답을 낸다(이미 있는 `run()`의 예외 처리). 변환은 순수 함수라 단위 테스트로 막는다.
- 화면용 값은 `records`에 넘기지 않는다.
- 대안: (B) 실행 직후 바로 내고 받는 쪽이 거름은 거르는 규칙이 받는 쪽마다 흩어지고 고정 답 위에 표가 남는다. (C) `tool_values`에 빈 목록을 넣어 몰래 모으기는 "실행 값은 읽기 전용"을 우회한다. 둘 다 거절했다.

### 3. 화면용 모델(탐색 결정 3)
새 모듈 `app/library/schemas/admin_results.py`에 만든다. `schemas/admin_agent.py`는 프로필(`admin_agent.py`)을 import하고 프로필은 tool 파일을 import하므로, tool 파일이 쓰는 모델을 거기 두면 순환 import가 된다(구현 중 확인).

```python
class TableResult(BaseModel):
    kind: Literal["table"] = "table"
    title: str
    caption: str | None
    columns: list[str]
    rows: list[list[str | int | float | None]]  # 칸 수 == len(columns), 50줄 이하
    bar_column: int | None
    total: int | None
    truncated: bool


class DraftLink(BaseModel):
    kind: Literal["draft"] = "draft"
    draft: Literal["curation", "template", "purchase"]
    id: int


ResultPayload = Annotated[TableResult | DraftLink, Field(discriminator="kind")]
```

- 막대는 따로 종류를 두지 않고 표의 숫자 열 하나(`bar_column`)에 그린다. 막대 길이는 화면이 그 열의 최댓값으로 맞춘다.
- 대안: tool 결과를 그대로(`{"tool", "data"}`) 내면 화면이 분석 스키마 넷을 알아야 하고, 검사는 JS 소스 문자열로만 할 수 있다. 거절했다.

### 4. 변환 함수(tool 파일마다)

| tool | 언제 | 제목 | 열 | 막대 |
| --- | --- | --- | --- | --- |
| `get_collection_status` | `group_by`가 있을 때 | {머리}별 장서 | 묶음 이름, 사본, 서명 | 사본 |
| `get_loan_stats` | `group_by`가 `book`이 아닌 묶기일 때 | {머리}별 대출 | 묶음 이름, 대출(+분야면 사본, 권당 대출) | 대출 |
| `get_loan_stats` | `group_by = book` | 많이 빌린 책 | 순위, 서명, 저자, 대출 | 없음 |
| `list_holdings_by_status` | 늘 | 분실 사본 / 훼손 사본 / 대출 중 사본 | 서명, 저자, 등록번호, 청구기호 | 없음 |
| `list_unborrowed_books` | 늘 | 안 빌린 책 | 서명, 저자, 권수 | 없음 |
| `draft_curation` 등 셋 | 초안을 올렸을 때 | - | `DraftLink` | - |

- 제목의 {머리}와 묶음 이름 열의 머리는 `field` → 분야, `status` → 상태, `acquisition_type` → 입수 구분, 그 밖의 축(기관 개별 기능의 축) → 구분이다. 변환은 기능 이름을 부르지 않는다.
- 설명 줄은 기간 표기(`period.label`, 진행 중이면 "진행 중"을 덧붙임), 분야 필터("자연과학 기준", 여럿이면 쉼표), 외부 대출 기관 사본의 가장 늦은 `last_synced_at` 날짜("11월 20일 가져온 파일 기준")를 " · "로 잇는다. 없으면 null.
- 잘림은 결과의 `total`, `truncated`를 그대로 싣는다(순위는 `ranking.total`).
- 묶지 않은 장서·대출, 그리고 `current`(지금 대출 중·연체)는 표로 내지 않는다(답 문장에 있다).
- 초안 변환은 handler 반환 dict의 id만 읽는다. `note`, 제목, 항목은 버린다.

### 5. 개인정보(탐색 결정 4)
- 변환 함수의 입력은 tool 입력과 지금 분석 결과(허용 목록 모델)뿐이고 DB를 읽지 않는다. 회원 값이 들어올 길이 코드에 없다.
- 새 테스트: tool마다 나올 수 있는 열 이름을 고정한 허용 목록(`tests/library/test_admin_results_privacy.py`), 회원 이름·회원번호·전화번호가 서로 다르게 있고 대출·연체·희망도서가 있는 기관에서 모든 변환 tool을 돌린 결과 JSON에 그 값이 없음, 두 기관 중 한 기관의 결과에 다른 기관 서명·등록번호가 없음.
- 등록번호와 청구기호는 사본을 찾는 번호라 보인다(지금도 LLM 결과와 답에 나온다).
- 결과 사건은 로그·실행 기록·`chat_messages`에 남기지 않는다.

### 6. `admin_chat`(탐색 결정 7)
- `stream_admin_turn`이 `ResultEvent`를 받으면 `ServerEvent("result", value.model_dump(mode="json"))`로 바로 보낸다(실행기가 이미 답 바로 앞에 낸다).
- `chat_messages`는 지금 그대로 질문과 답 문장만이다. 다음 턴의 LLM은 지난 표를 보지 못하고, 이어지는 질문에는 tool을 다시 부른다.
- AI 사서(`services/chat.py`)는 변환을 고른 tool이 없어 `ResultEvent`가 오지 않는다. 오더라도 지금 `isinstance` 갈래가 무시한다.

### 7. 화면: 표와 막대(탐색 결정 5)
- `admin/chat.js`: `result`를 배열에 모으고, `answer`가 오면 답 말풍선 다음에 표를 순서대로, 그다음 [초안 보기]를 붙인다. `answer`가 없으면 버린다.
- 표: `<table>`과 머리 행. 제목은 표 위 굵은 글자, 설명 줄은 그 아래 흐린 글자. 숫자 칸(`typeof === "number"`)은 오른쪽 맞춤, `null`은 `-`. 막대 칸은 숫자와 `<span class="bar">`의 `style.width`(최댓값 대비 %, 최댓값 0이면 그리지 않음). 잘렸으면 표 아래 "전체 N건 중 M건".
- 감싸는 `<div class="result-table">`에 `overflow-x: auto`를 둬서 그 표만 가로로 스크롤된다.
- 모르는 `kind`는 건너뛴다. 값은 `dom.js`의 `el`로만 넣는다.
- 스타일은 `admin.css`에 두고 구매 요청서 상세 표와 같은 테두리·여백을 쓴다.

### 8. [초안 보기](탐색 결정 6)
- `chat.js`의 초안 종류 표 `DRAFT_KINDS = { curation: "curations", template: "templates", purchase: "purchases" }`. 버튼을 누르면 `ui.onOpenDraft(kind, id)`.
- `main.js`: `openDraft(kind, id)`는 `tabs.approvals.reveal(kind, id)`를 부른 뒤 `location.hash = "approvals"`. 이미 승인 목록 탭이면 `reveal`이 직접 다시 그린다.
- `approvals.js`: `reveal(kind, id)`는 다음에 펼칠 초안을 기억하고 `show()`(=`load`)가 목록을 다 읽은 뒤 그 줄을 `open`으로 펼치고 `scrollIntoView`한다. 승인 대기 보기에 없으면 전체 보기로 바꿔 한 번 더 읽고, 그래도 없으면 "그 초안을 찾지 못했어요"를 보인다.
- 주소에 id를 넣는 방식(`#approvals/curation/12`)은 `tabName` 규칙과 숨긴 탭 주소 테스트를 고쳐야 하고, 새로 고치면 대화가 사라져 얻는 것이 적어서 미룬다.
- 운영 대화 패널은 숨기기만 하므로 돌아오면 대화와 표가 남는다.

### 9. 프롬프트와 평가(탐색 결정 8, 10)
- 프롬프트는 v4 그대로다. 이번 변경은 LLM이 받는 내용을 바꾸지 않는다. 답 문장과 표가 겹쳐 보일 수 있고, 다듬기는 평가 `must_say`와 함께 미룬다.
- 운영 평가 36개를 한 번 돌린다. LLM 약 80~110회(실행당 상한 8회 기준 최악 288회), 입력 약 30만·출력 약 1만 토큰, 약 $0.04, 외부 API 없음. 돌리기 직전에 다시 알리고 승인을 받는다.
- `science-word`, `busy-fields`, `curation-space`(기록된 흔들림)가 틀리면 그것만 `--only`로 한 번 더 돌린다. 그 밖이 틀리면 멈추고 보인다. 지난 기록보다 나빠지지 않으면 통과다. 결과는 아래 "확인 결과"에 적는다.
- 평가 러너는 SSE 사건을 이름별 dict로 모으므로 `result`가 더해져도 깨지지 않는다. pytest로 확인한다.

### 10. 확인용 DB(탐색 결정 9)
B7·B10·B11은 초안 행을 만들고 개발 DB의 SQL `delete`는 막혀 있다. 그래서 개발 DB 상태를 먼저 읽기 전용으로 보고, 개발 DB를 템플릿으로 확인용 DB를 따로 만든다(`createdb -T`, 템플릿 DB에 연결이 없어야 하므로 서버를 멈춘 뒤). 서버는 그 DB URL로 띄운다. 스키마를 바꾸지 않으므로 마이그레이션은 없다. 정확한 DB 이름과 명령은 태스크 4.1에서 확인해 드린다.

## 브라우저 확인

확인용 DB `chaekbang_check`(2026-11-26 개발 DB를 템플릿으로 만듦, alembic `949a92d2205d`)에서 한다. 개발 DB 상태(읽기 전용 확인): 햇살 기관 도서 35·사본 54·분실 1·대출 중 7·이번 달 대출 5·연체 7·ISBN 있는 처리 전 희망도서 0·최근 90일 인기 ISBN 9, 푸른숲 기관 도서 235·사본 254·대출 중 70(모두 11월 6일 가져오기). 햇살은 자체 대출, 푸른숲은 외부 대출 기관이다. B1~B12는 질문마다 운영 에이전트 실행 한 번(LLM 약 3~4회)이라 모두 약 40~50회이고, B11은 상세를 펼칠 때 YES24 정가 조회가 항목 수만큼 있다. 시작 전에 다시 알리고 승인을 받는다.

| B | 계정 | 누르기·입력 | 보여야 할 것 |
| --- | --- | --- | --- |
| B1 | 햇살 관리자 | [운영 대화]에 "분야별로 책이 몇 권씩 있어?" | 답 아래 "분야별 장서" 표. 분야마다 한 줄이고 "분류 없음" 줄이 있음. 사본 칸에 막대 |
| B2 | 햇살 | "이번 달 대출이 많았던 분야 알려줘" | 표 제목 아래에 이번 달 기간. 대출 칸에 막대, 사본·권당 대출 열이 있음 |
| B3 | 햇살 | "지난 3개월 동안 가장 많이 빌린 책 10권 알려줘" | 순위, 서명, 저자, 대출 표. 막대 없음 |
| B4 | 햇살 | "분실된 책 보여줘" | 서명, 저자, 등록번호, 청구기호 표. 막대 없음 |
| B5 | 햇살 | "올해 한 번도 안 빌린 책 보여줘" | 안 빌린 책 표. 20건을 넘으면 표 아래 "전체 N건 중 20건" |
| B6 | 햇살 | "우리 도서관 책이 모두 몇 권이야?" | 표 없이 답 문장만 |
| B7 | 햇살 | "공룡 책으로 큐레이션 만들어 줘" → 답 아래 [초안 보기] | [승인 목록] 탭으로 바뀌고, 큐레이션 묶음에서 그 초안이 펼쳐져 화면에 보임 |
| B8 | 햇살 | B7 뒤 [운영 대화] 탭 | 대화와 표가 그대로 있음 |
| B9 | 햇살 | B7의 초안을 [승인]한 뒤 [운영 대화]로 돌아와 같은 [초안 보기] | 승인 목록이 [전체] 보기로 바뀌고 그 초안이 펼쳐짐 |
| B10 | 햇살 | "연체 안내문 만들어 줘" → [초안 보기] | 연체 안내문 틀 묶음에서 그 틀이 펼쳐짐 |
| B11 | 햇살 | "많이 빌린 책으로 구매 요청서 만들어 줘" → [초안 보기] | 구매 요청서 묶음에서 펼쳐지고 추정 총액이 보임(햇살에는 ISBN 있는 희망도서가 없어 인기 후보로 만든다) |
| B12 | 푸른숲 관리자 | "지금 대출 중인 책 목록 보여줘" | 표 설명 줄에 "11월 6일 가져온 파일 기준", 70건이라 표 아래 "전체 70건 중 20건" |
| B13 | 아무나 | 표가 보이는 대화에서 [새 대화] | 답 문장과 표가 모두 사라짐 |
| B14 | 아무나 | 표가 보일 때 창을 좁히기 | 그 표만 가로로 스크롤되고 대화 화면은 가로로 넘치지 않음 |

"그 초안을 찾지 못했어요"는 초안이 지워지지 않아 화면으로 만들 방법이 없어 B에서 뺀다.

## Risks / Trade-offs

- [답 문장과 표가 겹침] 프롬프트가 표를 모른다 → v4 유지, 브라우저 확인에서 보고 미룬 일로 적는다.
- [변환 예외가 실행을 실패로 만듦] 표 하나 때문에 답이 고정 답이 될 수 있다 → 변환은 순수 함수이고 tool마다 단위 테스트로 막는다. 예외를 삼키지 않는 이유는 틀린 표를 조용히 빼는 것보다 드러나는 편이 낫기 때문이다.
- [일반 표의 칸은 아무 값이나 담을 수 있음] → 열 허용 목록 테스트와 실제 회원 값 테스트(결정 5).
- [같은 tool을 여러 번 부르면 표가 여럿] 비교 질문에서 표 둘 → 설명 줄의 기간으로 구분하고, 합치기는 미룬다.
- [옛 답의 [초안 보기]] 그사이 승인·반려되면 대기 보기에 없다 → 전체 보기로 다시 찾는다.

## 확인 결과와 미룬 일

- pytest(묶음 1 뒤): 2194 통과·7 스킵(이전 2159). 화면(묶음 3) 뒤: 2198 통과·7 스킵, ruff 통과.
- 브라우저 확인 B1~B14(2026-11-26, 사용자, 확인용 DB `chaekbang_check`): **모두 통과**. 확인 중 나온 에이전트의 한계(이어지는 분야 질문, 정해진 기간)는 아래 미룬 일에 적었고, 이 change에서는 고치지 않았다.
- 운영 평가 전체 회귀(2026-11-26, `gpt-6-luna`, 프로필 v4, 36개, `data/runs/20261126-021559-gpt-6-luna`): tool 선택 36/36, 숫자 충실도 36/36, 못 하는 분석 분류 35/36, 초안 충실도 36/36, **모두 맞음 35/36**. 입력 약 39만·출력 약 5천 토큰. 기록된 흔들림 셋(`science-word`, `busy-fields`, `curation-space`)은 모두 맞았다.
- 틀린 것은 `kids-science`("아동 과학책 몇 권이야?") 하나다. 호출(자연과학 + 어린이 필터)과 숫자(사본 5권)는 맞고 `unsupported`를 `topic_count`로 골랐다. `--only`로 다시 돌려도 같았다(`20261126-021857-gpt-6-luna`, 답 문장은 "못 해요" 없이 맞음). 이 시나리오는 v1~v3에서 네 번 모두 맞았고, v4(`add-purchase-request`의 프롬프트)에서는 이번이 처음이다.
- 2026-11-26 사용자 결정: v4를 그대로 두고 미룬 일로 기록한다(탐색 결정 8, MVP 우선). 틀리는 것은 기록용 분류 하나이고 화면에는 "지금은 못 하는 분석이에요" 표시가 붙지만 숫자와 표는 맞다.
- 이 change가 원인이 아님을 LLM 없이 확인했다: `main`과 이 브랜치에서 `build_admin_profiles`의 시스템 프롬프트와 tool 정의(이름·설명·JSON Schema)를 해시로 비교해 같다(`present`는 LLM에 가지 않는다).

미룬 일(archive 때 roadmap에 옮김):
- 표: 열 머리 정렬, 접기, CSV 내려받기, 열 단위, 결과 하나에 표 여러 개(대출 묶음과 `current`), 비교 두 표 합치기, 원형·선 차트
- 보일 결과 늘리기: 연체 목록, 구매 후보, 소장 도서 검색 결과
- 주소에 초안 id를 넣는 링크(뒤로 가기, 공유)
- 이어지는 분야 질문(2026-11-26 브라우저 확인 중 사용자 발견, 확인용 DB 실행 26~28): "이번 달 대출 많은 도서 종류"는 `group_by=book`(책 순위), 이어서 "그럼 도서 분야 알려줘"도 `group_by=book`을 다시 부르고 순위 결과에 분야가 없어 `unsupported=other`로 못 답했다. "대출이 많았던 분야"는 `group_by=field`로 맞았다. 데이터 문제가 아니고, LLM 입력은 `main`과 같아 이 change 때문도 아니다. 고칠 길은 둘: 프롬프트에서 "종류·분야"는 분야 묶기로 정하기, 또는 책 순위 결과에 분야 칸 더하기("그 책들 분야는?"까지 답함). MVP 뒤에 과학 분야 고르기와 함께
- 자유 기간(2026-11-26 브라우저 확인 중 사용자 지적: 기간이 목록에 묶이면 대화형의 장점이 없다): 기간은 프리셋 7개와 월 숫자뿐이라 "2개월"을 최근 90일로 대신하고 `unsupported=other`를 골랐다. DB 조회는 임의의 시작일·끝일을 받을 수 있으니 입구만 넓힌다("N개월", "N주", 날짜 범위. LLM은 숫자·월·일만 고르고 날짜 계산은 코드). 2026-11-26 사용자 결정: MVP를 완성한 뒤 에이전트만 고친다. 위 분야 질문과 `kids-science` 프롬프트 수정을 함께 하고 평가를 한 번 돌린다. 자연어 SQL과는 따로다
- 표가 보이는 답의 프롬프트 다듬기(v5, 평가 `must_say`와 함께)
- 과학 분야 고르기 프롬프트 수정에 `kids-science`를 더함: v4에서 분야·축 필터로 답하고도 `unsupported=topic_count`를 고른다(두 번 연속). `science-word`·`busy-fields`·`curation-space`와 함께 MVP 뒤에 고치고 전체 재평가
- 대화 기록에 표 남기기(화면 되살리기와 함께)
- "그 초안을 찾지 못했어요"의 브라우저 확인
- Playwright: archive 뒤 다음 change를 정할 때 다시 본다
