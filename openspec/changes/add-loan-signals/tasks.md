## 0. 시작 전

- [ ] 0.1 issue 번호를 받는다(design을 요약한 issue 제목·본문을 텍스트로 준다)
- [x] 0.2 `main`(`add-bibliographic-sources` 머지 `0be0748`)에서 브랜치 `add-loan-signals`를 만든다
- [x] 0.3 기준 수치를 남긴다(2026-11-17): `uv run pytest` 1439 통과·7 건너뜀. `topic --split all --variants current,vec-text,hybrid-k60,series1,mmr0.7`(`runs/20261117-033127`), `similar … sim-vec,sim-rrf,sim-vec-cat`(`033158`), `history … hist-mean`(`033201`)의 `results.json`이 A 최종 실행(`025721`, `025753`, `025756`)과 같다. 요약은 시각·걸린 시간 줄과, 기준 실행이 archive 커밋 전이라 커밋 줄만 다르다
- [x] 0.4 `uv run python -m evals.catalog_search` 결과가 `20261117-030343`과 같다(`evals/catalog_search/data/runs/20261117-033204`)
- [x] 0.5 `CLAUDE.md` 현재 단계의 진행 중 change를 `add-loan-signals`로 고친다. 확인: `git diff CLAUDE.md`에 그 줄만 바뀐다

## 1. 정보나루 대출 신호 응답 해석

- [x] 1.1 `app/central/external/data4library/definitions.py`에 `USAGE_ANALYSIS`, `POPULAR_LOANS` 엔드포인트, 응답 키, 연령 묶음 코드(전체·어린이 `0;6;8`·청소년 `14`·성인 `20;30;40;50;60`)를 둔다
- [x] 1.2 `parsing.py`: `UsageAnalysis`(함께 대출·마니아·다독자 ISBN 순위, 기준 책 대출 수), `PopularLoans`(ISBN 순위, 대출 수). ISBN 정리, 잘못된 ISBN 버림, 같은 ISBN은 처음만. 다른 값은 읽지 않는다
- [x] 1.3 `client.py`: `usage_analysis(isbn)`, `popular_loans(age, start, end, page_size)`. 지금 `get`을 쓴다(키, https, 중단 사유)
- [x] 1.4 테스트(`tests/external/test_data4library_loans.py`, `httpx.MockTransport`): 스펙 "정보나루 대출 신호 응답 해석"의 시나리오마다(함께 대출 순서, 잘못된 ISBN, 빈 함께 대출, 찾지 못함, 읽지 않는 값, 키 보호). 확인: `uv run pytest tests/external` 통과

## 2. 신호 코드 (제품 패키지)

- [x] 2.1 `related.py`에 `held_ranking`(ISBN 순위 → 그 기관이 가진 추천 가능한 책 순위, 공식 서지 ISBN 먼저)과 `co_loan_ranking`을 두고, `SimilarSettings.signals`에 `co_loan`을 더한다. 목록 공급 프로토콜 `LoanSignals`(`co_loans`, `popular`)를 받는다. 테스트(`tests/library/test_related_recommendation.py`): 스펙 "함께 대출 신호"의 시나리오마다, 기관 분리
- [x] 2.2 KDC 설정 `kdc_level`(`section`·`three`·`nested`)과 `kdc_order`(`title`·`vector`). 기본값은 지금과 같다. 테스트: 스펙 "같은 KDC 세목 신호"의 시나리오마다, 기본 설정의 결과가 고치기 전과 같음
- [x] 2.3 `HistorySettings.signals`(벡터 평균 방식의 기록 신호: `kdc`, `author`, `co_loan`). 기본은 벡터만이다. 테스트: 스펙 "최근 기록 합치기"의 새 시나리오(기록 신호, 기록 신호 끔)와 기존 시나리오
- [x] 2.4 `national_popular_ranking`과 채우기 순서(우리 도서관 → 정보나루, 어린이 조건이면 어린이 묶음), 빈 기록. 테스트: 스펙 "정보나루 인기로 채우기"·"빈 기록"의 시나리오마다, 다른 기관의 대출을 세지 않음(기존)
- [x] 2.5 `app/library/README.md`에 함께 대출 신호, 인기 채우기 순서, 빈 기록을 적는다. 확인: `uv run pytest` 통과, `uv run pytest tests/platform/test_package_layers.py` 통과

## 3. 대출 신호 받기

