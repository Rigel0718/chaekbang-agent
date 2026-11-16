## Context

- 개발·테스트 DB(`chaekbang`, `chaekbang_test`)의 기본 collation은 `en_US.utf8`이고 제공자는 libc다. 이미지는 `pgvector/pgvector:0.8.6-pg16-trixie`(PostgreSQL 16.15)이고 ICU가 들어 있다. `ko-x-icu`의 `pg_collation_actual_version`은 `153.128.46`이다(2026-11-16).
- 2026-11-16에 같은 문자열 묶음을 세 규칙으로 줄 세워 봤다.

  | 규칙 | 결과(앞부분) |
  | --- | --- |
  | 기본 `en_US.utf8` | `나비 · 하늘 · 가나다 · … · 가나다 10 · 10대 · 가나다 2 · 2권 · … · ABC 동화 · apple · Apple · Zebra · ㄱ` |
  | `ko-x-icu` | `(기호) · 10대 · 2권 · 9살 · ㄱ · 가나다 · 가나다 10 · 가나다 2 · 나비 · 하늘 · ABC 동화 · apple · Apple · Zebra` |
  | `und-x-icu` | `(기호) · 10대 · 2권 · 9살 · ABC 동화 · apple · Apple · Zebra · ㄱ · 가나다 · …` |
  | `C`(코드 포인트) | `… · ABC 동화 · Apple · Zebra · apple · 「작은」 책 · ㄱ · 가나다 · …` |

  glibc 규칙은 한글이 가나다순이 아니고 숫자와 한글이 서로 끼어든다. 고칠 대상이 맞다.
- 서명으로 줄 세우는 곳은 8곳이다(`grep -rn "order_by\|sorted(" app/`로 2026-11-16 확인). 모두 공식 서지 값을 먼저 쓰는 표시 서명 `coalesce(books.title, library_books.title)`이거나 그것을 담은 서브쿼리 열이다.
  - `app/library/services/library_books.py` `list_library_books`: `order_by(shown_title, id)`
  - `app/library/recommendation/search.py` `ranked_query`: 점수, 대출 가능, 표시 서명, id. 키워드 검색과 깊은 키워드 순위(`topic.py`)가 함께 쓴다
  - `app/library/recommendation/lookup.py`: `find_books` 2곳(정확·포함 단계, 유사 단계), `suggest_books` 1곳, `found_in_text` 2곳(`order` 튜플과 유사 단계)
  - `app/library/recommendation/authors.py` `same_author_books`: Python `sorted`에 `shown("title")`. Python 문자열 비교는 코드 포인트 순서라 한글끼리는 가나다순이지만 숫자 → 영문 대문자 → 소문자 → 호환 자모 → 한글 순서가 되어 DB 규칙과 다르다
- 저자·시리즈명·청구기호로 줄 세우는 곳은 없다. 그 밖의 정렬은 id, 등록번호, ISBN, 날짜, 순서 번호다. `ranking.py`의 RRF·시리즈 묶기·MMR은 점수와 id로만 동점을 가른다.
- 서명 열에는 B-tree 인덱스가 없다. 찾기 키 열(`title_starts`, `author_starts`)은 서명에서 계산하는 생성 열이다.

## Goals / Non-Goals

**Goals:**

- 서명으로 줄 세우는 8곳이 같은 규칙(스펙 `platform/text-normalization`의 서명 정렬 순서)을 쓰고, 그 규칙을 한곳에서 정한다.
- 정렬 키에만 걸고 비교·검색·인덱스·생성 열에는 손대지 않는다.
- 규칙이 없는 DB에서는 조용히 다른 순서가 나오는 대신 마이그레이션에서 멈춘다.

**Non-Goals:**

- 숫자를 값으로 줄 세우기, 권차 정렬
- 저자·시리즈명 정렬(그런 정렬이 생기면 같은 도우미를 쓴다)
- DB 기본 collation이나 운영 DB 생성 방식 바꾸기

## Decisions

### 1. 정렬할 때만 `COLLATE "ko-x-icu"`를 건다 (추천, 채택)

`app/core/text.py`에 정렬 도우미 하나를 둔다.

