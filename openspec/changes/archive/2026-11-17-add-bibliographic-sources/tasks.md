## 0. 시작 전

- [x] 0.1 issue 번호를 받는다(design을 요약한 issue 제목·본문을 텍스트로 준다). #37
- [x] 0.2 `main`(`add-related-book-experiments` 머지 `09afb13`)에서 브랜치 `add-bibliographic-sources`를 만든다. API 문서를 `api-guides/`로 모은 커밋 `c497901`이 첫 커밋이다
- [x] 0.3 기준 수치를 남긴다(2026-11-16): `uv run pytest` 1253 통과·7 건너뜀. `topic --split all --variants current,hybrid-k60`(`runs/20261116-205850`), `similar … sim-vec,sim-rrf`(`205906`), `history … hist-mean`(`205909`)의 `results.json`이 기준 run(`112024`, `161401`, `161415`)과 같다(요약은 걸린 시간 줄만 다름)
- [x] 0.4 `uv run python -m evals.catalog_search` 결과가 `20261116-153856`과 같다(2026-11-16: `evals/catalog_search/data/runs/20261116-205912`)
- [x] 0.5 `CLAUDE.md` 현재 단계의 진행 중 change를 `add-bibliographic-sources`로 고치고, MVP 순서의 15번을 `add-bibliographic-sources`와 `add-loan-signals` 둘로 나눈다

## 1. 출처 클라이언트와 응답 해석

- [x] 1.1 `app/central/external/http.py`: YES24의 `RateLimiter`, `StopReason`을 옮기고 출처 공통 중단 예외 `SourceStopped(source, reason)`를 둔다. YES24 클라이언트가 이것을 쓴다. 기존 YES24 테스트가 그대로 통과한다
- [x] 1.2 `app/central/external/data4library/`(`definitions.py`, `client.py`, `parsing.py`): `srchDtlList`(`format=json`, https), 필드 경로·길이, 0.5초 간격. 키는 쿼리에만 붙인다. `httpx` 예외는 사슬 없이 바꾸고, `httpx`·`httpcore` 로거는 WARNING으로 둔다. 테스트(`tests/external/test_data4library.py`, `httpx.MockTransport`): 앞뒤 공백, 이스케이프된 소개, 잘못된 부가기호, 표지 미사용, 결과 없음, 한도 초과·인증 실패·장애·시간 초과의 중단 사유, INFO 로그와 예외 문자열에 키 없음, 헤더에 키 없음
- [x] 1.3 `app/central/external/kakao/`(같은 꼴): `v3/search/book?target=isbn`, `KakaoAK` 헤더, 0.2초 간격, ISBN 분해, ISO 출간일, 정가 0, 판매가·판매 상태 빼기, 저자·역자 배열 잇기. 테스트(`tests/external/test_kakao.py`): ISBN10과 ISBN13, 다른 ISBN 문서만 있음, 빈 문서 목록, 저자 둘과 역자 하나, 역자 없음, 빈 이름, 429·401·503, 키는 헤더에만
- [x] 1.4 `app/core/config.py`에 `kakao_rest_api_key`, `library_bigdata_key`, 두 base URL을 더한다. `.env.example`에 세 키 설명과 정보나루 IP 등록을 적는다. `uv run pytest tests/external` 통과

## 2. 합치기, 공식 서지, 마이그레이션

- [x] 2.1 `app/central/sources.py`: `OfficialValues`(값 + 필드별 출처), `merge(isbn, d4l, kakao, yes24)`(design 결정 3의 세 출처 표, 서명·저자와 표지·링크는 한 출처). 서명 나누기 `split_title`은 `external/data4library/parsing.py`에 둔다. 테스트(`tests/catalog/test_bibliographic_sources.py`): 스펙 "필드별 기준 출처"·"필드별 출처 기록"의 시나리오마다(2026-11-16 사용자 결정으로 세 출처로 고침)
- [x] 2.2 마이그레이션 `ba608103e1e2`: `books.kdc_name`, `books.addition_symbol`(CHAR(5), 5자리 숫자 검사), `books.volume`, `books.field_sources`(JSONB, 기본 `{}`), 출처 값 제약에 `data4library`·`kakao`. `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check`(마이그레이션 전 백업 `/home/pollux/chaekbang-backups/chaekbang-20261116-2116-before-sources-migration.dump`). 테스트: 잘못된 부가기호 직접 저장 거부
- [x] 2.3 `create_official(session, isbn, values: OfficialValues)`로 바꾸고, YES24 하나만 쓰는 경로(평가 표본 적재, 지금 실험 장서 적재)는 `from_yes24`로 같은 함수를 부른다. 기존 "두 경로의 같은 결과"와 YES24 시나리오 테스트가 통과한다
- [x] 2.4 `app/central/contributors.py`의 `PARSERS`에 `data4library`·`kakao` → `parse_author_text`. 테스트(`tests/catalog/test_source_enrichment.py`): 정보나루 이름표 꼴, 괄호 꼴, 카카오 이은 원문, 세 출처 행의 다시 만들기 확인 방식 차이 0
- [x] 2.5 `app/central/README.md`: 세 출처, 필드별 기준 출처, 키 전달 방식, 이용 조건 요약(처음에 두 출처로 썼다. 세 출처로 고친다)

