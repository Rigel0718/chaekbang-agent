# 작가 기본 정보 조회

## 개요 

작가 기본 정보 조회 API는 상품 번호 또는 ISBN13으로 해당 상품의 작가 기본 정보를 조회합니다.

## Endpoint

```
GET
https://apis.yes24.com/v1/goods/author
```

## Query Parameters

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `searchType` | string | 필수 | ISBN13 | 검색 유형(ISBN13 또는 ItemId) |
| `query` | string | 필수 | - | ISBN13 값 또는 상품 번호(ItemId) |


## Request Example

```shell
curl -X GET "https://apis.yes24.com/v1/goods/author?searchType=ISBN13&query=9788966260959" -H "X-Api-Key: YOUR_API_KEY"
```

## Response Example

```json
{
  "success": true,
  "message": "성공",
  "errorCode": null,
  "data": {
    "meta": {
      "apiTitle": "작가 기본 정보 조회",
      "apiLink": "https://apis.yes24.com/v1/goods/author?searchType=ISBN13&query=9788966260959",
      "logoUrl": "https://image.yes24.com/sysimage/apis/openapi/images/logoN4.svg",
      "pubDate": "2026-07-14T09:16:14+09:00",
      "query": "?searchType=ISBN13&query=9788966260959",
      "version": "v1"
    },
    "data": {
      "authorId": 100001,
      "author": "로버트 C. 마틴",
      "authorType": "저자",
      "birthDate": "1952-12-05",
      "deathDate": "",
      "debutTitle": "Clean Code",
      "details": "소프트웨어 장인 정신과 클린 코드 분야의 대표 저자입니다.",
      "link": "https://www.yes24.com/product/author/100001"
    }
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
| `data.data.authorId` | integer | 작가 번호 |
| `data.data.author` | string | 작가명 |
| `data.data.authorType` | string | 작가 구분(저자, 역자 등) |
| `data.data.birthDate` | string | 생년월일 |
| `data.data.deathDate` | string | 사망일(없으면 빈 문자열) |
| `data.data.debutTitle` | string | 데뷔작 제목 |
| `data.data.details` | string | 작가 소개 |
| `data.data.link` | string | 작가 페이지 URL |


## 오류 코드

| HTTP | 오류 코드 | 설명 |
|------|-----------|------|
| **401** | `AUTH_001` | API Key 값이 없습니다. |
| **401** | `AUTH_002` | 유효하지 않은 API Key입니다. |
| **400** | `PARAM_004` | 유효하지 않은 query 입니다. |
| **404** | `AUTHOR_404` | 작가 정보가 없습니다. |
| **404** | `GOODS_002` | ISBN13에 해당하는 상품을 찾을 수 없습니다. |
| **404** | `SEARCH_002` | 검색 결과를 제공할 수 없습니다. |
| **503** | `UPSTREAM_UNAVAILABLE` | 외부 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요. |