```python
KOREAN_COLLATION = "ko-x-icu"


def korean_order(expr: ColumnElement) -> ColumnElement:
    """서명 정렬 순서(가나다). ORDER BY 키에만 쓴다. 비교·검색에는 쓰지 않는다."""
    return expr.collate(KOREAN_COLLATION)
```

8곳의 서명 정렬 키를 `korean_order(...)`로 감싼다. SQL은 `ORDER BY coalesce(books.title, library_books.title) COLLATE "ko-x-icu"`가 된다. `COLLATE`는 그 식의 정렬에만 적용되므로 `=`, `LIKE`, `strpos`, `levenshtein`, 자모 키 비교는 지금과 같다. 도우미를 `core`에 두는 이유는 정렬 규칙이 비교용 정규화(`compact_sql`)와 같은 층의 텍스트 규칙이고, `library`와 이후 `central`도 쓸 수 있어야 해서다(의존 방향 `library → core`에 맞다).

같은 저자 조회는 SQL에서 `korean_order(표시 서명), id`로 받아 온 뒤 Python에서 겹치는 지은이 수로만 안정 정렬한다(`sorted`는 안정 정렬이라 같은 수 안에서는 SQL 순서가 남는다). Python에 같은 규칙을 다시 만들지 않는다.

비교한 다른 안:

| 안 | 비용 | 인덱스·생성 열 영향 | 판단 |
| --- | --- | --- | --- |
| **정렬할 때만 `COLLATE`** | 코드 8곳, 마이그레이션은 확인만 | 없음. 지금도 서명 인덱스가 없고 결과는 한 기관 범위라 정렬 비용은 같다 | 채택 |
| 컬럼 collation 바꾸기(`books.title`, `library_books.title`를 `ko-x-icu`로) | 마이그레이션. 두 열에 기대는 생성 열 4개(`*_starts`)를 지웠다 다시 만들어야 하고 테이블을 다시 쓴다 | `=`·`LIKE`도 ICU 규칙이 되어 `LIKE` 앞부분 최적화가 막히고, 앞으로 서명 인덱스를 만들면 ICU 버전이 바뀔 때마다 `REINDEX`가 필요하다. 새 텍스트 식(`coalesce`, 서브쿼리)마다 collation이 따라오는지 확인해야 한다 | 비교에까지 번져 이 change의 조건(비교 불변)을 깬다 |
| DB 기본 collation 바꾸기(`--locale-provider=icu --icu-locale=ko`로 DB 다시 만들기) | 개발·테스트 DB 덤프·재생성·복원, `docker-compose`·초기화 스크립트 변경, 운영 DB 생성 절차까지 묶임 | 모든 텍스트 인덱스와 비교 규칙이 바뀌고 ICU 버전에 묶인다 | 반나절 범위를 넘고 위험이 크다. 운영 배포(`add-observability-deploy`) 때 다시 볼 수 있다 |
| Python에서 정렬 | 가나다 규칙을 맞추려면 PyICU(C 라이브러리 의존) 또는 직접 키 함수 | DB `LIMIT`·`OFFSET` 앞에서 정렬해야 하므로 기관 도서 전체를 읽어야 한다. 목록 페이지와 찾기 개수 제한이 깨진다 | 맞지 않음 |

### 2. collation 확인은 마이그레이션에 둔다 (추천, 채택)

새 Alembic 마이그레이션 하나가 `pg_collation`에 `ko-x-icu`가 있는지 보고, 없으면 `RuntimeError("PostgreSQL에 'ko-x-icu' collation이 없습니다. ICU로 빌드된 서버가 필요합니다")`로 멈춘다. 테이블·열은 바꾸지 않고 `downgrade`는 아무것도 하지 않는다. 확인 함수는 collation 이름을 인자로 받는 작은 함수(`app/core/migrations.py`의 `require_collation(connection, name)`)로 두고, 마이그레이션은 이것을 부른다. 테스트는 있는 이름과 없는 이름으로 이 함수를 불러 두 시나리오를 확인한다(실제 collation을 지우지 않는다).