## 3. 채움 실행

- [x] 3.1 `app/central/enrichment.py`: 조회 `lookup_sources(d4l, kakao, yes24)`(ISBN마다 셋을 한 번씩 → `merge`)와 조회를 받는 `run_enrichment`(만들기·`mismatch`·`not_found`, 출처마다 중단 사유). 테스트(`tests/catalog/test_source_enrichment.py`, 가짜 출처 셋): 스펙 "공식 서지 만들기", "저장하지 않는 값", "ISBN 일치 확인", "찾지 못한 도서", "외부 장애 시 중단"의 시나리오마다
- [x] 3.2 `scripts/enrich_books.py`: 세 키 확인(빠진 키 이름 안내, 종료 코드 1, 호출 없음), 출처마다 클라이언트, 중단 사유에 출처 이름. 테스트(`tests/catalog/test_enrich_script.py`): 키 미설정, 중단 출력, 출력과 로그에 키 없음
- [x] 3.3 기존 YES24 채움 테스트를 정리한다: 채움 실행의 흐름(대상, 나눠서 처리, 연결)은 조회가 무엇이든 같아, 기존 테스트는 테스트 전용 YES24 조회(`tests/yes24_helpers.yes24_lookup`)로 그대로 둔다. 세 출처의 판단과 값은 `tests/catalog/test_source_enrichment.py`가 `lookup_sources`로 본다. `uv run pytest` 통과

## 4. 어린이 근거와 출처 표시

- [x] 4.1 `app/features/children/rules.py`·`service.py`: 외부 근거에 공식 서지 부가기호 첫 자리 6·7(파일 근거와 같은 함수 `is_children_addition_code`)을 더한다. 갱신도 같다. 테스트(`tests/features/children/test_children.py`, `test_rules.py`): 스펙 "외부 분류 근거"(부가기호 `74850`·`63710` 어린이, `03810`·`43810` 일반, 높은 근거 유지, 운영자 실행은 바꾸지 않음, 새로 등록)와 "어린이 구분 갱신"(채움 뒤 갱신)
- [x] 4.2 조회 응답에 `cover_source`를 더하고(`Book.cover_source`, `app/library/schemas/catalog.py`), 카드의 표지 출처는 필드별 출처를 따른다(`cards.py`, 표시 이름 셋). 테스트: 스펙 "출처 표시" 시나리오, 카드 표지 출처
- [x] 4.3 `app/features/README.md`(어린이 기능의 README)에 부가기호 외부 근거를 적는다. `uv run pytest tests/platform/test_package_layers.py` 통과

## 5. 확인 호출

- [x] 5.1 정보나루 한도를 확인한다(2026-11-16 사용자: 하루 500건을 넘으려면 서버 IP 등록, 등록함). 사이트 이용약관(저장·재배포·출처 표기)은 서비스 전 확인 항목으로 `docs/design.md`에 올린다(9.2)
- [x] 5.2 확인 호출(정보나루 3회, 카카오 3회, 2026-11-16 사용자 승인). 실험 장서의 ISBN 3권(어린이 1, 번역서 1, 부제 있는 책 1), 응답은 저장소 밖(scratchpad)에만
- [x] 5.3 확인 결과를 design "결과"에 적는다: https 됨, JSON 꼴이 가정과 같음, 정보나루 서명 ` :`·끝 공백, 출간일은 해만, 카카오 소개 약 250자에서 잘림, 시리즈는 YES24만. 이 결과와 사용자 결정(2026-11-16: YES24도 세 출처 중 하나로 채움에 쓴다, 정보나루가 막히면 나머지로 계속 받는다)으로 design·proposal·스펙 delta를 세 출처로 고쳤다
- [x] 5.4 확인 호출로 본 실제 응답 꼴(정보나루 끝 공백 서명, `지음;… 옮김` 꼴 저자, 카카오 `isbn` 칸)을 고정본 테스트에 더한다

## 6. 새 출처 받기와 비교 수치

