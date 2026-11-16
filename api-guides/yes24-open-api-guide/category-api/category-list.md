# 카테고리 목록 조회

## 개요

카테고리 목록 조회 API는 예스24 분야별 카테고리 목록을 조회합니다. 카테고리 ID, 카테고리명, 전체 경로, 카테고리 URL을 제공합니다.

## Endpoint

```
GET
https://apis.yes24.com/v1/category/list
```

## Query Parameters

요청 Query Parameter가 없습니다.

## Request Example

```shell
curl -X GET "https://apis.yes24.com/v1/category/list" -H "X-Api-Key: YOUR_API_KEY"
```

## Response Example

```json
{
  "success": true,
  "message": "성공",
  "errorCode": null,
  "data": {
    "meta": {
      "apiTitle": "카테고리 목록 조회",
      "apiLink": "https://apis.yes24.com/v1/category/list",
      "logoUrl": "https://image.yes24.com/sysimage/apis/openapi/images/logoN4.svg",
      "pubDate": "2026-07-14T09:16:14+09:00",
      "query": "",
      "version": "v1"
    },
    "data": [
      {
        "categoryId": "001",
        "categoryName": "국내도서",
        "categoryFullPath": "국내도서",
        "categoryUrl": "https://www.yes24.com/Product/Category/Display/001"
      }
    ]
  }
}
```

## Response Fields

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 요청 성공 여부 |
| `message` | string | 응답 메시지 |
| `errorCode` | string · nullable | 오류 코드(성공 시 null) |
| `data.meta.apiTitle` | string | 호출한 API 제목 |
| `data.meta.apiLink` | string | 요청 URL |
| `data.meta.logoUrl` | string | 예스24 로고 URL |
| `data.meta.pubDate` | string | 응답 일시(ISO 8601) |
| `data.meta.query` | string | 요청 QueryString |
| `data.meta.version` | string | API 버전 |
| `data.data` | Category[] | 카테고리 목록 |
| `data.data[].categoryId` | string | 카테고리 ID |
| `data.data[].categoryName` | string | 카테고리 이름 |
| `data.data[].categoryFullPath` | string | 카테고리 전체 경로 |
| `data.data[].categoryUrl` | string | 카테고리 페이지 URL |

## 오류 코드

| HTTP | 오류 코드 | 설명 |
|------|-----------|------|
| **401** | `AUTH_001` | API Key 값이 없습니다. |
| **401** | `AUTH_002` | 유효하지 않은 API Key입니다. |
| **404** | `CATEGORY_001` | 카테고리 목록 조회 결과가 없습니다. |