- 마이그레이션에 두는 이유: 개발 DB, 테스트 DB(`conftest.py`가 `alembic upgrade head`), 평가(`evals.catalog_search`도 upgrade)가 모두 이 길을 지난다. 한 번 확인하면 되고 요청마다 비용이 없다.
- 시작 시점 확인(FastAPI lifespan)은 스크립트(`embed_books.py`, `evals.*`)가 앱을 띄우지 않아 빠지는 곳이 있고, 확인 쿼리가 서버를 띄울 때마다 돈다. 하지 않는다.
- 확인 없이 두면 ICU 없는 서버에서 정렬 쿼리마다 `collation "ko-x-icu" for encoding "UTF8" does not exist` 오류가 나서 원인은 드러나지만, 찾기 API가 500을 낸 뒤에야 안다.

### 3. 숫자는 글자 순서로 둔다 (추천, 채택)

`ko-x-icu`는 숫자를 글자로 본다(`가나다 10` < `가나다 2`). 숫자를 값으로 보려면 `CREATE COLLATION ko_numeric (provider = icu, locale = 'ko-u-kn-true')`로 새 collation을 마이그레이션에서 만들어야 한다. 서명의 숫자는 권차뿐 아니라 `10대`, `9살`, `2025 트렌드` 같은 뜻이 섞여 있고, 권차 순서는 시리즈 묶기(`add-related-books`에서 다시 정함)와 함께 보는 편이 맞다. 이번에는 기본 `ko-x-icu`를 쓰고, 바꾸고 싶어지면 도우미의 이름 하나만 바꾸면 된다.

### 4. 스펙 위치

정렬 규칙 자체는 `platform/text-normalization`(텍스트 규칙의 기준)에 하나로 두고, 각 기능 스펙은 "표시 서명의 서명 정렬 순서"를 가리키며 동점 순서를 적는다. 기관 도서 목록과 같은 저자 조회는 지금 스펙에 순서가 없어 이번에 적는다. 문장 속 서명 찾기(`agent/librarian`의 찾은 책 카드)는 스펙에 순서가 없고 서명 길이가 같은 책끼리만 영향을 받으므로 스펙은 바꾸지 않고 코드만 같은 도우미를 쓴다. 깊은 키워드 순위(`catalog/topic-recommendation`)는 "키워드 검색과 같은 순서 규칙"이라 따로 고치지 않는다.

## Risks / Trade-offs

- [동점 순서가 바뀌어 평가 수치가 움직인다] → 고치기 전 기준을 남겼다: `uv run pytest` 1198 통과·7 건너뜀, `evals.catalog_search` `data/runs/20261116-035252`(지난 기준 `20261116-033720`과 같음), 추천 실험 `topic` `evals/recommendation/data/runs/20261116-035334`. 끝난 뒤 다시 돌려 바뀐 수치의 전후와 이유(어느 질의에서 어느 책이 동점으로 앞뒤가 바뀌었는지)를 보고하고, 평가나 추천 설정은 고치지 않는다.
- [개수 제한 경계에서 잘리는 책이 바뀐다] → 점수·단계가 같은 책 사이의 일이라 스펙상 어느 쪽도 맞다. 위 평가 비교에 드러난다.
- [ICU 라이브러리 버전이 바뀌면 순서가 미세하게 바뀔 수 있다] → collation을 인덱스에 쓰지 않으므로 `REINDEX`는 필요 없다. 이미지를 올린 뒤 PostgreSQL이 collation 버전 불일치 경고를 내면 `ALTER COLLATION "ko-x-icu" REFRESH VERSION`으로 기록만 맞춘다. 테스트가 가나다 시나리오를 확인하므로 순서가 크게 바뀌면 테스트가 잡는다.
- [기존 순서 테스트가 영문·숫자 서명 순서에 기대고 있을 수 있다] → 구현 중 실패하는 테스트는 기대 순서가 새 규칙에서 맞는지 보고 고친다. 고친 테스트는 보고한다.
- [`COLLATE`를 붙인 정렬이 느려진다] → ICU 비교는 glibc보다 대체로 빠르거나 비슷하고, 정렬 대상은 한 기관의 맞은 책이다. `test_book_lookup_speed`(200ms)가 확인한다. 대량 삽입 테스트 뒤에는 테스트 DB에 `VACUUM ANALYZE`를 한다.

## Migration Plan