- [x] 6.1 `evals/collection/sources.py`(`uv run python -m evals.collection.sources [--dry-run]`): YES24 원본 파일에서 ISBN과 분야를 읽고, ISBN마다 정보나루·카카오를 부르고, 출처마다 상태를 파일에 쓴다. 정보나루가 멈춰야 하는 오류를 내면 정보나루만 멈추고 카카오는 계속한다. 다시 실행하면 출처마다 받지 않은 ISBN만 부른다. 테스트(`tests/evals/test_collection_sources.py`): 스펙 "새 출처 더 받기"와 "출처마다 이어 받기"의 시나리오마다
- [x] 6.2 `evals/collection/compare.py`: design 결정 8의 3(찾은 출처, 서명 일치 셋, 기여자, 소개 길이, KDC·부가기호, 어린이 구분)을 건수로만 출력한다. 테스트: 작은 고정본으로 건수
- [x] 6.3 `--dry-run`으로 호출 수를 세어 알리고(정보나루 525, 카카오 525, YES24 0, 한도 대비 비율) 승인을 받은 뒤 받는다. 정보나루가 막히면 카카오를 마저 받고, 다음 날 정보나루만 이어 받는다. 찾은 출처별 건수를 알린다 (2026-11-16: 카카오 525 끝, 정보나루 494 받고 31 남음. 하루 500건 한도로 보여 다음 날 이어 받는다)
- [x] 6.4 `compare`를 돌려 design "결과"에 적는다. 서명 일치율(정보나루 대 YES24, 판본 표기 지운 뒤)이 90%보다 낮으면 멈추고 규칙을 다시 정한다(design 결정 4). (2026-11-16: 67%로 멈춤 → 2026-11-17 사용자 결정으로 서명·저자는 YES24 먼저, 정보나루 서명은 정리 규칙. 6.5에서 고친다) 2026-11-17 다시 잼: 정리 뒤 85%, design "결과"에 적음
- [x] 6.5 `merge`의 서명·부제·저자 순서를 YES24 → 정보나루 → 카카오로 바꾸고, 정보나루 서명 정리 규칙(`split_title`: ` :`·` =`·` /`·` - `, 괄호 관제, 숫자 권 붙이기)을 넣는다. 테스트: 스펙 "정보나루 서명 정리"와 바뀐 "필드별 기준 출처"·"필드별 출처 기록" 시나리오. `compare`의 정보나루 서명도 정리한 값으로 잰다

## 7. 실험 장서 다시 채우기

- [x] 7.1 `scripts/seed_experiment.py --purge`와 `app/seed/experiment.py`의 지우기. 테스트(`tests/platform/test_experiment_collection.py`): 스펙 "실험 장서 지우기" 세 시나리오
- [x] 7.2 적재가 YES24 원본과 새 출처 파일을 세 출처로 합친다(`merge`, `--sources`로 출처 고르기, 순서 번호 유지, 고른 출처 모두 없는 책 건너뛰기, ISBN 없는 책의 기관 값, 새 출처 파일이 없으면 YES24만). 테스트: 스펙 "공식 서지와 가상 기관으로 적재", "실제 장서를 닮은 구성", "반복 실행과 다른 데이터 보호"의 시나리오마다, 책 키가 YES24만 적재했을 때와 같은지(작은 고정본). `uv run pytest` 통과, 테스트 DB `VACUUM ANALYZE`
- [x] 7.3 백업하고 경로를 알린다: `pg_dump`를 `/home/pollux/chaekbang-backups/chaekbang-<시각>-before-sources.dump`에, 라벨·기준 책을 `labels-<시각>-before-sources/`에 (2026-11-16: `/home/pollux/chaekbang-backups/chaekbang-20261116-2206-before-sources.dump`, `labels-20261116-2206-before-sources/`)
- [x] 7.4 비교 B 상태: `uv run python scripts/seed_experiment.py --purge && uv run python scripts/seed_experiment.py --sources data4library,kakao` → `rebuild_contributors.py --check`(차이 0) → 임베딩 서버 → `embed_books.py --incremental --kind full`(백그라운드) → `--incremental` 0건. 넣은 건수, 건너뛴 책 수, 어린이 도서 수를 알린다 (2026-11-17: 기관 도서 524권, 정보나루·카카오 모두 서명·저자가 없어 빠진 책 1권, 공식 서지 471(data4library 469, kakao 2), 어린이 143, 기여자 차이 0, 벡터 공식 471·기관 53. 측정 `runs/20261117-023607`·`023625`·`023628`)
- [x] 7.5 비교 A 상태(마지막 상태): `--purge` → 세 출처로 적재 → 한 번 더 적재(건수가 같아야 한다) → 같은 확인과 벡터 적재. 넣은 건수와 어린이 도서 수를 알린다 (2026-11-17: 기관 도서 525권, 공식 서지 472(출처 yes24 472), 두 번째 적재 건수 같음, 어린이 169, 기여자 차이 0, 벡터 공식 472·기관 53)

