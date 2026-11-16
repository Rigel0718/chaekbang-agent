# YES24 OPEN API

## 개요

예스24 Open API를 사용하여 카테고리와 상품 데이터를 애플리케이션에 통합하세요.

## 예스24 Open API란?

예스24 Open API는 외부 개발자가 예스24의 카테고리, 베스트셀러, 신상품, 상품 정보를 활용하여 서비스를 구축할 수 있도록 제공하는 공식 API입니다.

REST 방식으로 설계되었으며, JSON 형식으로 응답합니다. 발급받은 API Key를 요청 헤더에 포함하는 방식으로 인증합니다.

## 제공 API

| API | 설명 | Endpoint |
|-----|------|----------|
| Category API | 카테고리 목록, 베스트셀러, 신상품 조회 | `/v1/category` |
| Goods API | 상품 검색, 상품 상세, 목차, 작가 정보 조회 | `/v1/goods` |

## Base URL

모든 API 요청은 아래 Base URL을 사용합니다.

```
https://apis.yes24.com/v1
```

## Rate Limit

| 등급 | 일일 요청 | 초당 요청(버스트) |
|------|-----------|-------------------|
| 기본키 | 20,000회 | 10회 |

한도는 API Key 기준으로 적용되며, 일일 한도는 매일 자정에 초기화됩니다. 한도 초과 시 HTTP 429 Too Many Requests가 반환됩니다 


## 응답 형식

모든 응답은 `Content-Type: application/json`으로 반환됩니다.

```json
# 성공 응답
{
  "success": true,
  "message": "성공",
  "data": { ... },
  "errorCode": null
}
```

```json
# 오류 응답
{
  "success": false,
  "message": "API Key가 없거나 유효하지 않습니다.",
  "data": null,
  "errorCode": "AUTH_001"
}
```

## 페이징 정책

목록형 API는 `page`와 `pageSize` Query Parameter를 사용합니다.

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| page | 1 | 조회할 페이지 번호 |
| pageSize | 20 | 페이지당 결과 수, 최대 100 |



## Category API

| 기능 | Endpoint | 필수 파라미터 | 선택 파라미터 | 결과 위치 | 상세 문서 |
|------|----------|---------------|---------------|-----------|-----------|
| 카테고리 목록 조회 | `GET /v1/category/list` | 없음 | 없음 | `data.data[]` | [category-list.md](category-api/category-list.md) |
| 종합 베스트셀러 조회 | `GET /v1/category/bestseller` | `categoryId` | `sex`, `age`, `page`, `pageSize`, `detail` | `data.items[]` | [bestseller.md](category-api/bestseller.md) |
| 월별 베스트셀러 조회 | `GET /v1/category/bestsellerMonthly` | `categoryId` | `date`, `sex`, `age`, `page`, `pageSize`, `detail` | `data.items[]` | [bestseller-monthly.md](category-api/bestseller-monthly.md) |
| 스테디셀러 조회 | `GET /v1/category/bestsellerSteady` | `categoryId` | `page`, `pageSize`, `detail` | `data.items[]` | [bestseller-steady.md](category-api/bestseller-steady.md) |

개요에 나온 신상품 조회는 아직 상세 문서가 없습니다.

## Goods API

| 기능 | Endpoint | 필수 파라미터 | 선택 파라미터 | 결과 위치 | 상세 문서 |
|------|----------|---------------|---------------|-----------|-----------|
| 상품 검색 | `GET /v1/goods/itemList` | `query` | `category`, `sort`, `page`, `pageSize`, `detail` | `data.items[]` | [item-list.md](goods-api/item-list.md) |
| 상품 상세 조회 | `GET /v1/goods/itemDetail` | `searchType`(기본값 ISBN13), `query` | `detail` | `data.items[]` | [item-detail.md](goods-api/item-detail.md) |
| 작가 기본 정보 조회 | `GET /v1/goods/author` | `searchType`(기본값 ISBN13), `query` | 없음 | `data.data` | [author.md](goods-api/author.md) |

개요에 나온 목차 조회는 아직 상세 문서가 없습니다. 목차 내용은 `data.items[].contentDetail.tableOfContents`로도 받을 수 있습니다.

