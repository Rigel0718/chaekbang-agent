# 대화 추천 평가

실제 LLM과 대화해 AI 사서가 카드로 낸 추천을, 추천 실험의 어울림 라벨로 채점한다. 프롬프트·tool·모델을 바꾼 버전끼리 같은 라벨로 비교하는 점수표다. **실제 LLM을 부르므로 돌리기 전에 호출 수와 비용을 알리고 승인받는다.**

```bash
docker compose --profile embedding up -d embedder        # 실행 동안 필요(질의 인코딩)
uv run python -m evals.conversation                      # 세 세트 60항목 (--sets topic, --only t01,s01, --model)
uv run python -m evals.conversation.compare <실행> <실행>   # 지금 라벨로 다시 채점해 나란히 (LLM·DB 없음)
uv run python -m evals.recommendation.draft dump topic --pool <실행>   # 라벨 없는 카드·tool 앞 5권 보충 (similar, history도)
uv run python -m evals.recommendation topic --keywords-from <실행> --split all --variants hybrid-k60,hybrid-best   # 실제 LLM 낱말로
```

- **장서**: 실험 장서 525권을 개발 DB와 같은 적재 코드(`seed_experiment`)로 **테스트 DB**(`TEST_DATABASE_URL`)의 트랜잭션 안에 넣고, 끝나면 모두 되돌린다. 개발 DB는 쓰지 않는다. 책 키(`isbn:`/`acc:`)가 개발 DB 실험 장서와 같아 추천 실험의 라벨을 그대로 쓴다. 평가가 도는 동안 pytest를 돌리지 않는다.
- **벡터**: 두 층을 운영자 실행과 같은 코드로 넣는다. 문서 벡터는 `data/doc_vectors.json`에 캐시해 처음 한 번만 인코딩한다(525권 약 12분). 질의는 LLM 낱말이 실행마다 달라 임베딩 서버가 필요하고, 같은 질의는 `data/query_vectors.json`에서 꺼낸다.
- **세트 → 대화**: 주제(`topic` 30)는 이용자 문장 한 턴이다. 비슷한 책(`similar` 20)은 기준 책을 고른 턴(LLM 없음) 뒤 `이 책이랑 비슷한 책 있어요?`다. 최근 기록(`history` 10)은 기록의 책을 차례로 고른 턴 뒤 `아무거나 추천해 줘`다. 기준 책·기록의 책이 모두 어린이 도서면 어린이 요청 문장을 쓴다.
- **채점**: 카드(최대 5권)와, 처음 부른 책 tool 결과의 앞 5권을 Hit@5·Recall@5(분모 min(R, 5))·nDCG@5로 잰다. 묶음은 주제어, 상황, 어린이, 비슷한 책, 아무거나다. 라벨 없는 책은 0으로 세고, 있으면 요약 첫머리에 "라벨 보충 전"이 붙는다.
- **규칙 검사**: AI 사서 평가(`evals/librarian/checks.py`)와 같다. 위반이 있으면 종료 코드 1이다.
- **tool 입력**: 검색 낱말과 tool 결과의 책은 평가가 tool handler를 감싸 받아 결과 파일에만 쓴다. 제품 실행 기록에는 여전히 남지 않는다.
- **라벨 보충**: 실행 뒤 라벨 파일(`evals/recommendation/data/labels/`)을 먼저 백업한다. 그다음 Claude 초안(`draft dump/apply <세트> --pool <실행>`, 단계 `pool`), 고정 표본 검수(`review <세트> --sample --since <백업>`) 순서다. 표본의 30% 이상을 고치면 멈춘다.
- **실행 사이 비교**: `compare`는 저장된 카드를 지금 라벨로 다시 채점한다. 세트 해시가 다르면 멈춘다.

## 파일

| 위치 | 내용 | 저장소 |
| --- | --- | --- |
| `data/doc_vectors.json`, `data/query_vectors.json` | 문서·질의 벡터 캐시 | 뺀다 |
| `data/runs/<시각>-<모델>/` | 항목별 JSON, `items.json`(비교용), `results-<세트>.json`(보충 도구 형식, 변형 `chat`), `summary.md`, `compare-<기준>.md` | 뺀다 |

결과에는 실험 장서 서지와 책 키가 들어 있어 저장소에 넣지 않는다. 장서는 YES24 스테디셀러이고 기관·사본은 가상이다. 라벨은 Claude 초안에 사람이 표본만 검수한 것이라, 수치는 같은 라벨에서 버전끼리 비교할 때만 쓴다.