## 8. 같은 ISBN 다른 메타데이터 비교

- [x] 8.1 `uv run python -m evals.recommendation compare <기준 실행> <새 실행>`(지금 라벨로 다시 채점, 변형별·항목별 짝 비교, 세트 해시 검사). 테스트(`tests/evals/test_recommendation_compare.py`): 스펙 "실행 사이 비교"의 시나리오마다
- [x] 8.2 라벨을 `/home/pollux/chaekbang-backups/labels-<시각>-before-supplement/`에 백업한다. B·A 상태마다 topic(`current, vec-text, hybrid-k60, series1, mmr0.7`), similar(`sim-vec, sim-rrf, sim-vec-cat`), history(`hist-mean`)를 `--split all`로 돌린다(B는 7.4 뒤, A는 7.5 뒤). 상위 10권의 라벨 없는 책 수를 세어 알린다 (2026-11-17: 백업 `/home/pollux/chaekbang-backups/labels-20261117-0245-before-supplement/`. B `runs/20261117-023607`·`023625`·`023628`, A `20261117-024423`·`024454`·`024457`. 상위 10권의 라벨 없는 책 topic 71, 비슷한 책 83, 최근 기록 34, 합 188)
- [x] 8.3 `draft dump --pool`로 모은 라벨 없는 책에 Claude가 보충 라벨을 단다(세 출처 값을 함께 읽고, 어느 변형·상태의 책인지 보지 않고) → `draft apply --pool`. 건수와 등급별 수를 알린다 (2026-11-17: 188건, 1 이상 topic 15, 비슷한 책 15, 최근 기록 12)
- [x] 8.4 보충 라벨의 고정 표본 20건(topic 8, 비슷한 책 7, 최근 기록 5. 등급별 고르게, 해시 순서)을 사용자가 검수 화면에서 본다. 고친 것이 6건 이상이면 멈추고 기준을 다시 맞춘다. 검수 화면에 `--since <백업 라벨 파일>`을 더해 백업에 없던 라벨(이번 보충)에서만 표본을 뽑는다(2026-11-17 구현 중 더함, 테스트 `test_supplement_only_sample`) (2026-11-17: 20건 모두 봄, 고친 것 1건(topic t18 1→0), 일치율 topic 88%·비슷한 책 100%·최근 기록 100%)
- [x] 8.5 A 상태에서 같은 명령을 두 번 돌려 같은지 본다(상위 5권 라벨 없음 0, 위반 0). `compare`로 YES24 기준 실행과 A·B를 비교한다. A 안의 채택 규칙(`hybrid-k60` 대 `current`, `sim-rrf` 대 `sim-vec`, `hist-mean`)을 본다. A에서 뒤집히면 멈추고 알린다. 임베딩 서버를 내린다 (2026-11-17: 두 번 같음, A에서 세 설정 그대로, `sim-rrf`가 이번에는 채택 규칙을 넘음. 임베딩 서버 내림)
- [x] 8.6 design "결과"에 재측정 표, 실행 사이 비교(A, B), 신호 건수, 어린이 구분 차이, 라벨 수와 표본 일치율을 적는다 (2026-11-17)

## 9. 문서와 마무리

- [x] 9.1 `CLAUDE.md`: 현재 단계(결과 요약과 다음 change `add-loan-signals`), "서지 출처 YES24는 실험용" 문장들(세 출처로), 코딩 규칙의 YES24 예외 문구(실험 장서를 지우지 않음, 새 출처 파일), 기술 스택의 서지 출처, 명령(`evals.collection.sources`, `evals.recommendation compare`, `seed_experiment.py --purge/--sources`), 디렉터리 구조, 도메인 용어(공식 서지의 출처, 부가기호, 필드별 출처)
- [x] 9.2 `docs/design.md`: 공식 서지의 출처(세 출처), 외부 API 표, 카카오·정보나루 이용 조건과 서비스 전 확인 항목(카카오 캐시 조항, 정보나루 약관), 주차 표. `evals/recommendation/README.md`(`compare`, 새 출처 파일)
- [x] 9.3 `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run python -m evals.catalog_search`(기준 `20261116-205912`와 같음), `openspec validate add-bibliographic-sources --strict`가 모두 통과한다. 스펙 시나리오마다 테스트가 있는지 docstring으로 점검한다

## Workflow follow-up

- 사람이 확인한 뒤 `/opsx:archive`로 archive한다.
- 다음 change `add-loan-signals`를 제안한다.
