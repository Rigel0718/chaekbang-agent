## Context

- `app/core/config.py`의 `Settings`(pydantic-settings)는 필드 약 37개를 모두 환경변수와 `.env`에서 읽는다(`extra="ignore"`). 쓰는 곳은 64개 파일이고, 정책값 필드는 28개 파일 약 50줄에서 읽는다.
- `docker-compose.yml`의 embedder가 `TEI_MODEL_ID`, `EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS`를 `${VAR:-기본값}`로 읽고, `docker/embedder/start.sh`가 이를 쓴다. 앱의 `TeiEmbedder.check()`는 서버 `/info`의 모델 이름과 입력 한도를 설정과 비교해 다르면 `MODEL_MISMATCH`로 멈춘다.
- 벡터 열 차원은 `app/central/models.py`의 `EMBEDDING_DIM = 1024`이고, `Settings.embedding_dim`은 `tei.py`만 읽는 복사본이다.
- 테스트와 평가가 설정을 바꾸는 길: 생성 인자(`Settings(..., llm_model=...)`), `monkeypatch.setattr(get_settings(), ...)`(7곳), 평가의 `settings.model_copy(update=...)`와 `--model`, `tests/conftest.py`의 `os.environ["PASSWORD_SCRYPT_N"]`. 환경변수로 덮는 곳은 마지막 하나와 `SEED_*`뿐이다.
- 층 규칙: `app/core`는 `central`을 import하지 못한다. 그래서 `config.py`가 `EMBEDDING_DIM`을 가져다 쓸 수 없고, 차원을 쓰는 `central/external/tei.py`가 상수를 직접 쓴다.

동기는 proposal의 Why를 본다.

## Goals / Non-Goals

**Goals:**
- `.env`와 환경변수가 바꿀 수 있는 필드를 허용 목록으로 한정한다. 새 필드의 기본은 코드값이다.
- 호출부(필드 이름, `get_settings()`)와 테스트의 덮어쓰기 길은 그대로 둔다.
- compose와 앱이 어긋날 길을 닫는다(리터럴과 비교 테스트, 실행 중에는 `check()`).

**Non-Goals:**
- 설정 필드 이름 바꾸기, 객체 둘로 나누기, 불변화(개선 사항으로 미룸).
- 기관별 설정(시간대, 하루 상한을 기관마다 다르게)은 만들지 않는다. 시간대는 서울 고정이다.
- 옛 `.env` 키를 알려 주는 경고, 임베딩 모델 비교용 경로.

## Decisions

**1. 한 객체, 환경 읽기만 허용 목록으로 거른다.** `config.py`에 `ENV_FIELDS`(환경 필드 이름 집합)를 두고 `settings_customise_sources`로 환경변수 소스와 `.env` 소스의 결과에서 `ENV_FIELDS` 밖의 키를 버린다. 생성 인자 소스는 거르지 않는다. 시작 때 `ENV_FIELDS`의 이름이 모두 `Settings` 필드인지 확인한다.
- 대안 A(문서만 정리): `.env`의 정책 키가 계속 코드값을 이긴다. 목적을 이루지 못한다.
- 대안 C(환경 객체와 정책 객체 둘): 호출부 28개 파일과 `OpenAiClient`·`TeiEmbedder` 생성자가 바뀐다. MVP에 주는 이득이 없어 개선 사항으로 둔다.
- 불변(`frozen`)으로 만들면 테스트 `monkeypatch.setattr` 7곳과 평가의 덮어쓰기가 깨져서 하지 않는다.

**2. 허용 목록이 기준이다.** 이름으로 허용한 필드만 `.env`를 읽고 나머지는 코드값이다. 환경 필드: `database_url`, `test_database_url`, `openai_api_key`, `yes24_api_key`, `library_bigdata_key`, `kakao_rest_api_key`, `seed_admin_password`, `seed_kiosk_password`, `embedding_base_url`, `embedding_query_enabled`. 판단 기준은 "같은 코드를 설치하는 곳마다 값이 달라야 하거나 비밀인가"다.
- `embedding_query_enabled`는 임베딩 서버를 띄우는 환경인지에 달려 있어 환경 필드다(약 4GB 메모리를 못 내는 PC).
- 외부 API 주소 3개는 이미 `.env.example`에 없고 코드 기본값이므로 코드값으로 확정한다.
- 시간대는 서울 고정이다(`library_timezone` 필드는 코드값으로 두고 이름은 바꾸지 않는다).

