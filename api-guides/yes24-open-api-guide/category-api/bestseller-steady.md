# 스테디셀러 조회

## 개요

스테디셀러 조회 API는 긴 기간 동안 꾸준히 판매되는 스테디셀러 목록을 조회합니다.

## Endpoint

```
GET
https://apis.yes24.com/v1/category/bestsellerSteady
```

## Query Parameters

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `categoryId` | string | 필수 | - | 카테고리 ID |
| `page` | integer | 선택 | 1 | 페이지 번호 |
| `pageSize` | integer | 선택 | 20 | 페이지 크기(최대 100) |
| `detail` | string | 선택 | N | 상세 정보 포함 여부(Y 또는 N) |

## Request Example

```shell
curl -X GET "https://apis.yes24.com/v1/category/bestsellerSteady?categoryId=001" -H "X-Api-Key: YOUR_API_KEY"
```

## Response Example

### 1. `detail=N` 기본

`GoodsSimpleInfo` — 기본 필드만 반환합니다.

```json
{
  "success": true,
  "message": "성공",
  "errorCode": null,
  "data": {
    "meta": {
      "apiTitle": "스테디셀러 조회",
      "apiLink": "https://apis.yes24.com/v1/category/bestsellerSteady?categoryId=001",
      "logoUrl": "https://image.yes24.com/sysimage/apis/openapi/images/logoN4.svg",
      "pubDate": "2026-07-14T09:16:14+09:00",
      "query": "?categoryId=001",
      "version": "v1"
    },
    "items": [
      {
        "sortOrder": 1,
        "itemId": 12345678,
        "title": "클린 코드",
        "author": "로버트 C. 마틴",
        "goodsType": "국내도서",
        "goodsSortNm": "국내도서",
        "adultYn": "N",
        "publisher": "인사이트",
        "isbn10": "8966260950",
        "isbn13": "9788966260959",
        "shopPrice": 33000,
        "salePrice": 29700,
        "publishDate": "2013-12-24",
        "itemStatus": "판매중",
        "cover": "https://image.yes24.com/goods/12345678/L",
        "sideCover": "https://image.yes24.com/goods/12345678/SIDE/L",
        "backCover": "https://image.yes24.com/goods/12345678/BACK/L",
        "link": "https://www.yes24.com/product/goods/12345678",
        "addOnLink": "",
        "upDown": null,
        "contentDetail": {
          "bookIntroduction": "소프트웨어 장인 정신을 담은 도서입니다. 깨끗한 코드를 작성하는 방법을 알려줍니다.",
          "bookSummary": null,
          "tableOfContents": "1장 깨끗한 코드\n2장 의미 있는 이름\n3장 함수\n..."
        }
      }
    ],
    "currentPage": 1,
    "pageSize": 20,
    "totalCount": 100
  }
}
```

### 2. `detail=Y` 확장

`GoodsInfo` — 확장 필드(페이지 수, 평점, 시리즈, 콘텐츠 등)가 추가됩니다.

```json
{
  "success": true,
  "message": "성공",
  "errorCode": null,
  "data": {
    "meta": {
      "apiTitle": "스테디셀러 조회",
      "apiLink": "https://apis.yes24.com/v1/category/bestsellerSteady?categoryId=001",
      "logoUrl": "https://image.yes24.com/sysimage/apis/openapi/images/logoN4.svg",
      "pubDate": "2026-07-14T09:16:14+09:00",
      "query": "?categoryId=001",
      "version": "v1"
    },
    "items": [
      {
        "sortOrder": 1,
        "itemId": 12345678,
        "title": "클린 코드",
        "subTitle": "애자일 소프트웨어 장인 정신",
        "author": "로버트 C. 마틴",
        "goodsType": "국내도서",
        "goodsSortNm": "국내도서",
        "adultYn": "N",
        "publisher": "인사이트",
        "isbn10": "8966260950",
        "isbn13": "9788966260959",
        "shopPrice": 33000,
        "salePrice": 29700,
        "publishDate": "2013-12-24",
        "itemStatus": "판매중",
        "originalTitle": null,
        "originalTranslation": null,
        "yesPoint": 1650,
        "salePoint": 99999,
        "fixedBookPriceYn": "Y",
        "pages": 584,
        "weight": null,
        "width": null,
        "length": null,
        "height": null,
        "itemFormat": null,
        "starScore": 9.4,
        "cover": "https://image.yes24.com/goods/12345678/L",
        "sideCover": "https://image.yes24.com/goods/12345678/SIDE/L",
        "backCover": "https://image.yes24.com/goods/12345678/BACK/L",
        "link": "https://www.yes24.com/product/goods/12345678",
        "addOnLink": "",
        "mobileLink": "https://m.yes24.com/goods/detail/12345678",
        "eBookLink": null,
        "ebookId": null,
        "upDown": null,
        "contentDetail": {
          "bookIntroduction": "소프트웨어 장인 정신을 담은 도서입니다. 깨끗한 코드를 작성하는 방법을 알려줍니다.",
          "bookSummary": null,
          "tableOfContents": "1장 깨끗한 코드\n2장 의미 있는 이름\n3장 함수\n..."
        },
        "series": [
          {
            "seriesId": 10001,
            "seriesName": "마틴 파울러 시리즈"
          }
        ]
      }
    ],
    "currentPage": 1,
    "pageSize": 20,
    "totalCount": 100
  }
}
```

## Response Fields

detail 파라미터 값에 따라 반환 필드가 달라집니다. 
N+Y 공통  
Y only detail=Y 전용