- [x] 3.1 `evals/collection/loans.py`(`uv run python -m evals.collection.loans [--dry-run]`): 대상 ISBN(정보나루 `found` + 공식 서지로 소장), 이용 분석과 인기 8조건, 호출마다 파일에 쓰기, 한도 초과 등에서 멈춤, 이어 받기, 다 받음. 테스트(`tests/evals/test_collection_loans.py`): 스펙 "정보나루 대출 신호 받기"·"대출 신호 이어 받기"의 시나리오마다
- [x] 3.2 `--overlap`: 함께 대출·마니아·다독자의 소장 겹침 분포(0, 1~2, 3 이상, 평균), 기준 책 중 비지 않은 수, 인기 조건마다 길이·가진 책·어린이 도서·추천 가능한 책. 테스트: 작은 파일로 건수
- [x] 3.3 `app/central/README.md`에 엔드포인트 셋과 남기지 않는 값을 적는다. `.gitignore`에 대출 신호 파일이 데이터 폴더로 들어가는지 확인한다(`git check-ignore`)

## 4. 실험 틀

- [x] 4.1 `evals/recommendation/signals.py`: 대출 신호 파일을 읽는 `LoanSignals` 구현, `--loan-signals`, 파일 없음(종료 코드 1), 받지 않은 ISBN 수. 테스트: 스펙 "대출 신호 파일"의 시나리오마다
- [x] 4.2 신호 건수 보고에 함께 대출(진단 둘 포함)과 정보나루 인기, 소장 겹침 줄을 더한다. 테스트: 스펙 "신호 건수 보고"의 시나리오(빈 신호, 소장 겹침)
- [x] 4.3 변형(design 결정 6·9·10): `sim-rrf-kdc0`, `sim-kdc`, `sim-rrf-kdc3`, `sim-rrf-kdcn`, `sim-rrf-kdcv`, `sim-rrf-kdc-w0.5`, `sim-rrf-kdc-w2`, `sim-vec-kdc`, `sim-kdc-best`, `sim-best-co`, `sim-co`, `sim-best-mania`, `sim-best-reader`, `hist-mean-rules`, `hist-mean-co`, `hist-mean-all`. 확인: 없는 이름은 기존처럼 종료 코드 1, `sim-best`·`hist-best`는 아직 지금 설정과 같다(`results.json`이 0.3과 같음)
- [x] 4.4 남겨 둔 분야 세트: `--holdout`(세트·라벨 파일 따로, 정해 둔 변형만), 세트 검사(스펙 "남겨 둔 분야 제외"의 새 시나리오, "남겨 둔 분야 세트"의 시나리오마다), `pick --holdout`, `draft`·`review`가 남겨 둔 분야 라벨 파일을 받는다. 확인: `uv run pytest tests/evals` 통과
- [x] 4.5 `uv run ruff check . && uv run ruff format --check .`, `uv run pytest` 통과(테스트 DB에 대량 삽입·롤백 뒤 `VACUUM ANALYZE`)

## 5. KDC 단계 (외부 호출 없음)

- [x] 5.1 `similar --split all --variants sim-vec,sim-rrf,sim-rrf-kdc0,sim-kdc,sim-rrf-kdc3,sim-rrf-kdcn,sim-rrf-kdcv,sim-rrf-kdc-w0.5,sim-rrf-kdc-w2,sim-vec-kdc`. 상위 10권의 라벨 없는 책 수를 세어 알린다
- [x] 5.2 신호 건수(단위별 비지 않은 기준 책 수)를 design "결과"에 적는다

## 6. 정보나루 받기 (승인 뒤)

- [x] 6.1 호출 수를 API별·일일 한도 대비로 다시 세어 알리고 **승인을 받는다**(design 결정 3: 확인 3, 이용 분석 469, 인기 8)
- [x] 6.2 확인 호출 3회(응답은 scratchpad에만). 응답 꼴을 design "결과"와 `api-guides/data4library_project.md`에 적고, 다르면 1.2의 고정본 테스트를 고친다
- [ ] 6.3 `uv run python -m evals.collection.loans --dry-run` → 받기. 막히면 남은 수를 알리고 다음 날 이어 받는다
- [ ] 6.4 `--overlap`의 수치를 design "결과"에 적고, 결정 4의 문턱(조정 기준 책 5권)과 결정 7의 기간(소장 겹침이 많은 쪽)을 정해 알린다

## 7. 함께 대출·최근 기록 단계와 보충

