## Why

공식 서지의 출처가 지금은 YES24 하나다. YES24는 소개·목차·시리즈·분류를 잘 주지만, 실제 KDC와 ISBN 부가기호를 주지 않는다. 그래서 같은 KDC 세목 신호를 잴 수 없고, 어린이 분류의 외부 근거가 YES24 분류 원문 셋에만 기댄다. 추천 실험 둘이 끝났으니, 지금 도서관 정보나루(KDC, 부가기호, 도서관 서지)와 카카오 책 검색(정가, 출간일, 넓은 수록 범위)을 더해 **세 출처를 필드별로 합친다**. 같은 장서를 세 출처 값으로 다시 채워, YES24 값으로 정한 추천 설정이 메타데이터가 바뀌어도 유지되는지도 잰다. YES24는 버리지 않고 세 출처 중 하나로 계속 쓴다(2026-11-16 사용자 결정).

## What Changes

- **나누기**(design 결정 1): 원래 `add-bibliographic-sources` 범위를 둘로 나눈다. 이 change는 출처 연동, 채움 일반화, 실험 장서 다시 채우기, 같은 ISBN 비교를 맡는다. 실제 KDC 세목 신호의 측정, 함께 대출된 책, 정보나루 인기, 빈 기록, 다른 분야(남겨 둔 50권) 비교, 비슷한 책 기본값 다시 보기는 다음 change `add-loan-signals`가 맡는다.
- **출처 연동**(`app/central/external/`): 정보나루 도서 상세 조회(`srchDtlList`)와 카카오 책 검색(`target=isbn`)의 클라이언트와 응답 해석을 더한다. 엔드포인트와 필드 정의는 출처마다 한곳에 둔다. 정보나루 키는 API 규칙상 쿼리 파라미터로만 보낼 수 있다. 그래서 https로 부르고, 키가 든 URL을 출력·로그·오류에 남기지 않는다.
- **공식 서지 채움 일반화**: ISBN마다 세 출처를 한 번씩 부르고 필드별 기준 출처 규칙으로 하나의 공식 서지를 만든다.
  - 정보나루: 서명·부제(서명의 ` :` 뒤), 저자 원문, 출판사, KDC, KDC 분류명, 부가기호, 권
  - YES24: 소개, 목차, 시리즈, 분류 원문, 표지, 상품 링크. 정보나루에 없는 책의 서명·저자
  - 카카오: 정가, 출간일. 정보나루·YES24에 없는 책의 서지
  - 필드마다 어느 출처에서 왔는지 공식 서지에 남긴다. 서명·저자의 출처는 `external_source`로 둔다.
- **출처별 저자 해석**: 정보나루 저자 원문(`지은이: A ;옮긴이: B`, `정세랑 (지은이)`)은 기존 기관 파일 해석기로 읽는다. 카카오는 `authors`·`translators` 배열을 정해진 꼴의 원문으로 이어 저장하고 같은 해석기로 다시 읽는다. YES24 해석기는 그대로다.
- **어린이 근거 넓히기**(`features/children`): 연결된 공식 서지의 부가기호 첫 자리 6·7(초등 학습참고서, 아동)을 외부 근거로 더한다. YES24 분류 원문 규칙은 그대로다.
- **공식 서지 칸 추가**(마이그레이션): KDC 분류명, 부가기호, 권, 필드별 출처를 더하고 출처 값에 `data4library`·`kakao`를 더한다. 조회 응답과 찾은 책 카드의 출처 표시는 표지의 출처를 따로 보여 준다.
- **실험 장서 다시 채우기**(개발 DB와 저장소 밖 파일만)
  - YES24 원본 파일과 받기 명령은 그대로 둔다.
  - 실험 장서 525권의 ISBN으로 정보나루와 카카오를 한 번 받아 새 출처 파일을 만든다. 정보나루가 하루 한도(서버 IP 미등록 시 500건)에 걸리면 정보나루만 비워 두고 카카오는 계속 받고, 다음 날 정보나루만 이어 받는다.
  - 가상 기관을 지우고 세 출처를 합친 값으로 다시 적재한다. 등록번호가 같으므로 책 키(`isbn:`·`acc:`)와 라벨이 이어진다. ISBN 없는 53권은 합친 값을 기관 값으로 쓴다.
  - 비교 수치(서명·저자 일치, 소개 길이, KDC·부가기호 채움, 어린이 구분 차이, 기여자 어긋남)를 적는다.
