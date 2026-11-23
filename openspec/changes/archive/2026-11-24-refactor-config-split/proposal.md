## Why

`Settings` 하나가 비밀·설치 환경 값과 제품 정책값을 모두 `.env`에서 읽는다. 그래서 `.env.example`이 약 40줄이 되고, 개발 `.env`에 남은 정책 키(`LIBRARIAN_MAX_TURNS`, `LLM_MODEL` 등)가 코드 기본값을 조용히 덮는다. 임베딩 차원은 스키마 상수(`EMBEDDING_DIM`)와 설정 필드 두 곳에 있어, `.env`에서 바꾸면 벡터 열과 어긋난다. MVP 출시 전에 설치하는 사람이 채울 값(`.env`)과 코드 리뷰를 거쳐 바꿀 값(코드)을 나눠 둔다.

## What Changes

- **환경 값만 `.env`에서 읽는다.** `.env`·환경변수로 읽는 필드는 비밀과 설치마다 다른 값으로 한정한다: DB 접속(`DATABASE_URL`, `TEST_DATABASE_URL`), 외부 API 키 4개, 시드 비밀번호 2개, 임베딩 서버 주소·켜기(`EMBEDDING_BASE_URL`, `EMBEDDING_QUERY_ENABLED`). 나머지 필드는 코드 기본값만 쓰고 같은 이름의 환경변수·`.env` 키가 있어도 무시한다(오류 없음). 생성 인자로는 모든 필드를 바꿀 수 있다(테스트·평가).
- **코드 config로 옮기는 값**: 토큰 수명, 시간대(서울 고정), 해시 비용, 세션 무입력 분, 턴·하루 상한, LLM 모델·생각 수준·토큰 상한·제한 시간, 임베딩 모델 이름·입력 한도·배치·제한 시간·질의 제한 시간·쉬는 시간.
- **`embedding_dim` 필드를 없앤다.** 임베딩 인코더의 차원은 스키마 상수 `EMBEDDING_DIM` 하나만 쓴다.
- **`docker-compose.yml`의 임베딩 서버(embedder)** 가 `${...}` 치환 대신 `TEI_MODEL_ID`·`EMBEDDING_MODEL`·`EMBEDDING_MAX_TOKENS`를 리터럴로 적는다. 앱 설정과 같은 값인지 테스트가 비교한다. 서버가 설정과 다르게 떠 있으면 `check()`가 지금처럼 막는다.
- **`.env.example`을 환경 값만 남기고 다시 쓴다**(약 40줄 → 15~18줄). 머리 주석에 "정책값은 `app/core/config.py`에 있고 여기 적어도 효과 없다"를 적는다.
- **테스트**: `tests/conftest.py`는 해시 비용을 환경변수 대신 설정 객체에서 낮춘다.
- **문서**: `CLAUDE.md` 코딩 규칙, `README.md`, `app/{agent,central,library}/README.md`의 환경변수 이름을 설정 필드 이름으로 고치고, 평가 `--model` 도움말("없으면 LLM_MODEL") 3곳을 고친다.
- **BREAKING**(운영자): `.env`로 정책값(모델, 상한, 토큰 수명 등)을 바꾸던 길이 사라진다. 값을 바꾸려면 코드를 고친다. 개발 PC의 `.env`는 지울 키 목록을 확인받은 뒤 정리한다.

## Capabilities

### New Capabilities
- `platform/app-settings`: 설정을 읽는 규칙. 환경 값과 코드값의 구분, `.env.example`과 환경 필드의 일치, 임베딩 서버와 앱이 같은 모델·입력 한도를 쓰는 것.

### Modified Capabilities
- `agent/runner`: "LLM 설정"의 시나리오 "모델 설정 적용"에서 `LLM_MODEL` 환경변수 대신 설정의 모델을 바꾼다.

## Impact

- 코드: `app/core/config.py`, `app/central/external/tei.py`, `docker-compose.yml`, `tests/conftest.py`, `tests/core/test_config.py`, 평가 `__main__.py` 3곳의 도움말. 설정 필드 이름과 호출부(28개 파일)는 바꾸지 않는다.
- 문서: `.env.example`, `CLAUDE.md`, `README.md`, `app/agent/README.md`, `app/central/README.md`, `app/library/README.md`. `docs/roadmap.md`는 archive 때 고친다.
- DB 스키마·마이그레이션, API, 화면, 새 의존성은 없다. LLM·외부 API 호출도 없다.
- 미룬 일(개선 사항): 무시한 옛 키 경고, `Settings` 불변화나 객체 분리, 평가 `--effort`, 임베딩 모델 비교 실험 경로, `EMBEDDING_PORT`와 `EMBEDDING_BASE_URL` 짝 맞추기.
