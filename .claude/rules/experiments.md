---
paths:
  - "evals/**"
  - "app/library/recommendation/**"
  - "scripts/seed_experiment.py"
  - "app/seed/experiment*"
---

# 추천 실험 규칙

- 명령은 `evals/recommendation/README.md`(실행·라벨·검수·비교)와 `evals/collection/README.md`(실험 장서 받기·적재)에 있다. 확정된 기본값과 수치는 `docs/roadmap.md`에 있다.
- 실험 장서는 YES24 카테고리 스테디셀러 525권(19개 분야)이고 개발 DB의 `실험용 가상 작은도서관`이 소장한다. 서비스 데이터가 아니다.
- 종교·예술·건강 취미·여행 50권은 남겨 둔 분야다. 조정에 쓰지 않고 정해 둔 변형만 확인용으로 한 번 잰다(`--holdout`).
- 라벨은 Claude가 초안을 단다. 사람은 고정 표본만 본다(약 15분). 전수 검수를 전제로 설계하지 않는다. 라벨이 LLM 판단에 기대므로 수치는 같은 세트·같은 라벨에서 방식끼리 비교할 때만 쓴다.
- 채택 규칙: 조정 세트에서 평균 차이 > 0, 이김 > 짐, 부트스트랩 95% 구간 하한 > 0이면 채택하고, 아니면 단순한 쪽을 둔다. 확인 세트는 마지막에 한 번 본다.
- 장서 값을 바꾼 전후는 `evals.recommendation compare`로 같은 라벨에서 짝 비교한다.
