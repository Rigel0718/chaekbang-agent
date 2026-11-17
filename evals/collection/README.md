# 실험 장서 받기

추천 실험용 실험 장서 525권(YES24 카테고리 스테디셀러, 19개 분야, 2026-11-15에 한 번 받음)과, 같은 ISBN의 정보나루·카카오 값과 정보나루 대출 신호를 받는다. 서비스 경로가 아니다.

```bash
uv run python -m evals.collection.fetch --dry-run     # 실험 장서 받기 미리 보기 (실제 받기는 한 번만, 파일이 있으면 멈춤)
uv run python -m evals.collection.sources --dry-run   # 정보나루·카카오 값 받기 미리 보기 (출처마다 이어 받기, 다 받으면 멈춤)
uv run python -m evals.collection.compare             # 출처끼리 같은 ISBN 비교 (건수만)
uv run python -m evals.collection.loans --dry-run     # 정보나루 대출 신호(이용 분석·인기) 받기 미리 보기 (이어 받기, 다 받으면 멈춤. --overlap은 소장 겹침만)
uv run python scripts/seed_experiment.py              # 운영자: 실험 장서를 개발 DB의 `실험용 가상 작은도서관`에 넣기 (다시 돌려도 같음. --purge 지우기, --sources 합칠 출처 고르기)
```

- 받은 파일은 `data/`에 두고 저장소에 넣지 않는다(`yes24_collection.json`, `sources_collection.json`, `loan_signals.json`). YES24 이용 조건이 전체 도서 정보의 축적과 재배포를 금지하기 때문이다. 이 예외의 범위는 `docs/data-sources.md`에 있다.
- 대출 신호 파일에는 ISBN 순위와 수만 두고 서명·표지는 두지 않는다.
- 정보나루는 하루 500건 한도가 있다. 다 못 받으면 다음 날 이어 받는다.