**3. `embedding_dim` 필드를 지우고 `tei.py`가 `EMBEDDING_DIM`을 쓴다.** 차원의 출처를 스키마 상수 하나로 하면 `.env`로 스키마와 어긋나는 길이 없다. `central`이 `central/models.py`를 읽는 것은 같은 층이라 층 규칙에 맞다.

**4. 임베딩 모델 이름과 입력 한도는 코드값, compose는 리터럴.** `embedding_model`, `embedding_max_tokens`는 모델을 바꾸면 전체 재적재와 추천 평가를 다시 하는 제품 결정이라 설치마다 다르면 안 된다. compose는 `${...}` 치환을 빼 `.env`의 옛 키가 서버를 움직이지 않게 한다. 같은 값인지는 테스트가 compose 파일을 정규식으로 읽어 비교한다(`test_web_ui.py`가 JS 상수를 읽는 방식과 같고 YAML 의존성을 더하지 않는다). 실행 중에 어긋나면 `check()`가 막는다.
- 대안(세 값을 `.env`로): 출처는 하나가 되지만 설치하는 사람이 모델을 고르게 된다. 이번 변경의 방향과 반대다.
- `EMBEDDING_PORT`(compose)와 `EMBEDDING_BASE_URL`(앱)은 서로 맞아야 하는 환경 값이다. `.env.example` 주석으로 짝을 안내하고 코드로 묶지는 않는다.

**5. LLM 모델·생각 수준은 코드값.** 평가 결과는 특정 모델 기준이고 `LLM_PRICES`가 코드에 있어, 모델을 바꾸는 일은 코드 변경이다. 바꾸는 길은 평가의 `--model`과 생성 인자다.

**6. 테스트의 해시 비용.** `conftest.py`가 환경변수 대신 `get_settings().password_scrypt_n = 1024`를 첫 테스트 전에 설정한다. `hash_password`는 부를 때마다 설정을 읽고 해시 문자열에 `n`이 들어 있어 검증은 영향이 없다. 시드 스크립트를 subprocess로 도는 테스트는 낮춘 값을 물려받지 못하고 기본값으로 해시한다(계정 몇 개라 시간 영향은 작다고 보고, 구현 때 재서 알린다).

**7. 옛 키는 조용히 무시한다.** 거른 키는 오류도 경고도 없다. 막는 문제가 없고, 설치는 새 `.env.example`로 시작한다. 개발 PC 한 대의 `.env`는 지울 키 목록을 확인받은 뒤 손으로 정리한다(값은 출력하지 않는다).

## Risks / Trade-offs

- [`.env`에 정책 키를 적고 효과가 있다고 믿는다] → `.env.example` 머리 주석과 `CLAUDE.md` 규칙에 "효과 없음"을 적는다. 경고 기능은 개선 사항.
- [pydantic-settings 소스 거르기가 버전에 따라 다르게 동작] → 테스트 시나리오(정책 필드 전부, 옛 키 `.env`, 환경 필드)가 동작을 고정한다. 이 의존성은 이미 `uv.lock`에 고정되어 있다.
- [모델 바꾸기가 코드 배포가 된다] → 가격표(`LLM_PRICES`)도 같은 파일이라 어차피 코드 변경이 필요하다. `retires_on`으로 미리 안다.
- [시드 subprocess 테스트가 느려진다] → 구현 때 재서 알리고, 눈에 띄게 느리면 멈추고 묻는다.
- [임베딩 모델 비교 실험이 불편해진다] → compose와 `config.py`를 함께 고친다. MVP 뒤 개선 사항.

## 결과

- 시작 전(1.1): `pytest` 2012 passed, 7 skipped(2분 41초), `ruff check` 통과.
- 시드 subprocess 테스트(2.3): `tests/platform/test_seed.py` 12개 통과, `test_script_success_and_rerun` 3.66초 → 3.61초로 변화 없음(해시 비용을 낮춘 값을 물려받지 못해도 계정이 몇 개뿐이다).
- 끝난 뒤(6.1): `pytest` 2040 passed, 7 skipped(2분 41초, 28개 늘어남), `ruff check`·`ruff format --check` 통과. 개발 `.env` 정리 뒤에도 같은 결과다.
- 서버 확인(6.2): `.env` 59줄 → 39줄(키 집합이 `.env.example`과 같음) 상태에서 `uvicorn`을 띄워 `/docs` 200, 관리자 `POST /auth/login` 200.
