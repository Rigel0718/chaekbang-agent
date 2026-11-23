순서: 1은 시작 전 기준, 2는 설정 경계(코드와 테스트), 3은 compose, 4는 문서와 `.env.example`, 5는 개발 `.env` 정리, 6은 마무리 검증이다. 기능은 바뀌지 않는다. 바꿔야 할 일이 생기면 멈추고 먼저 묻는다. 분량이 넘치면 개선 사항으로 돌리고 범위를 늘리지 않는다(MVP 우선).

모델 분리: **2·6은 Opus**(설정을 읽는 경로, 테스트가 덮어쓰는 길, 검증), **1·3·4는 Sonnet**(compose 리터럴, 문서 치환), **5는 어느 모델이든**(키 이름만 다룸).

## 1. 시작 전 기준 (Sonnet)

- [x] 1.1 `uv run pytest`와 `uv run ruff check .`를 돌려 통과 수를 design 끝 "결과"에 적는다(확인: 기존 테스트가 모두 통과)

## 2. 설정 경계 (Opus, design 결정 1~3·6)

- [x] 2.1 `app/core/config.py`에 환경 필드 허용 목록과 소스 거르기를 둔다(환경변수·`.env`만 거르고 생성 인자는 받음). `ENV_FIELDS`가 모두 `Settings` 필드인지 시작 때 확인한다. 필드는 절 주석(환경 값 / 코드값)으로 나눈다(확인: 스펙 app-settings "환경 값과 코드값 분리"의 테스트 4개 — 정책 필드 전부를 한 parametrize로, 옛 키가 든 임시 `.env`, 환경 필드, 직접 준 값)
- [x] 2.2 `Settings.embedding_dim`을 지우고 `app/central/external/tei.py`가 `app.central.models.EMBEDDING_DIM`을 쓰게 한다(확인: 스펙 app-settings "임베딩 서버와 같은 모델·입력 한도"의 "인코더 차원" 테스트, 기존 임베딩 테스트 통과)
- [x] 2.3 `tests/conftest.py`의 `os.environ["PASSWORD_SCRYPT_N"]`를 첫 테스트 전에 설정 객체의 `password_scrypt_n`을 낮추는 코드로 바꾼다. `SEED_*`의 `setdefault`는 그대로 둔다(확인: 전체 `pytest` 통과, 시드 subprocess 테스트 시간을 재서 design 끝 "결과"에 적음)
- [x] 2.4 `tests/core/test_config.py`의 `delenv("LLM_MODEL")`을 없애고, 스펙 agent/runner "모델 설정 적용"과 맞게 docstring을 고친다(확인: `uv run pytest tests/core tests/agent`)

## 3. compose (Sonnet, design 결정 4)

- [x] 3.1 `docker-compose.yml`의 embedder `environment`에서 `TEI_MODEL_ID`·`EMBEDDING_MODEL`·`EMBEDDING_MAX_TOKENS`를 `${...}` 없이 리터럴로 적는다. `EMBEDDING_PORT`·`POSTGRES_*` 치환은 그대로 둔다(확인: `docker compose --profile embedding config`의 embedder 환경이 세 값을 보인다. embedder는 띄우지 않는다)
- [x] 3.2 compose의 값과 `Settings` 기본값을 비교하는 테스트를 `tests/core/test_config.py`에 더한다. 정규식으로 읽고 새 의존성은 쓰지 않는다(확인: 스펙 app-settings "compose와 설정이 같다"의 테스트가 통과하고, compose 값을 임시로 바꾸면 실패한다)

## 4. 문서와 `.env.example` (Sonnet, design 결정 7)

- [x] 4.1 `.env.example`을 환경 키만 남기고 다시 쓴다. 머리 주석("정책값은 `app/core/config.py`, 여기 적어도 효과 없음"), `EMBEDDING_PORT`↔`EMBEDDING_BASE_URL` 짝 주석을 둔다. 키 일치 테스트를 `tests/core/test_config.py`에 더한다(확인: 스펙 app-settings "키 집합 비교"의 테스트)
- [x] 4.2 `CLAUDE.md` 코딩 규칙의 `.env` 줄을 설정 규칙 2줄(`.env`는 환경 값만·코드값이 기본, 임베딩 모델 이름과 입력 한도는 `config.py`와 compose에 같은 값)로 바꾼다(확인: 문구가 탐색 결정 7의 초안과 같음)
- [x] 4.3 `README.md` 71행, `app/agent/README.md` 60행, `app/library/README.md` 124행, `app/central/README.md`(112·115·118·123·125·157·160행 근처)의 대문자 환경변수 이름을 설정 필드 이름으로 고치고, central의 "모델 바꾸는 순서" 2단계를 `config.py`와 `docker-compose.yml`을 함께 바꾸는 말로 고친다(확인: `grep -rnE "LLM_MODEL|EMBEDDING_(MODEL|MAX_TOKENS|DIM|BATCH|TIMEOUT|QUERY_(TIMEOUT|PAUSE))|ADMIN_TOKEN_HOURS|KIOSK_TOKEN_HOURS" --include=*.md . `가 archive와 `docs/roadmap.md` 밖에서 나오지 않음)
- [x] 4.4 평가 `evals/{librarian,conversation,admin_agent}/__main__.py`의 `--model` 도움말 "없으면 LLM_MODEL"을 "없으면 기본 모델"로 고친다(확인: `uv run ruff check .`, `--help` 출력)

## 5. 개발 `.env` 정리 (어느 모델이든, design 결정 7)

- [x] 5.1 `.env`의 키 이름만 읽어 지울 키 목록(정책 키와 옛 키)을 사용자에게 보여 주고, 확인을 받은 뒤 그 줄만 지운다. 값은 출력하지 않는다(확인: 지운 뒤 `.env`의 키 집합이 `.env.example`의 앱 키와 같고, `uv run pytest`가 통과)

## 6. 마무리 검증 (Opus)

- [x] 6.1 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`가 통과하고, 통과 수를 시작 전 기준(1.1)과 비교해 design 끝 "결과"에 적는다(확인: 모든 스펙 시나리오에 테스트가 하나 이상 있음을 시나리오 이름과 테스트 docstring으로 대조)
- [x] 6.2 `uv run uvicorn app.main:app`을 시작해 `/docs`가 뜨고 `.env`를 정리한 상태에서 DB·로그인이 되는지 확인한다(확인: 서버 시작, `POST /auth/login` 성공)

## Workflow follow-up

- 사람이 확인한 뒤 archive하고, `docs/roadmap.md`의 `refactor-config-split` 행 상태와 확정된 기본값, 개선 사항 5건(무시한 옛 키 경고, `Settings` 불변화·객체 분리, 평가 `--effort`, 임베딩 모델 비교 실험 경로, `EMBEDDING_PORT`·`EMBEDDING_BASE_URL` 짝 맞추기)을 적는다. `CLAUDE.md` "현재 단계"도 고친다.
