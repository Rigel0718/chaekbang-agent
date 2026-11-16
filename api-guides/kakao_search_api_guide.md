# 카카오 책 검색 API 정리

> 출처: [Kakao Developers - 다음 검색 > 책 검색](https://developers.kakao.com/docs/ko/daum-search/dev-guide#search-book)
> 정리일: 2026-11-16

질의어로 도서 정보를 검색해 결과를 돌려주는 API입니다.

---

## 1. 기본 정보

| 항목 | 내용 |
|---|---|
| 메서드 | `GET` |
| URL | `https://dapi.kakao.com/v3/search/book` |
| 인증 | REST API 키 |
| 용도 | 질의어에 맞는 도서 정보 검색 |

---

## 2. 요청 (Request)

### 2-1. 헤더

| 이름 | 설명 | 필수 |
|---|---|---|
| `Authorization` | `KakaoAK ${REST_API_KEY}` 형식의 REST API 키 | O |

### 2-2. 쿼리 파라미터

| 이름 | 타입 | 설명 | 필수 | 기본값 / 범위 |
|---|---|---|---|---|
| `query` | String | 검색 질의어 | O | - |
| `sort` | Enum | 정렬 방식<br>`accuracy`: 정확도순<br>`latest`: 발간일순 | X | 기본값 `accuracy` |
| `page` | Integer | 결과 페이지 번호 | X | 1 ~ 50, 기본값 1 |
| `size` | Integer | 한 페이지에 보여줄 문서 수 | X | 1 ~ 50, 기본값 10 |
| `target` | Enum | 검색 필드 제한<br>`title`: 제목<br>`isbn`: ISBN<br>`publisher`: 출판사<br>`person`: 인명 | X | 미지정 시 전체 필드 |

> ⚠️ 다른 다음 검색 API(웹, 블로그 등)는 최신순 값이 `recency`지만, **책 검색은 `latest`** 입니다.

---

## 3. 응답 (Response)

본문 최상위는 `meta`와 `documents` 두 키로 구성됩니다.

### 3-1. `meta`

| 이름 | 타입 | 설명 |
|---|---|---|
| `total_count` | Integer | 검색된 전체 문서 수 |
| `pageable_count` | Integer | 중복을 제외하고, 첫 페이지부터 요청 페이지까지 노출 가능한 문서 수 |
| `is_end` | Boolean | 현재 페이지가 마지막인지 여부. `false`면 `page`를 올려 다음 페이지 요청 가능 |

### 3-2. `documents[]`

| 이름 | 타입 | 설명 |
|---|---|---|
| `title` | String | 도서 제목 |
| `contents` | String | 도서 소개 |
| `url` | String | 도서 상세 페이지 URL |
| `isbn` | String | ISBN10 또는 ISBN13. 둘 다 있으면 공백으로 구분 (예: `"8996991341 9788996991342"`) |
| `datetime` | Datetime | 출판일 (ISO 8601, `[YYYY]-[MM]-[DD]T[hh]:[mm]:[ss].000+[tz]`) |
| `authors` | String[] | 저자 목록 |
| `publisher` | String | 출판사 |
| `translators` | String[] | 번역자 목록 |
| `price` | Integer | 정가 |
| `sale_price` | Integer | 판매가 |
| `thumbnail` | String | 표지 미리보기 이미지 URL |
| `status` | String | 판매 상태 (정상, 품절, 절판 등). 값이 바뀔 수 있으니 문자열 비교 로직에 쓰지 말고 표시용으로만 사용 권장 |

---

## 4. 예제

### 4-1. 요청 (curl)

```bash
curl -v -G "https://dapi.kakao.com/v3/search/book?target=title" \
  --data-urlencode "query=미움받을 용기" \
  -H "Authorization: KakaoAK ${REST_API_KEY}"
```

- `-G` + `--data-urlencode`: 한글 질의어를 URL 인코딩해 쿼리스트링으로 붙임
- `target=title`: 제목에서만 검색

### 4-2. 응답 (HTTP 200)

```json
{
  "meta": {
    "is_end": true,
    "pageable_count": 9,
    "total_count": 10
  },
  "documents": [
    {
      "title": "도서 제목",
      "contents": "도서 소개 일부...",
      "url": "https://search.daum.net/search?w=bookpage&bookId=...",
      "isbn": "ISBN10 ISBN13",
      "datetime": "2014-11-17T00:00:00.000+09:00",
      "authors": ["저자"],
      "publisher": "출판사",
      "translators": ["번역자"],
      "price": 14900,
      "sale_price": 13410,
      "thumbnail": "https://search1.kakaocdn.net/thumb/...",
      "status": "정상판매"
    }
  ]
}
```

> 응답 값(제목, 가격, URL 등)은 구조를 보여주기 위한 예시이며, 실제 값은 호출 결과로 확인하세요.

---

## 5. 공통 사항

- **인증**: 모든 다음 검색 API는 `Authorization: KakaoAK ${REST_API_KEY}` 헤더 사용
- **에러**: 별도 REST API 에러 코드 문서 참고
- **테스트**: 개발자 사이트 [도구] > REST API 테스트에서 바로 호출 가능
- **페이징**: `meta.is_end`가 `false`인 동안 `page`를 1씩 증가 (최대 50)

---

## 6. (참고) Python 호출 예시

공식 문서에는 없는 내용으로, FastAPI 백엔드에서 쓰기 좋은 `httpx` 비동기 예시입니다.

```python
import os
import httpx

KAKAO_BOOK_URL = "https://dapi.kakao.com/v3/search/book"


async def search_books(
    query: str,
    *,
    target: str | None = None,   # "title" | "isbn" | "publisher" | "person"
    sort: str = "accuracy",      # "accuracy" | "latest"
    page: int = 1,
    size: int = 10,
) -> dict:
    headers = {"Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}"}
    params = {"query": query, "sort": sort, "page": page, "size": size}
    if target:
        params["target"] = target

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(KAKAO_BOOK_URL, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
```

### 체크 포인트

- `isbn`은 공백으로 나눈 뒤 13자리 값을 대표 키로 쓰면 중복 제거가 쉬움 → `isbn.split()`
- `datetime`은 빈 문자열일 수 있으니 파싱 전에 확인
- `page`, `size` 최대치가 각각 50이라 한 질의로 가져올 수 있는 결과는 많아야 2,500건