| 필드 | 타입 | N | Y | 설명 |
|------|------|---|---|------|
| `success` | boolean | ✓ | ✓ | 요청 성공 여부 |
| `message` | string | ✓ | ✓ | 응답 메시지 |
| `errorCode` | string · nullable | ✓ | ✓ | 오류 코드(성공 시 null) |
| `data.meta.apiTitle` | string | ✓ | ✓ | 호출한 API 제목 |
| `data.meta.apiLink` | string | ✓ | ✓ | 요청 URL |
| `data.meta.logoUrl` | string | ✓ | ✓ | 예스24 로고 URL |
| `data.meta.pubDate` | string | ✓ | ✓ | 응답 일시(ISO 8601) |
| `data.meta.query` | string | ✓ | ✓ | 요청 QueryString |
| `data.meta.version` | string | ✓ | ✓ | API 버전 |
| `data.items` | array | ✓ | ✓ | 상품 목록 |
| `data.currentPage` | integer | ✓ | ✓ | 현재 페이지 번호 |
| `data.pageSize` | integer | ✓ | ✓ | 페이지 크기 |
| `data.totalCount` | integer | ✓ | ✓ | 전체 데이터 수 |
| `data.items[].sortOrder` | integer | ✓ | ✓ | 목록 내 순서 |
| `data.items[].itemId` | integer | ✓ | ✓ | 예스24 상품 번호 |
| `data.items[].title` | string | ✓ | ✓ | 상품 제목 |
| `data.items[].author` | string | ✓ | ✓ | 저자 또는 아티스트명 |
| `data.items[].goodsType` | string | ✓ | ✓ | 상품 유형 |
| `data.items[].goodsSortNm` | string | ✓ | ✓ | 관리 분류 |
| `data.items[].adultYn` | string | ✓ | ✓ | 성인물 여부(Y/N) |
| `data.items[].publisher` | string | ✓ | ✓ | 출판사 |
| `data.items[].isbn10` | string | ✓ | ✓ | ISBN10 |
| `data.items[].isbn13` | string | ✓ | ✓ | ISBN13 |
| `data.items[].shopPrice` | decimal | ✓ | ✓ | 정가 |
| `data.items[].salePrice` | decimal | ✓ | ✓ | 판매가 |
| `data.items[].publishDate` | string | ✓ | ✓ | 출간일 |
| `data.items[].itemStatus` | string | ✓ | ✓ | 판매 상태 |
| `data.items[].cover` | string | ✓ | ✓ | 커버 이미지 URL (미등록 상품은 대체 이미지 반환) |
| `data.items[].sideCover` | string | ✓ | ✓ | 책등 이미지 URL (미등록 상품은 대체 이미지 반환) |
| `data.items[].backCover` | string | ✓ | ✓ | 뒷표지 이미지 URL (미등록 상품은 대체 이미지 반환) |
| `data.items[].link` | string | ✓ | ✓ | 예스24 원본 상품 상세 URL |
| `data.items[].addOnLink` | string | ✓ | ✓ | 애드온 클릭 URL. 애드온 미신청 상태에서는 공란 |
| `data.items[].upDown` | integer · nullable | ✓ | ✓ | 베스트셀러 등락 값 |
| `data.items[].contentDetail` | object · nullable | ✓ | ✓ | 상품 소개/요약/목차 |
| `data.items[].contentDetail.bookIntroduction` | string · nullable | ✓ | ✓ | 책 소개 |
| `data.items[].contentDetail.bookSummary` | string · nullable | ✓ | ✓ | 줄거리 |
| `data.items[].contentDetail.tableOfContents` | string · nullable | ✓ | ✓ | 목차 |
| `data.items[].subTitle` | string | - | ✓ | 부제목 |
| `data.items[].originalTitle` | string · nullable | - | ✓ | 원제 |
| `data.items[].originalTranslation` | string · nullable | - | ✓ | 번역서 여부 |
| `data.items[].yesPoint` | integer · nullable | - | ✓ | YES 포인트 |
| `data.items[].salePoint` | integer · nullable | - | ✓ | 판매지수 |
| `data.items[].fixedBookPriceYn` | string | - | ✓ | 도서정가제 여부(Y/N) |
| `data.items[].pages` | integer · nullable | - | ✓ | 페이지 수 |
| `data.items[].weight` | integer · nullable | - | ✓ | 무게(g) |
| `data.items[].width` | integer · nullable | - | ✓ | 가로(mm) |
| `data.items[].length` | integer · nullable | - | ✓ | 세로(mm) |
| `data.items[].height` | integer · nullable | - | ✓ | 높이(mm) |
| `data.items[].itemFormat` | string · nullable | - | ✓ | 판형 |
| `data.items[].starScore` | double | - | ✓ | 리뷰 평점 |
| `data.items[].mobileLink` | string | - | ✓ | 모바일 상품 링크 |
| `data.items[].eBookLink` | string · nullable | - | ✓ | 연결된 eBook 링크 |
| `data.items[].ebookId` | integer · nullable | - | ✓ | 연결된 eBook 상품번호 |
| `data.items[].series` | array | - | ✓ | 시리즈 목록 |
| `data.items[].series[].seriesId` | integer | - | ✓ | 시리즈 번호 |
| `data.items[].series[].seriesName` | string | - | ✓ | 시리즈명 |


## 오류 코드

| HTTP | 오류 코드 | 설명 |
|------|-----------|------|
| **401** | `AUTH_001` | API Key 값이 없습니다. |
| **401** | `AUTH_002` | 유효하지 않은 API Key입니다. |
| **400** | `PARAM_001` | categoryId 파라미터를 입력하세요. |
| **400** | `PARAM_006` | pageSize는 1에서 100 사이의 값이어야 합니다. |
| **404** | `BEST_001` | 베스트셀러 결과가 없습니다. |