- [x] 7.1 단계 5의 승자를 `variants.py`에 반영하고 `sim-kdc-best` 확인 → 단계 6 `sim-best-co`, `sim-co`, `sim-best-mania`, `sim-best-reader` → `history --variants hist-mean,hist-mean-rules,hist-mean-co,hist-mean-all`
- [x] 7.2 라벨 백업(`/home/pollux/chaekbang-backups/labels-<시각>-before-loan-supplement/`, 경로를 알림) → 5·7.1 실행의 상위 10권 중 라벨 없는 책에 Claude가 보충 라벨(변형을 보지 않음). 건수를 알린다
- [x] 7.3 표본 검수 ①(사용자, `review similar --sample --since <백업>` 등, 20건). 고친 것이 6건 이상이면 멈춘다. 주제 세트는 보충 라벨이 없어 그 몫(8건)을 옮긴다: `review`에 `--size`를 더하고(구현 중 추가) 비슷한 책 12건·최근 기록 8건
- [ ] 7.4 기본값 확정(design 결정 10): `SimilarSettings`·`HistorySettings` 기본값, `BEST_SIM_*`·`BEST_HIST_*`. 기본값이 스펙에 적힌 값(KDC 단위·순서, 기록 신호)을 바꾸면 스펙 delta를 먼저 고치고 알린다
- [ ] 7.5 최종 두 번(같은 명령, `results.json`이 같고 요약은 시각·걸린 시간 줄만 다름). 상위 5권 라벨 없음 0, 위반 0. 결과 표를 design "결과"에 적는다

## 8. 남겨 둔 분야 비교

- [x] 8.1 남겨 둔 분야 주제 질의 8개(`sets/topic-holdout.json`, Claude), 기준 책 8권·최근 기록 4개(`pick --holdout`, Claude가 다듬고 바꾼 내역을 한 줄씩 알림)
- [x] 8.2 라벨 백업(`labels-<시각>-before-holdout/`) → 실행 전 라벨 후보 수를 세어 알림 → Claude가 실행 전 라벨(어떤 변형도 돌리기 전)
- [ ] 8.3 임베딩 서버를 띄워 새 질의 8개를 인코딩(캐시)하고 내린다 → `--holdout`으로 정해 둔 변형만 한 번 실행
- [ ] 8.4 라벨 백업(`labels-<시각>-before-holdout-supplement/`) → 보충 라벨 → 표본 검수 ②(사용자, 20건, 6건 이상 고치면 멈춤) → 같은 명령으로 최종 두 번(같은지)
- [ ] 8.5 결과 표(방향이 같음 / 반대 / 차이 없음)를 design "결과"에 적는다. 반대면 알린다(기본값은 바꾸지 않는다)

## 9. 문서와 마무리

- [ ] 9.1 `CLAUDE.md`(현재 단계·결과 요약·다음 `add-related-books`, 명령, 디렉터리 구조, 실험 장서 예외의 대출 신호 파일), `docs/design.md`(결과 한 줄, 정보나루 대출 신호와 약관 확인 항목, 주차 표), `evals/recommendation/README.md`(대출 신호 파일, 남겨 둔 분야 세트, 결과 표)
- [ ] 9.2 모든 스펙 시나리오에 테스트가 있는지 점검한다(테스트 docstring의 요구사항 이름). `uv run pytest`, `uv run ruff check . && uv run ruff format --check .` 통과, `evals.catalog_search`가 기준과 같다
- [ ] 9.3 무엇을 했는지 요약하고 멈춘다(archive는 사람이 확인한 뒤)

## 미룬 일 (2026-11-17, 사용자 결정: 기다리지 않고 다음 change로)

정보나루가 `upstream_unavailable`로 막혀(오늘 471회) 남은 11회(이용 분석 3: `9791199489509`, `9791199491717` = 조정 기준 책 `s10`, `9791199509009` / 인기 8조건)를 받지 못했다. 아래는 그것을 받은 뒤에 한다. 체크하지 않은 6.3·6.4·7.4·7.5·8.3~8.5·9.1~9.3이 이 일이다.

- [ ] D.1 호출 수(11회)를 다시 세어 승인 → `evals.collection.loans` 이어 받기 → `--overlap`으로 인기 기간(결정 7) 정하기(6.3·6.4)
- [ ] D.2 `s10`을 넣어 단계 6·최근 기록을 같은 명령으로 다시 잰다. 결과가 지금(기본값 그대로)과 다르면 보충 라벨·표본 검수부터 다시(7.4·7.5)
- [ ] D.3 남겨 둔 분야 실행(8.3~8.5). 세트와 실행 전 라벨 304건은 이미 있다
- [ ] D.4 결과 요약 문서(9.1 남은 부분: CLAUDE.md 현재 단계, docs/design.md 결과 한 줄·주차 표, README 결과 표)와 마지막 점검(9.2·9.3)

지금까지의 결론(보충 라벨·표본 검수 ① 뒤, `s10` 빈 신호): 채택 규칙을 넘은 변형이 없어 `SimilarSettings`·`HistorySettings` 기본값과 `BEST_*`는 바뀌지 않는다(`sim-rrf`, `hist-mean`). 9.2의 시나리오 점검·pytest·ruff·`evals.catalog_search`는 2026-11-17에 통과했다.
