## Why

이용자 화면에서 낱말을 치고 Enter를 누르면 지금은 항상 AI 사서 대화로 간다. `채식`은 서명 찾기(`/catalog/search`)와 주제로 찾기 모두 채식주의자가 1위인데, 대화에서 LLM이 낱말에 `요리`를 더해 최강록 책을 올렸다(2026-11-24, 개발 DB 실험 기관 id 7에서 읽기만 확인). 이용자가 아는 책을 친 경우에는 LLM을 거치지 않고 그 책과 관련된 책을 바로 보여 줘야 한다. MVP 출시 전에 사용자가 화면을 써 보고 걸린 점으로 꼽았다(`polish-web-ui` 탐색, roadmap 24d).

## What Changes

- **주제 검색 REST** `GET /catalog/topic?q=`: AI 사서의 소장 도서 검색이 쓰는 제품 경로의 주제로 찾기를 감싼 얇은 API다. 키오스크·관리자가 쓰고, 기관은 토큰으로 정한다. 질의(1~100자)를 공백으로 나눈 낱말로 부르고, 결과는 서명·저자 찾기와 같은 카드 값으로 최대 10권이다. 낱말이 없으면 빈 목록이다. 임베딩 서버가 없거나 실패하면 지금처럼 키워드 순위로 내려간다. LLM을 부르지 않고 질의와 기록을 남기지 않는다.
- **이용자 화면의 두 단계 검색**: Enter를 누르면 먼저 서명·저자 찾기를 부른다.
  - 1권 이상이면 AI 사서 대화를 보내지 않고, 위 단 "이 책을 찾으시나요?"(찾기 결과 앞 2권), 아래 단 "'질의'와 관련된 책"(주제 검색 결과에서 위 단 책을 뺀 것), [사서에게 물어보기](같은 글을 대화로)를 보인다.
  - 0권이거나, 입력이 100자를 넘거나, 찾기가 실패하면(401은 빼고) 지금처럼 AI 사서 대화로 보낸다.
  - 자동완성 후보를 고르는 것과 "'질의'로 책 모두 찾기"는 지금 그대로다.
- **화면이 부르는 경로**에 `/catalog/topic`을 더한다. 화면 전용 API는 여전히 두지 않는다.
- 스키마 변경 없음. 추천 기준값(주제로 찾기의 기본 설정)은 바꾸지 않는다(evals 채택 실험 없음).
- **범위 밖**(design의 미룰 것): 맞은 방식으로 위 단 1권·2권 나누기, 위 단에서 빠진 찾기 결과 더 보기, 두 요청 동시 호출, 한두 글자 질의 빼기, 서버 쪽 위 단 제외, 벡터만으로 나온 결과 표시, 브라우저 자동화 테스트.

## Capabilities

### New Capabilities

(없음)

### Modified Capabilities

- `catalog/topic-recommendation`: 제품 경로의 주제로 찾기를 REST(`GET /catalog/topic`)로도 낸다(인증, 질의 규칙, 낱말 나누기, 빈 낱말, 기록 없음)
- `platform/web-ui`: "기존 API만 사용"의 이용자 화면 경로에 주제 검색을 더하고, 이용자 화면의 Enter를 두 단계 검색으로 바꾼다

## Impact

- 서버: `app/library/api/catalog.py`(경로 하나), `app/library/services/topic.py`(질의를 낱말로 나눠 부르는 함수 하나). 질의 인코더 의존성은 `app/library/api/librarian.py`의 것을 그대로 쓴다. DB 스키마·마이그레이션 없음.
- 화면: `app/web/public/shared/api.js`(`topic`), `app/web/public/librarian/`의 `main.js`·`suggest.js`(Enter 갈림), `chat.js`(두 단계 블록), `librarian.css`.
- 테스트: 새 `tests/library/test_topic_api.py`, `tests/platform/test_web_ui.py` 확장.
- 문서: `app/web/README.md`, `app/library/README.md`. archive 때 `docs/roadmap.md`, `CLAUDE.md` "현재 단계".
- 외부 API·LLM 호출: 서버 경로는 없음. 브라우저 확인에서 사용자가 AI 사서 대화를 약 4번 부른다.