- **같은 ISBN 다른 메타데이터 비교**: 같은 세트와 라벨로 두 상태를 YES24 기준 실행과 항목별로 짝 비교한다. (A) 세 출처를 합친 값(제품 설정), (B) YES24를 뺀 정보나루·카카오 값(다른 출처로의 일반화). 상태마다 공식 서지 벡터(`full`)를 다시 적재하고 topic·similar·history의 기준 변형을 잰다. 새로 상위 10권에 든 라벨 없는 책에는 Claude가 보충 라벨을 단다. 사용자는 고정 표본만 본다. 개발 DB는 (A)로 끝낸다.
- **문서**: `CLAUDE.md`(현재 단계, 서지 출처, MVP 순서), `docs/design.md`(공식 서지 출처, 카카오·정보나루 이용 조건과 확인 항목), `app/central/README.md`, `.env.example`(세 키와 정보나루 IP 등록).

범위 밖은 다음과 같다.
- `add-loan-signals`에서 할 것: 같은 KDC 세목·함께 대출·정보나루 인기의 측정, 빈 기록의 "아무거나", 다른 분야 비교, 비슷한 책 기본값 다시 보기
- 평가 표본 87권(`evals/librarian/data/`, `evals/catalog_search/data/`)의 출처 바꾸기
- 이미 있는 공식 서지에 새 출처 값을 채우는 보완 실행(Open Questions)
- 시드 기관(Faker) ISBN의 채움 실행

## Capabilities

### New Capabilities

- `catalog/bibliographic-sources`: 외부 서지 출처 셋(정보나루, 카카오, YES24)의 필드별 기준 출처 규칙, 필드별 출처 기록, 정보나루·카카오 응답 해석(서명 나누기, ISBN 분해 등)

### Modified Capabilities

- `catalog/book-enrichment`: 채움이 세 출처를 조회해 공식 서지를 만든다. 찾지 못함·ISBN 불일치·장애의 판단이 세 출처 기준이 된다. API 키 보호에 쿼리 파라미터 키가 더해진다. 저장하지 않는 값에 카카오 판매가·판매 상태가 더해진다. 출처 표시에 표지 출처가 더해진다
- `catalog/book-contributors`: 출처별 해석기 고르기(정보나루·카카오는 기관 파일 해석기), 카카오 저자·역자 배열 해석
- `catalog/books`: 부가기호 저장 제약(5자리 숫자)
- `features/children`: 외부 근거에 공식 서지 부가기호 첫 자리 6·7을 더한다(갱신 포함)
- `platform/experiment-collection`: 실험 장서 ISBN으로 정보나루·카카오를 더 받기(출처마다 이어 받기), 지우기와 다시 적재, 세 출처 합치기와 출처 고르기, ISBN 없는 책의 기관 값
- `platform/recommendation-experiments`: 실행 사이의 항목별 짝 비교(같은 세트·라벨, 다른 장서 값)

## Impact

- 코드
  - 새 `app/central/external/data4library/`, `app/central/external/kakao/`, `app/central/external/http.py`·`values.py`(출처 공통), `app/central/sources.py`(필드별 기준 출처 합치기)
  - 고치는 곳: `app/central/enrichment.py`, `official_books.py`(출처 중립 값), `contributors.py`, `models.py`, `scripts/enrich_books.py`, `app/features/children/`(rules, service), `app/library/recommendation/cards.py`, `app/library/schemas/catalog.py`, `app/seed/experiment.py`, `evals/collection/`, `evals/recommendation/`(실행 비교)
- DB: 마이그레이션 하나(`books`에 칸 넷, 출처 값 둘). 개발 DB의 실험 기관과 그 공식 서지를 지우고 다시 넣는다(비교 B, A 순서로 두 번). 바꾸기 전에 `pg_dump`로 `/home/pollux/chaekbang-backups/`에 백업한다
- 외부 호출(승인 뒤에만)
  - 확인: 정보나루 3회, 카카오 3회(2026-11-16에 했다)
  - 실험 장서 받기: 정보나루 `srchDtlList` 525회, 카카오 525회, YES24 0회(원본 파일을 쓴다)
  - 카카오는 일일 한도 30,000의 약 1.8%다. 정보나루는 서버 IP를 등록하지 않으면 하루 500건이다(2026-11-16 등록)
  - LLM 호출은 없다
- 임베딩 서버: 공식 서지 벡터 `full` 다시 적재 두 번(각 약 12분, 백그라운드). 끝나면 내린다
- 사용자 시간: 받기 승인 한 번, 보충 라벨 고정 표본 검수(약 20건, 10분 이내)
- 기존 동작: 기관 API, 서명·저자 찾기(`evals.catalog_search` 기준 그대로), AI 사서 tool 목록은 그대로다. YES24 하나로 만든 공식 서지가 있는 DB에서도 조회·어린이 판단이 그대로 동작한다