1. 개발 DB를 `pg_dump`로 `/home/pollux/chaekbang-backups/`에 백업하고 경로를 알린다.
2. `uv run alembic upgrade head`(확인 마이그레이션만, 스키마 변화 없음). 명령은 `&&`로 잇는다.
3. 되돌리기: `uv run alembic downgrade -1`(아무것도 하지 않는 downgrade). 코드는 브랜치를 되돌리면 이전 순서로 돌아간다. 데이터는 바뀌지 않는다.

## 결과 (2026-11-16)

- 테스트: 1216 통과·7 건너뜀(기준 1198 + 새 시나리오 테스트 18). 새 정렬 테스트 11개 중 9개는 고치기 전 코드에서 실패한다(순수 한글 같은 저자 순서와 표시 서명 기준 목록은 전에도 맞았다). 기대를 고친 기존 테스트는 `tests/evals/test_recommendation_run.py::test_runs_without_llm` 하나다. `공룡 어린이책`과 `공룡 일반서`가 키워드 점수가 같은데, 1위의 라벨 값이 예전 glibc 순서(일반서 먼저)에 기대고 있었다.
- 서명·저자 찾기 평가(`evals/catalog_search/data/runs/20261116-104322`, 기준 `20261116-035252`). 바뀐 수치는 모두 같은 단계·같은 점수인 두 책의 앞뒤가 바뀐 것이다. `korean_order`를 끈 실행과 질의별로 비교해 확인했다.

  | 종류 | 1위 전 → 후 | 다른 변화 | 예 |
  | --- | --- | --- | --- |
  | word | 87.7% → 90.4% (+2) | MRR 0.92 → 0.93 | `과학`: `다있소 과학 1`이 `어린이 과학백과 시리즈 세트`보다 앞, `아이들`: `법 만드는 아이들`이 `세금 내는 아이들`보다 앞 |
  | author | 88.6% 그대로 | 같은 저자 두 권의 1위가 맞바뀜(+2, −2) | `앤 카슨`, `옥효진` |
  | vowel | 84.0% → 82.7% (−1) | MRR 0.90 → 0.89 | `클료드`: 같은 유사도의 `뚝딱 바로 써먹는 AI 3대장 …`이 앞 |
  | final | 82.9% → 81.6% (−1) | 5위 안 97.4% → 98.7%, MRR 0.89 → 0.88 | `자고`: 대상이 6위 → 1위 |
  | key | 81.3% 그대로 | 맞바뀜(+2, −2) | |
  | suggest | 87.6% 그대로 | MRR 0.94 → 0.93, 맞바뀜 13건씩 | `빵도둑`: `빵도둑과 디저트 왕자`가 `빵도둑과 따끈따끈 빵차`보다 앞 |
  | 기준선 word | 87.7% → 86.3% (−1) | MRR 0.92 → 0.91 | `전하는` |

  표본의 질의는 대상 책 하나를 정해 두므로, 같은 점수인 두 책 중 어느 쪽이 대상이냐에 따라 오르내린다. 품질 변화가 아니라 동점 순서가 정해진 것으로 본다.
- 추천 실험 topic(`evals/recommendation/data/runs/20261116-104400`, 기준 `20261116-035334`). 키워드 점수는 동점이 많아 상위 5권이 `current`는 30개 중 24개, `hybrid-k60`는 20개 질의에서 바뀌었다. 상위 5권에 라벨 없는 책이 새로 들어왔다(`current` 4건, `hybrid-k60` 2건, 전에는 0건). 라벨 없는 책은 지표에서 0으로 세므로 수치가 조금 낮게 나올 수 있다. 규칙 위반은 그대로 0건이다.

  | 세트 | `current` nDCG@5 전 → 후 | `hybrid-k60` nDCG@5 전 → 후 | 차이 전 → 후 (95% 구간) |
  | --- | --- | --- | --- |
  | 조정(20) | 0.410 → 0.446 | 0.517 → 0.516 | +0.107 → +0.070 (+0.024 ~ +0.116) |
  | 확인(10) | 0.421 → 0.384 | 0.549 → 0.522 | +0.128 → +0.139 (+0.069 ~ +0.217) |

  `hybrid-k60`가 두 세트에서 모두 이기는 결론은 그대로다. 평가와 설정은 고치지 않았다. 라벨 없는 6건에 pool 라벨을 달면 수치를 다시 맞출 수 있다(이 change 범위 밖).
