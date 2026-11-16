---
title: 도서관 정보나루 Open API 매뉴얼 (에이전트용 Markdown)
source: 정보나루 Open API 매뉴얼 PDF, 버전 v20260620 (70쪽)
base_url: http://data4library.kr/api/
apis: 19
---

# 도서관 정보나루 Open API (에이전트용)

이 문서는 정보나루 Open API 매뉴얼 PDF(v20260620)를 에이전트가 읽기 쉽게 옮긴 것입니다.

- **원문 내용은 빠짐없이 옮겼습니다.** 파라미터, 응답 필드, 규칙, 코드표를 모두 담았습니다.
- **옮기면서 바꾼 점**
  - API마다 반복되는 공통 파라미터와 규칙은 [0. 공통 규칙](#0-공통-규칙)으로 모았습니다.
  - 원문의 '결과화면' 스크린샷은 XML 예시로 옮겨 적었습니다.
- **표기 구분**: 원문에 없는 내용은 `> 📝 변환 주석` 블록에만 적었습니다.

## 목차

- [API 한눈에 보기](#api-한눈에-보기)
- [0. 공통 규칙](#0-공통-규칙)
- [1. 정보공개 도서관 조회](#1-정보공개-도서관-조회-libsrch) · [2. 도서관별 장서/대출 데이터 조회](#2-도서관별-장서대출-데이터-조회-itemsrch) · [3. 인기대출도서 조회](#3-인기대출도서-조회-loanitemsrch) · [4. 마니아를 위한 추천도서 조회](#4-마니아를-위한-추천도서-조회-recommandlist-typemania) · [5. 다독자를 위한 추천도서 조회](#5-다독자를-위한-추천도서-조회-recommandlist-typereader)
- [6. 도서 상세 조회](#6-도서-상세-조회-srchdtllist) · [7. 도서 키워드 목록](#7-도서-키워드-목록-keywordlist) · [8. 도서별 이용 분석](#8-도서별-이용-분석-usageanalysislist) · [9. 도서관/지역별 인기대출 도서 조회](#9-도서관지역별-인기대출-도서-조회-loanitemsrchbylib) · [10. 도서관별 대출반납추이](#10-도서관별-대출반납추이-usagetrend)
- [11. 도서관별 도서 소장여부 및 대출 가능여부 조회](#11-도서관별-도서-소장여부-및-대출-가능여부-조회-bookexist) · [12. 대출 급상승 도서](#12-대출-급상승-도서-hottrend) · [13. 도서 소장 도서관 조회](#13-도서-소장-도서관-조회-libsrchbybook) · [14. 도서관별 통합정보](#14-도서관별-통합정보-extendslibsrch) · [15. 도서관별 인기대출도서 통합](#15-도서관별-인기대출도서-통합-extendsloanitemsrchbylib)
- [16. 도서 검색](#16-도서-검색-srchbooks) · [17. 이달의 키워드](#17-이달의-키워드-monthlykeywords) · [18. 지역별 독서량/독서율](#18-지역별-독서량독서율-readqt) · [19. 신착도서 조회](#19-신착도서-조회-newarrivalbook)
- [20. 코드](#20-코드)
- [부록. 변환 주석 모음 (원문 불일치·예시 관찰)](#부록-변환-주석-모음)

---

## API 한눈에 보기

모든 엔드포인트는 `http://data4library.kr/api/` 아래에 있습니다. 모든 API에 `authKey`가 필수이고, `format`은 선택입니다(기본 xml).

| # | 이름 | 엔드포인트 | 필수 파라미터 (authKey 제외) | 기본 pageSize | 최대 결과 |
|---|---|---|---|---|---|
| 1 | 정보공개 도서관 조회 | `libSrch` | 없음 | 10 | – |
| 2 | 도서관별 장서/대출 데이터 조회 | `itemSrch` | `libCode` + (`type=ALL` 또는 `startDt`·`endDt`) | 100 | – |
| 3 | 인기대출도서 조회 (전국) | `loanItemSrch` | 없음 | 200 | 5,000건 |
| 4 | 마니아를 위한 추천도서 | `recommandList` | `isbn13` | – | 200건 |
| 5 | 다독자를 위한 추천도서 | `recommandList` | `isbn13`, `type=reader` | – | 200건 |
| 6 | 도서 상세 조회 | `srchDtlList` | `isbn13` | – | – |
| 7 | 도서 키워드 목록 | `keywordList` | `isbn13` | – | 키워드 50건 |
| 8 | 도서별 이용 분석 | `usageAnalysisList` | `isbn13` | – | 항목별 상이 |
| 9 | 도서관/지역별 인기대출 도서 | `loanItemSrchByLib` | `libCode`·`region`·`dtl_region` 중 하나 | 200 | 200건 |
| 10 | 도서관별 대출반납추이 | `usageTrend` | `libCode`, `type`(D/H) | – | – |
| 11 | 도서 소장여부·대출 가능여부 | `bookExist` | `libCode`, `isbn13` | – | – |
| 12 | 대출 급상승 도서 | `hotTrend` | `searchDt` | – | 일자별 5위 × 3일 |
| 13 | 도서 소장 도서관 조회 | `libSrchByBook` | `isbn`, `region` | (원문 미기재) | – |
| 14 | 도서관별 통합정보 | `extends/libSrch` | 없음 | 10 | 신착 10권 |
| 15 | 도서관별 인기대출도서 통합 | `extends/loanItemSrchByLib` | `libCode` | – | 그룹별 20권 |
| 16 | 도서 검색 | `srchBooks` | 없음 | 20 | – |
| 17 | 이달의 키워드 | `monthlyKeywords` | 없음 | – | 100건 |
| 18 | 지역별 독서량/독서율 | `readQt` | 없음 | – | – |
| 19 | 신착도서 조회 | `newArrivalBook` | `libCode` | (원문 미기재) | – |

### 목적별 API 고르기

> 📝 변환 주석: 아래 안내는 원문 각 API의 '주요기능' 설명을 목적별로 묶은 것입니다.

- **도서관 찾기·정보**: 1 `libSrch`, 14 `extends/libSrch`(대출반납추이·신착도서 포함), 13 `libSrchByBook`(특정 책을 소장한 도서관)
- **책 찾기·상세**: 16 `srchBooks`(검색), 6 `srchDtlList`(상세·대출통계), 7 `keywordList`(키워드), 8 `usageAnalysisList`(종합 분석)
- **추천**: 4 마니아 추천, 5 다독자 추천, 8의 `coLoanBooks`·`maniaRecBooks`·`readerRecBooks`
- **인기·트렌드**: 3 전국 인기대출, 9 도서관/지역별 인기대출, 15 도서관별 이용자 그룹별 인기대출, 12 대출 급상승, 17 이달의 키워드, 18 지역 독서량
- **특정 도서관 데이터**: 2 장서/대출, 10 대출반납추이, 11 소장·대출 가능 여부, 19 신착도서

---

## 0. 공통 규칙

### 0.1 호출 방식

- 호출 URL은 `http://data4library.kr/api/{엔드포인트}?{파라미터}` 형식입니다.
  - 원문 표현으로는 '오픈 API 프로토콜 입력 규칙에 따라 베이스 URL, 타겟 DB, 질문식, 검색항목 등을 조합하여' 호출합니다.
- 응답은 기본이 XML입니다. `format=json`을 주면 JSON으로 받습니다.
- 원문 URL 예시에서 **푸른색은 필수입력 항목**이었습니다. 이 문서에서는 각 파라미터 표의 '필수여부' 칸으로 표시했습니다.

### 0.2 공통 파라미터

아래 파라미터는 해당 API의 파라미터 표에서 생략하고 이름만 적었습니다.

| 파라미터 | 설명 | 필수여부 | 입력형태 | 기본값/규칙 | 사용하는 API |
|---|---|---|---|---|---|
| `authKey` | 인증키 (발급받은 키) | **필수** | 문자열 | – | 전체 1~19 |
| `format` | 응답유형 `[xml: xml 타입, json: json 타입]` | 선택 | 문자열 | 없으면 xml 타입으로 제공 | 전체 1~19 |
| `pageNo` | 페이지번호. 응답결과가 제공되는 페이지 번호 지정 | 선택 | 숫자 | 없으면 첫 번째 페이지 출력 | 1, 2, 3, 9, 13, 14, 16 |
| `pageSize` | 페이지크기. 한 페이지당 제공되는 목록 개수 지정 | 선택 | 숫자 | **기본값은 API마다 다름**(위 요약표·각 API 참조) | 1, 2, 3, 9, 13, 14, 16 |

**페이지 계산 예** (원문 3·9·16번에 있는 예):
- `pageSize=300` 입력 시, 1페이지에 300건의 검색결과 제공
- `pageNo=2&pageSize=300` 입력 시, 2페이지에 해당하는 301번~600번의 도서 목록 제공

### 0.3 필수여부 표기

| 표기 | 의미 |
|---|---|
| 필수 | 반드시 입력 |
| 선택 | 생략 가능 |
| 선택필수 | 같은 그룹 중 하나 이상은 반드시 입력. 어떤 그룹인지는 각 API 규칙에 적혀 있음 |

### 0.4 값 입력 공통 규칙

- **다중선택**: '(다중선택가능)'으로 표시된 항목은 `;`(세미콜론)으로 구분해 여러 값을 넣을 수 있습니다.
  - 예: 서울, 부산, 대구를 다중선택할 경우 `region=11;21;22`
- **ISBN**: 여러 API가 `isbn13`에 10자리 또는 13자리 ISBN을 섞어 쓰는 것을 허용합니다. 허용 여부는 API별로 따로 적었습니다.
- **날짜 형식**: `yyyy-mm-dd`(예: 2022-01-01), `yyyy-mm`(예: 2022-06), `yyyy`, `mm`. 형식은 API별 표를 따릅니다.
- **코드값**: 성별, 연령, 지역, 세부지역, KDC 주제, ISBN 부가기호 코드는 [20. 코드](#20-코드)를 참조합니다.

### 0.5 대출 조건 필터 공통 규칙 (3번 `loanItemSrch`, 9번 `loanItemSrchByLib`)

두 API는 같은 필터 파라미터를 씁니다: `startDt`, `endDt`, `gender`, `from_age`, `to_age`, `age`, `region`, `dtl_region`, `addCode`, `kdc`, `dtl_kdc`, `book_dvsn`.

- 선택조건이 없으면 성별, 연령, 지역, ISBN 부가기호, KDC 주제분류 전체 대출데이터를 기준으로 조회합니다.
- **기간**
  - `startDt`만 있으면 `endDt`는 조회일 하루 전 날짜로 자동 설정됩니다.
  - `endDt`만 있으면 `startDt`는 2014년 1월 1일로 자동 설정됩니다.
  - (9번 원문) 최소 3개월 이상의 대출기간을 검색조건으로 입력해야 양질의 데이터를 받을 수 있습니다.
- **성별**: `gender`가 없으면 모든 성별을 대상으로 설정합니다.
- **연령**
  - `from_age`, `to_age`, `age`가 모두 없으면 모든 연령을 대상으로 설정합니다.
  - 연령 조건은 시작·종료연령(`from_age`, `to_age`) 또는 연령(`age`) 둘 중 하나로 설정합니다.
    - 예: 21세부터 25세까지 → `from_age=21&to_age=25`
    - 예: 20대 → `age=20`
  - `from_age`만 있으면 `to_age`는 100세로 자동 설정됩니다.
  - `to_age`만 있으면 `from_age`는 0세로 자동 설정됩니다.
- **지역**: `region`이 없으면 모든 지역을 대상으로 설정합니다.
- **다중선택**: `;`로 구분합니다.
  - 예(3번 원문): 서울, 부산, 대구 → `region=11;21;22`
  - 예(9번 원문): 유아, 초등 → `age=6;8`
- **세부지역·세부주제 제약** (3번 원문에 명시)
  - `dtl_region`을 입력하면 `region`은 다중선택할 수 없습니다.
    - 예: 부산의 중구, 서구 → `region=21&dtl_region=21010;21020`
  - `dtl_kdc`를 입력하면 `kdc`는 다중선택할 수 없습니다.
    - 예: 문학의 한국문학, 중국문학 → `kdc=8&dtl_kdc=81;82`

### 0.6 응답 공통 사항

- **페이징 필드**: 목록형 응답에는 `pageNo`(페이지 번호), `pageSize`(페이지 크기), `numFound`(전체 검색결과 건수), `resultNum`(응답결과 건수)이 함께 오는 경우가 많습니다. 정확한 구성은 API별 응답 트리를 따릅니다.
- **`request` 블록**: 예시 응답에는 `<response>` 바로 아래에 요청 파라미터를 되돌려 주는 `<request>` 블록이 있습니다(원문 명세 표에는 없음).
- **책표지 이미지 이용 제한**:

> ⚠️ **bookImageURL 이용 제한 (원문, `bookImageURL`이 있는 모든 API에 적용)**
> bookImageURL은 비영리 서비스의 화면 표시에 한하여 이용 가능하며, 영리적 목적의 이용과 복사저장재배포 및 AI 입력학습 등 그 밖의 활용을 금함.

> 📝 변환 주석 (응답 다루기)
> - XML 예시에서 문자열 값 대부분은 `<![CDATA[ 값 ]]>` 형태이고, **값 앞뒤에 공백이 들어 있습니다**(예: `<![CDATA[ 2.28도서관 ]]>`). 파싱 후 trim하는 것이 안전합니다. 이 문서의 예시에서는 읽기 쉽게 CDATA를 벗겨 적었습니다.
> - 값이 없는 필드는 `<vol/>`처럼 빈 요소로 옵니다.
> - 원문에는 JSON 응답 예시가 없습니다. JSON의 키 구조, 특히 반복 요소가 배열로 오는 방식은 실제 호출로 확인해야 합니다.

### 0.7 응답 트리 표기법 (이 문서 전용)

원문은 응답 계층을 들여쓰기로만 표현했습니다. 이 문서는 다음처럼 적습니다.

```
필드명            설명
  하위필드        설명        ← 2칸 들여쓰기 = 한 단계 아래
  doc[]           도서        ← [] = 여러 번 반복되는 요소
```

> 📝 `[]` 표시는 원문에 없습니다. 예시 응답과 필드 의미('목록'의 원소)를 보고 붙였습니다.

---

## 1. 정보공개 도서관 조회 (`libSrch`)

**주요기능**
- 빅데이터 분석 플랫폼을 통해 데이터를 공개하는 도서관 정보를 제공합니다.
- 도서관 목록과 각 도서관의 주소, 연락처, 홈페이지, 운영시간, 휴관일 정보 등을 조회할 수 있습니다.
- 선택조건을 통해 조회할 데이터의 규모를 설정할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/libSrch`

**호출 예**
```
http://data4library.kr/api/libSrch?authKey=[발급받은키]&pageNo=1&pageSize=10
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관 코드 | 선택 | 숫자(코드) |
| `region` | 지역 | 선택 | 숫자(코드) |
| `dtl_region` | 세부지역 | 선택 | 숫자(코드) |

**규칙**
- 특정 도서관 정보를 조회할 경우 도서관 코드(`libCode`) 입력
- 지역(`region`) 또는 세부지역(`dtl_region`)이 없을 경우 모든 지역을 대상으로 제공
- `pageSize` 기본값: 페이지당 **10개** 도서관 목록 제공

**응답 트리**
```
pageNo                페이지 번호
pageSize              페이지 크기
numFound              전체 검색결과 건수
resultNum             응답결과 건수
libs                  목록
  lib[]               도서관
    libCode           도서관코드
    libName           도서관명
    address           주소
    tel               전화번호
    fax               FAX 번호
    latitude          위도
    longitude         경도
    homepage          홈페이지 URL
    closed            휴관일
    operatingTime     운영시간
    BookCount         단행본수
```
- 단행본수(`BookCount`)는 도서관이 소장한 도서의 권수입니다.

**응답 예시** (원문 결과화면 판독)
```xml
<response>
  <request><pageNo>1</pageNo><pageSize>10</pageSize></request>
  <pageNo>1</pageNo>
  <pageSize>10</pageSize>
  <numFound>1309</numFound>
  <resultNum>10</resultNum>
  <libs>
    <lib>
      <libCode>127058</libCode>
      <libName>2.28도서관</libName>
      <address>대구광역시 중구 2·28길 9</address>
      <tel>053-257-2280</tel>
      <fax>053-257-2284</fax>
      <latitude>35.8592504</latitude>
      <longitude>128.5894055</longitude>
      <homepage>http://library.daegu.go.kr/228lib/index.do</homepage>
      <closed>매주 월요일 / 법정공휴일(일요일을 제외한 관공서 공휴일), 도서관 및 기타 사정으로 …(스크린샷에서 잘림)</closed>
      <operatingTime>화~금 09:00~18:00, 토일 09:00~17:00</operatingTime>
      <BookCount>51941</BookCount>
    </lib>
    <!-- lib 반복 -->
  </libs>
</response>
```

---

## 2. 도서관별 장서/대출 데이터 조회 (`itemSrch`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 도서관의 장서 및 대출정보를 제공합니다.
- 특정 도서관의 장서정보와 대출정보를 조회할 수 있습니다. 제공 정보는 도서명, 저자명, 출판사, 출판년도, ISBN, KDC 주제분류, 청구기호, 등록일 등입니다.
- 선택조건을 통해 조회할 데이터의 규모를 설정할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/itemSrch`

**호출 예**
```
http://data4library.kr/api/itemSrch?authKey=[발급받은키]&libCode=[도서관코드]&type=ALL&pageNo=1&pageSize=10
http://data4library.kr/api/itemSrch?authKey=[발급받은키]&libCode=[도서관코드]&startDt=[검색시작일자]&endDt=[검색종료일자]&pageNo=1&pageSize=10
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `type` | 검색조건 `[ALL: 전체 데이터]` | 선택필수 | 문자열 |
| `libCode` | 도서관코드 | **필수** | 숫자(코드) |
| `isbn13` | 13자리 ISBN | 선택 | 숫자 |
| `startDt` | 검색시작일자(도서 등록일) | 선택필수 | yyyy-mm-dd |
| `endDt` | 검색종료일자(도서 등록일) | 선택필수 | yyyy-mm-dd |
| `kdc` | 대주제(다중선택가능) | 선택 | 숫자(코드) |
| `dtl_kdc` | 세부주제(다중선택가능) | 선택 | 숫자(코드) |

**규칙**
- 검색조건(`type`) 또는 검색시작/종료일자(`startDt`, `endDt`) 둘 중 하나는 필수 입력
- `type`이 없는 경우 `startDt`와 `endDt` 모두 필요
  - `type`이 ALL이면서 검색시작/종료일자를 함께 요청하면 `type`을 우선 조회
- `isbn13`은 `;`로 구분하여 최대 5개까지 입력 가능
- 대주제(`kdc`)와 세부주제(`dtl_kdc`)는 둘 중 하나만 입력 권장. OR 검색 불가
- 다중선택이 가능한 항목은 `;`로 구분하여 입력 가능
- `pageSize` 기본값: 페이지당 **100개** 장서/대출 데이터 제공

**응답 트리**
```
libNm                       도서관명
pageNo                      페이지 번호
pageSize                    페이지 크기
numFound                    전체 검색결과 건수
resultNum                   응답결과 건수
docs                        목록
  doc[]                     도서
    bookname                도서명
    authors                 저자명
    publisher               출판사
    publication_year        출판년도
    isbn13                  13자리 ISBN
    set_isbn13              13자리 세트 ISBN
    bookImageURL            책표지 URL
    addition_symbol         ISBN 부가기호
    vol                     권
    class_no                주제분류
    class_nm                주제분류명
    callNumbers             도서별 청구기호
      callNumber[]          도서 청구기호
        separate_shelf_code   별치기호
        separate_shelf_name   별치기호명
        book_code             도서기호
        shelf_loc_code        배가기호
        shelf_loc_name        배가기호명
        copy_code             복본기호
    reg_date                등록일자
```
- `bookImageURL` 이용 제한 적용 ([0.6](#06-응답-공통-사항))

**응답 예시**
```xml
<response>
  <request><libCode>141321</libCode><type>all</type><pageNo>1</pageNo></request>
  <libNm>부천시립상동도서관</libNm>
  <pageNo>1</pageNo>
  <pageSize>100</pageSize>
  <numFound>181080</numFound>
  <resultNum>100</resultNum>
  <docs>
    <doc>
      <bookname>중학생 일기</bookname>
      <authors>박문정 지음;강정희 지도감수;서영희 지도감수</authors>
      <publisher>부크크(bookk)</publisher>
      <publication_year>2022</publication_year>
      <isbn13>9791137270053</isbn13>
      <set_isbn13/>
      <bookImageURL>https://image.aladin.co.kr/product/28787/2/cover/k632836581_1.jp…(잘림)</bookImageURL>
      <addition_symbol>0</addition_symbol>
      <vol/>
      <class_no>818</class_no>
      <class_nm>문학 > 한국문학 > 르포르타주 및 기타</class_nm>
      <callNumbers>
        <callNumber>
          <separate_shelf_code/>
          <separate_shelf_name/>
          <book_code>박36ㅈ</book_code>
          <shelf_loc_code>AAJ</shelf_loc_code>
          <shelf_loc_name>[상동도서관]부천작가(1층)</shelf_loc_name>
          <copy_code/>
        </callNumber>
      </callNumbers>
      <reg_date>2022-05-07</reg_date>
    </doc>
  </docs>
</response>
```

---

## 3. 인기대출도서 조회 (`loanItemSrch`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 대출정보를 기반으로 분석한 인기대출도서 정보를 제공합니다.
- 전국 공공도서관 인기대출도서를 다양한 조건으로 조회할 수 있습니다. 제공 정보는 대출순위, 도서명, 저자명, 출판사, 출판년도, ISBN, KDC, 대출횟수 등입니다.
- 인기대출도서는 ISBN을 기준으로 집계되며, 최대 5,000건의 도서 목록을 제공합니다.
- 선택조건을 통해 대출기간, 성별, 연령별, 지역별, ISBN 부가기호별, KDC 주제분류별 데이터를 조회할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/loanItemSrch`

**호출 예**
```
http://data4library.kr/api/loanItemSrch?authKey=[발급받은키]&startDt=2022-01-01&endDt=2022-03-31&gender=1&age=20&region=11;31&addCode=0&kdc=6&pageNo=1&pageSize=10
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `startDt` | 검색시작일자(대출기간) | 선택 | yyyy-mm-dd |
| `endDt` | 검색종료일자(대출기간) | 선택 | yyyy-mm-dd |
| `gender` | 성별(다중선택가능) | 선택 | 숫자(코드) |
| `from_age` | 시작연령 | 선택 | 숫자 |
| `to_age` | 종료연령 | 선택 | 숫자 |
| `age` | 연령(다중선택가능) | 선택 | 숫자(코드) |
| `region` | 지역(다중선택가능) | 선택 | 숫자(코드) |
| `dtl_region` | 세부지역(다중선택가능) | 선택 | 숫자(코드) |
| `book_dvsn` | 도서구분 `[big: 큰글씨도서, oversea: 국외도서]` | 선택 | 문자열 |
| `addCode` | ISBN 부가기호(다중선택가능) | 선택 | 숫자(코드) |
| `kdc` | 대주제(다중선택가능) | 선택 | 숫자(코드) |
| `dtl_kdc` | 세부주제(다중선택가능) | 선택 | 숫자(코드) |

**규칙**
- 필터 규칙 전체는 [0.5 대출 조건 필터 공통 규칙](#05-대출-조건-필터-공통-규칙-3번-loanitemsrch-9번-loanitemsrchbylib)을 따릅니다. 기간 자동설정, 연령 지정 방식, `dtl_region`/`dtl_kdc` 제약이 모두 여기에 해당합니다.
- `pageSize` 기본값: 페이지당 **200개** 도서 목록 제공

**응답 트리**
```
resultNum               응답결과 건수
numFound                전체 검색결과 건수
docs                    목록
  doc[]                 도서
    no                  순번
    ranking             순위
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
    bookDtlUrl          도서 상세 페이지 URL
    loan_count          대출건수
```
- 인기대출도서는 최대 5,000건의 도서 목록을 제공
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <request><pageNo>1</pageNo><pageSize>200</pageSize></request>
  <resultNum>200</resultNum>
  <docs>
    <doc>
      <no>1</no>
      <ranking>1</ranking>
      <bookname>나미야 잡화점의 기적 :히가시노 게이고 장편소설</bookname>
      <authors>지은이: 히가시노 게이고 ;옮긴이: 양윤옥</authors>
      <publisher>현대문학</publisher>
      <publication_year>2012</publication_year>
      <isbn13>9788972756194</isbn13>
      <addition_symbol>03830</addition_symbol>
      <vol/>
      <class_no>833.6</class_no>
      <class_nm>문학 > 일본문학 > 소설</class_nm>
      <loan_count>296468</loan_count>
      <bookImageURL>http://image.aladin.co.kr/product/15848/6/cover/k622533431_1.jpg</bookImageURL>
    </doc>
  </docs>
</response>
```

---

## 4. 마니아를 위한 추천도서 조회 (`recommandList`, type=mania)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 최근 36개월의 대출정보를 기반으로, 조건부 확률로 분석한 마니아를 위한 추천도서 정보를 제공합니다.
- 특정 도서와 함께 읽을 확률이 높은 도서 목록을 조회할 수 있습니다. 복수의 ISBN을 입력할 수 있으며, 추천도서는 최대 200건까지 제공합니다.

**엔드포인트**: `http://data4library.kr/api/recommandList`

> 📝 엔드포인트 철자는 원문 그대로 `recommandList`입니다(recommend가 아님).

**호출 예**
```
http://data4library.kr/api/recommandList?authKey=[발급받은키]&isbn13=[ISBN]
http://data4library.kr/api/recommandList?authKey=[발급받은키]&isbn13=9788983922571;9788983921475;9788983921994
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn13` | 10자리 또는 13자리 ISBN | **필수** | 숫자 |
| `type` | 추천유형 `[mania: 마니아를 위한 추천도서]` | 선택 | 문자열 |

**규칙**
- `isbn13`은 10자리 또는 13자리 ISBN 혼용 가능
- `isbn13`은 `;`로 구분하여 최대 5개까지 조회 가능. 5개 이상 입력 시 순차적으로 5개의 ISBN만 대상으로 조회

**응답 트리**
```
resultNum               응답결과 건수
docs                    목록
  book[]                도서
    no                  순번
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
```
- 마니아를 위한 추천도서는 최대 200건의 도서 목록을 제공
- `bookImageURL` 이용 제한 적용

> 📝 이 API는 `docs` 아래 원소 이름이 `doc`이 아니라 **`book`** 입니다(원문 명세·예시 모두).

**응답 예시**
```xml
<response>
  <request><isbn13>9788936434267</isbn13></request>
  <resultNum>200</resultNum>
  <docs>
    <book>
      <no>1</no>
      <bookname>서른의 반격 :손원평 장편소설</bookname>
      <authors>지은이: 손원평</authors>
      <publisher>은행나무</publisher>
      <publication_year>2017</publication_year>
      <isbn13>9791196199807</isbn13>
      <addition_symbol/>
      <vol/>
      <class_no>813.7</class_no>
      <class_nm>문학 > 한국문학 > 소설</class_nm>
      <bookImageURL>https://image.aladin.co.kr/product/11987/76/cover/k672531630_1.jpg</bookImageURL>
    </book>
  </docs>
</response>
```

---

## 5. 다독자를 위한 추천도서 조회 (`recommandList`, type=reader)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 최근 36개월간의 대출정보를 기반으로, 조건부 확률을 지수화하여 분석한 다독자를 위한 추천도서 정보를 제공합니다.
- 특정 도서와 함께 두루 읽힌 도서 목록을 조회할 수 있습니다. 복수의 ISBN을 입력할 수 있으며, 추천도서는 최대 200건까지 제공합니다.

**엔드포인트**: `http://data4library.kr/api/recommandList` (4번과 같고 `type=reader`로 구분)

**호출 예**
```
http://data4library.kr/api/recommandList?authKey=[발급받은키]&type=reader&isbn13=[ISBN]
http://data4library.kr/api/recommandList?authKey=[발급받은키]&type=reader&isbn13=9788983922571;9788983921475;9788983921994
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn13` | 10자리 또는 13자리 ISBN | **필수** | 숫자 |
| `type` | 추천유형 `[reader: 다독자를 위한 추천도서]` | **필수** | 문자열 |

**규칙**
- `isbn13`은 10자리 또는 13자리 ISBN 혼용 가능
- `isbn13`은 `;`로 구분하여 최대 5개까지 조회 가능. 5개 이상 입력 시 순차적으로 5개의 ISBN만 대상으로 조회

**응답 트리** (4번과 같은 구조)
```
resultNum               응답결과 건수
docs                    목록
  book[]                도서
    no                  순번
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
```
- 다독자를 위한 추천도서는 최대 200건의 도서 목록을 제공
- `bookImageURL` 이용 제한 적용

**응답 예시** (4번과 같은 ISBN으로 type=reader 조회)
```xml
<response>
  <request><isbn13>9788936434267</isbn13></request>
  <resultNum>199</resultNum>
  <docs>
    <book>
      <no>1</no>
      <bookname>달러구트 꿈 백화점.이미예 장편소설</bookname>
      <authors>지은이: 이미예</authors>
      <publisher>팩토리나인</publisher>
      <publication_year>2020</publication_year>
      <isbn13>9791165341909</isbn13>
      <addition_symbol/>
      <vol>1-2 :</vol>
      <class_no>813.7</class_no>
      <class_nm>문학 > 한국문학 > 소설</class_nm>
      <bookImageURL>https://image.aladin.co.kr/product/24512/70/cover/k392630952_1.jpg</bookImageURL>
    </book>
  </docs>
</response>
```

---

## 6. 도서 상세 조회 (`srchDtlList`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 도서관의 장서 및 대출정보를 기반으로 분석한 도서의 상세정보를 제공합니다.
- 특정 도서의 상세한 서지정보와 대출정보를 조회할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/srchDtlList`

**호출 예**
```
http://data4library.kr/api/srchDtlList?authKey=[발급받은키]&isbn13=[ISBN]&loaninfoYN=Y&displayInfo=age
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn13` | 13자리 ISBN | **필수** | 숫자 |
| `loaninfoYN` | 대출상세정보 제공여부 `[Y: 제공, N: 미제공]` | 선택 | 문자열 |
| `displayInfo` | 대출정보 조회대상 `[gender: 성별, age: 연령별, region: 지역별]` | 선택 | 문자열 |

**규칙**
- `isbn13`은 10자리 또는 13자리 ISBN 혼용 가능
- `isbn13`만 있는 경우 도서명, 저자명, 출판사, 출판년, 권, KDC 주제분류, 책소개, 책표지 URL 정보만 제공
- `loaninfoYN`이 없는 경우 N을 기본값으로 설정
- `displayInfo`는 `loaninfoYN`이 Y인 경우에만 적용
- `displayInfo`가 없으면 성별/연령별/지역별 대출정보를 모두 제공하고, 있으면 입력한 대출정보만 제공
  - 예: 성별/연령별/지역별 대출정보를 모두 원할 경우 `loaninfoYN=Y`
  - 예: 지역별 대출정보만 원할 경우 `loaninfoYN=Y&displayInfo=region`

> 📝 원문 예시에는 `IoaninfoYN=Y`(대문자 I)로 오기되어 있어 `loaninfoYN`으로 바로잡았습니다.

**응답 트리**
```
detail                  상세
  book                  도서
    no                  순번
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_date    출판일자
    publication_year    출판년도
    isbn                ISBN
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    description         책소개
    bookImageURL        책표지 URL
loanInfo                대출정보
  Total                 전체 대출정보
    ranking             순위
    name                명칭
    loanCnt             대출 건수
  regionResult          지역별 대출정보
    region[]            지역
      ranking           순위
      name              명칭
      loanCnt           대출건수
  ageResult             연령별 대출정보
    age[]               연령
      ranking           순위
      name              명칭
      loanCnt           대출건수
  genderResult          성별 대출정보
    gender[]            성별
      ranking           순위
      name              명칭
      loanCnt           대출건수
```
- 대출정보는 최근 90일을 기준으로 제공
- 대출정보는 각 조건별 상위 1,000위까지의 데이터를 제공
  - 예: 초등(여) 조건에서 상위 812위인 경우 제공
  - 예: 초등(남) 조건에서 상위 1,001위인 경우 미제공
- `bookImageURL` 이용 제한 적용

**응답 예시** (`loaninfoYN=Y&displayInfo=age`)
```xml
<response>
  <request><isbn13>9788936434267</isbn13><loaninfoYN>Y</loaninfoYN><displayInfo>age</displayInfo></request>
  <detail>
    <book>
      <no>1</no>
      <bookname>아몬드 :손원평 장편소설</bookname>
      <authors>지은이: 손원평</authors>
      <publisher>창비</publisher>
      <class_no>813.7</class_no>
      <class_nm>문학 > 한국문학 > 소설</class_nm>
      <publication_year>2017</publication_year>
      <publication_date>2017</publication_date>
      <bookImageURL>http://image.aladin.co.kr/product/16839/4/cover/k492534773_1.jpg</bookImageURL>
      <isbn>8936434268</isbn>
      <isbn13>9788936434267</isbn13>
      <description>제10회 창비청소년문학상을 수상하며 등단한 손원평 작가의 첫 장편소설 &lt;아몬드&gt;가 출간 1년 만에 20만부를 맞아 선물용 특별판 &lt;아몬드&gt;를 선보인다. …(이하 생략)</description>
    </book>
  </detail>
  <loanInfo>
    <Total><ranking>3</ranking><name>전체</name><loanCnt>7296</loanCnt></Total>
    <ageResult>
      <age><ranking>642</ranking><name>초등(8~13)</name><loanCnt>534</loanCnt></age>
      <age><ranking>3</ranking><name>청소년(14~19)</name><loanCnt>547</loanCnt></age>
      <age><ranking>5</ranking><name>20대</name><loanCnt>1186</loanCnt></age>
      <age><ranking>13</ranking><name>30대</name><loanCnt>1221</loanCnt></age>
      <age><ranking>7</ranking><name>40대</name><loanCnt>2508</loanCnt></age>
      <age><ranking>19</ranking><name>50대</name><loanCnt>618</loanCnt></age>
      <age><ranking>193</ranking><name>60대 이상</name><loanCnt>154</loanCnt></age>
    </ageResult>
  </loanInfo>
</response>
```
> 📝 `description` 안의 `<`, `>`는 `&lt;`, `&gt;`로 이스케이프된 채 옵니다.

---

## 7. 도서 키워드 목록 (`keywordList`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 서지정보를 기반으로 분석한 핵심 키워드를 제공합니다.
- ISBN으로 특정 장서의 핵심 키워드 목록과 각 단어의 유의미한 가중치 정보를 조회할 수 있습니다. 도서별 최대 50건의 키워드를 제공합니다.

**엔드포인트**: `http://data4library.kr/api/keywordList`

**호출 예**
```
http://data4library.kr/api/keywordList?authKey=[발급받은키]&isbn13=[ISBN]&additionalYN=Y
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn13` | 13자리 ISBN | **필수** | 숫자 |
| `additionalYN` | 부가정보 적용여부 `[Y: 제공, N: 미제공]` | 선택 | 문자열 |

**규칙**
- `isbn13`은 10자리 또는 13자리 ISBN 혼용 가능
- `additionalYN`이 없는 경우 N을 기본값으로 설정
- `additionalYN`이 Y인 경우 서지정보(도서명, 저자명, 출판사, 출판년, 13자리 ISBN, 권)를 제공

**응답 트리**
```
resultNum               응답결과 건수
items                   항목
  item[]                기본항목
    word                단어
    weight              가중치
  additionalItem        도서정보   (additionalYN=Y일 때)
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    vol                 권
```
- 도서별 키워드는 최대 50건까지 제공

**응답 예시**
```xml
<response>
  <request><additionalYN>Y</additionalYN></request>
  <resultNum>50</resultNum>
  <items>
    <item><word>망원동브라더스</word><weight>12</weight></item>
    <item><word>편의점</word><weight>8</weight></item>
    <item><word>불편한편의점</word><weight>6</weight></item>
    <item><word>김호연</word><weight>6</weight></item>
    <!-- item 반복 -->
  </items>
  <additionalItem>
    <bookname>불편한 편의점 :김호연 장편소설</bookname>
    <authors>지은이: 김호연</authors>
    <publisher>나무옆의자</publisher>
    <isbn13>9791161571188</isbn13>
  </additionalItem>
</response>
```
> 📝 예시 화면에서는 `additionalItem`이 `items` 바깥(`</items>` 다음, `</response>` 앞)에 나옵니다. 원문 명세 표에서는 `item`과 같은 들여쓰기(`items` 아래)로 적혀 있습니다. 파싱할 때는 두 위치를 모두 고려하세요.

---

## 8. 도서별 이용 분석 (`usageAnalysisList`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 장서정보와 대출정보를 기반으로 도서의 이용정보를 분석하여 제공합니다.
- ISBN으로 도서의 서지정보, 대출정보, 핵심 키워드, 함께 대출된 도서를 조회할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/usageAnalysisList`

**호출 예**
```
http://data4library.kr/api/usageAnalysisList?authKey=[발급받은키]&isbn13=[ISBN]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn13` | 13자리 ISBN | **필수** | 숫자 |

**규칙**
- `isbn13`은 10자리 또는 13자리 ISBN 혼용 가능

**응답 트리**
```
book                    서지정보
  bookname              도서명
  authors               저자명
  publisher             출판사
  publication_year      출판년도
  isbn13                13자리 ISBN
  addition_symbol       ISBN 부가기호
  vol                   권
  class_no              주제분류
  class_nm              주제분류명
  description           책소개
  bookImageURL          책표지 URL
  loanCnt               대출건수
loanHistory             대출추이
  loan[]                대출정보
    month               대출년월
    loanCnt             대출건수
    ranking             순위
loanGrps                다대출 이용자 그룹
  loanGrp[]             이용자 그룹
    age                 연령
    gender              성별
    loanCnt             대출건수
    ranking             순위
keywords                키워드정보
  keyword[]             키워드
    word                단어
    weight              가중치
coLoanBooks             함께 대출된 도서
  book[]                도서정보
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    vol                 권
maniaRecBooks           마니아를 위한 추천도서
  book[]                도서정보
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    vol                 권
readerRecBooks          다독자를 위한 추천도서
  book[]                도서정보
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    vol                 권
```
- 대출정보(`loan`)는 최근 12개월간의 대출건수와 순위를 월별로 제공
- 다대출 이용자 그룹(`loanGrps`)은 최근 30일 동안 대출을 가장 많이 한 연령 및 성별 순으로 제공
  - 예: 40대(여) 그룹은 최근 30일 동안 <밝은 밤>을 603회 대출하여 첫 번째로 많이 대출했으며, 40대(여) 그룹에서 <밝은 밤>은 대출 10위 도서
- 키워드정보(`keywords`)는 최대 50건까지 제공
- 함께 대출된 도서(`coLoanBooks`)는 최근 36개월 동안의 동시대출빈도를 기준으로 최대 10권까지 제공
- 마니아를 위한 추천도서(`maniaRecBooks`)는 최근 36개월간의 대출정보를 기반으로 조건부 확률로 분석, 최대 10권까지 제공
- 다독자를 위한 추천도서(`readerRecBooks`)는 최근 36개월간의 대출정보를 기반으로 조건부 확률을 지수화하여 분석, 최대 10권까지 제공
- `recBooks`(추천도서)는 `maniaRecBooks`(마니아를 위한 추천도서)로 변경되어 2023년 3월 31일 이후 삭제
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <request><isbn13>9788954681179</isbn13></request>
  <book>
    <bookname>밝은 밤 :최은영 장편소설</bookname>
    <authors>지은이: 최은영</authors>
    <publisher>문학동네</publisher>
    <bookImageURL>https://image.aladin.co.kr/product/27541/91/cover/8954681174_1.jpg</bookImageURL>
    <description>백 년의 시간을 감싸안으며 이어지는 사랑과 숨의 기록 『쇼코의 미소』 『내게 무해한 사람』 최은영 첫 장편소설 …</description>
    <publication_year>2021</publication_year>
    <isbn13>9788954681179</isbn13>
    <vol/>
    <class_no>813.7</class_no>
    <class_nm>문학 > 한국문학 > 소설</class_nm>
    <loanCnt>17204</loanCnt>
  </book>
  <loanHistory/>  <!-- 스크린샷에서는 접혀 있음 -->
  <loanGrps>
    <loanGrp><age>40대</age><gender>여성</gender><loanCnt>603</loanCnt><ranking>10</ranking></loanGrp>
    <loanGrp><age>30대</age><gender>여성</gender><loanCnt>439</loanCnt><ranking>4</ranking></loanGrp>
    <loanGrp><age>20대</age><gender>여성</gender><loanCnt>258</loanCnt><ranking>14</ranking></loanGrp>
    <loanGrp><age>50대</age><gender>여성</gender><loanCnt>180</loanCnt><ranking>10</ranking></loanGrp>
    <loanGrp><age>40대</age><gender>남성</gender><loanCnt>74</loanCnt><ranking>704</ranking></loanGrp>
  </loanGrps>
  <keywords>
    <keyword><word>최은영</word><weight>7</weight></keyword>
    <keyword><word>쇼코의미소</word><weight>6</weight></keyword>
    <keyword><word>문학동네</word><weight>5</weight></keyword>
    <keyword><word>장편소설</word><weight>5</weight></keyword>
  </keywords>
  <coLoanBooks>
    <book>
      <bookname>시선으로부터,</bookname>
      <authors>정세랑 (지은이)</authors>
      <publisher>문학동네</publisher>
      <publication_year>2020</publication_year>
      <isbn13>9788954672214</isbn13>
      <vol/>
      <loanCnt>459</loanCnt>
    </book>
    <!-- book 반복 -->
  </coLoanBooks>
  <maniaRecBooks>
    <book>
      <bookname>작별하지 않는다 :한강 장편소설</bookname>
      <authors>지은이: 한강</authors>
      <publisher>문학동네</publisher>
      <publication_year>2021</publication_year>
      <isbn13>9788954682152</isbn13>
      <vol/>
    </book>
  </maniaRecBooks>
  <readerRecBooks>
    <book>
      <bookname>시선으로부터,</bookname>
      <authors>정세랑 (지은이)</authors>
      <publisher>문학동네</publisher>
      <publication_year>2020</publication_year>
      <isbn13>9788954672214</isbn13>
      <vol/>
    </book>
  </readerRecBooks>
</response>
```
> 📝 예시 관찰 내용
> - `loanGrp`의 `age`, `gender`는 코드가 아니라 **한글 명칭**(예: `40대`, `여성`)으로 옵니다.
> - `coLoanBooks > book`에는 명세 표에 없는 **`loanCnt`** 가 예시에 나옵니다.
> - 원문 스크린샷에는 삭제된 `recBooks` 블록도 보이지만, 위 규칙대로 지금은 쓰지 않으므로 이 예시에서는 뺐습니다.

---

## 9. 도서관/지역별 인기대출 도서 조회 (`loanItemSrchByLib`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 대출정보를 기반으로 도서관별 또는 지역별로 분석한 인기대출도서를 제공합니다.
- 도서관별 또는 지역별 인기대출도서를 다양한 조건으로 조회할 수 있습니다. 제공 정보는 대출순위, 도서명, 저자명, 출판사, 출판년도, ISBN, KDC, 대출횟수 등입니다.
- 도서관별/지역별 인기대출도서는 ISBN을 기준으로 집계되며, 최대 200건의 도서 목록을 제공합니다.
- 선택조건을 통해 대출기간, 성별, 연령별, 지역별, ISBN 부가기호별, KDC 주제분류별 데이터를 조회할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/loanItemSrchByLib`

**호출 예**
```
http://data4library.kr/api/loanItemSrchByLib?authKey=[발급받은키]&libCode=[도서관코드]&gender=1
http://data4library.kr/api/loanItemSrchByLib?authKey=[발급받은키]&region=[지역코드]&age=0
http://data4library.kr/api/loanItemSrchByLib?authKey=[발급받은키]&dtl_region=[세부지역코드]&kdc=8
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관 코드 | 선택필수 | 숫자(코드) |
| `region` | 지역 | 선택필수 | 숫자(코드) |
| `dtl_region` | 세부지역 | 선택필수 | 숫자(코드) |
| `startDt` | 검색시작일자(대출기간) | 선택 | yyyy-mm-dd |
| `endDt` | 검색종료일자(대출기간) | 선택 | yyyy-mm-dd |
| `gender` | 성별(다중선택가능) | 선택 | 숫자(코드) |
| `from_age` | 시작연령 | 선택 | 숫자 |
| `to_age` | 종료연령 | 선택 | 숫자 |
| `age` | 연령(다중선택가능) | 선택 | 숫자(코드) |
| `addCode` | ISBN 부가기호(다중선택가능) | 선택 | 숫자(코드) |
| `kdc` | 대주제(다중선택가능) | 선택 | 숫자(코드) |
| `dtl_kdc` | 세부주제(다중선택가능) | 선택 | 숫자(코드) |
| `book_dvsn` | 도서구분 `[big: 큰글씨도서, oversea: 국외도서]` | 선택 | 문자열 |

**규칙**
- 도서관 코드(`libCode`), 지역코드(`region`), 세부지역코드(`dtl_region`) 셋 중 하나는 필수 입력
- 그 밖의 필터는 [0.5 대출 조건 필터 공통 규칙](#05-대출-조건-필터-공통-규칙-3번-loanitemsrch-9번-loanitemsrchbylib)을 따름. "최소 3개월 이상의 대출기간 권장" 안내는 이 API의 원문에 있는 내용임
- `pageSize` 기본값: 페이지당 **200개** 도서 목록 제공

**응답 트리**
```
libNm                   도서관명      (도서관 기준으로 조회했을 경우)
regionNm                지역명        (지역 기준으로 조회했을 경우)
dtlregionNm             세부지역명    (세부지역 기준으로 조회했을 경우)
resultNum               응답결과 건수
docs                    목록
  doc[]                 도서
    no                  순번
    ranking             순위
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
    bookDtlUrl          도서 상세 페이지 URL
    loan_count          대출건수      (지역 또는 세부지역 기준으로 조회했을 경우)
```
- 도서관/지역별 인기대출도서는 최대 200건의 도서 목록을 제공
- 도서관별 인기대출도서는 대출순위만 제공(`loan_count` 없음)
- `bookImageURL` 이용 제한 적용

**응답 예시** (`region=11`)
```xml
<response>
  <request><region>11</region><pageNo>1</pageNo><pageSize>200</pageSize></request>
  <regionNm>서울특별시</regionNm>
  <resultNum>200</resultNum>
  <docs>
    <doc>
      <no>1</no>
      <ranking>1</ranking>
      <bookname>나미야 잡화점의 기적 :히가시노 게이고 장편소설</bookname>
      <authors>지은이: 히가시노 게이고 ;옮긴이: 양윤옥</authors>
      <publisher>현대문학</publisher>
      <publication_year>2012</publication_year>
      <isbn13>9788972756194</isbn13>
      <addition_symbol>03830</addition_symbol>
      <vol/>
      <class_no>833.6</class_no>
      <class_nm>문학 > 일본문학 > 소설</class_nm>
      <loan_count>66268</loan_count>
      <bookImageURL>http://image.aladin.co.kr/product/15848/6/cover/k622533431_1.jpg</bookImageURL>
    </doc>
  </docs>
</response>
```

---

## 10. 도서관별 대출반납추이 (`usageTrend`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 대출정보를 기반으로 도서관의 대출반납 정보를 제공합니다.
- 제공 정보는 도서관의 요일별/시간대별 대출반납 추이입니다.

**엔드포인트**: `http://data4library.kr/api/usageTrend`

**호출 예**
```
http://data4library.kr/api/usageTrend?authKey=[발급받은키]&libCode=[도서관코드]&type=[조회기준코드]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관코드 | **필수** | 숫자 |
| `type` | 조회기준 `[D: 요일별, H: 시간대별]` | **필수** | 문자열 |

**응답 트리 — 요일별 (`type=D`)**
```
libNm                   도서관명
results                 조회결과
  result[]              요일별 추이
    dayOfWeek           요일
    loan                대출 상대적 수치(%)
    return              반납 상대적 수치(%)
```
- 요일별 대출반납추이는 최근 30일간 총 대출량, 반납량을 100으로 하여 상대적 비율을 제공
- `dayOfWeek`(요일)는 영문명으로 제공: Sunday, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday

**응답 트리 — 시간대별 (`type=H`)**
```
libNm                   도서관명
results                 조회결과
  result[]              시간대별 추이
    hour                시간대
    loan                대출 상대적 수치(%)
    return              반납 상대적 수치(%)
```
- 시간대별 대출반납추이는 최근 30일간 총 대출량, 반납량을 100으로 하여 상대적 비율을 제공
- `hour`(시간대) 값

| hour 값 | 의미 |
|---|---|
| `00` | 0시 ~ 9시 |
| `09` ~ `19` | 각 시간대별 제공 |
| `20` | 20시 ~ 23시 |

**응답 예시 — 요일별**
```xml
<response>
  <request><libCode>141321</libCode><type>D</type></request>
  <libNm>부천시립상동도서관</libNm>
  <results>
    <result><dayOfWeek>Sunday</dayOfWeek><loan>28</loan><return>26</return></result>
    <result><dayOfWeek>Monday</dayOfWeek><loan>12</loan><return>12</return></result>
    <result><dayOfWeek>Tuesday</dayOfWeek><loan>12</loan><return>12</return></result>
    <result><dayOfWeek>Wednesday</dayOfWeek><loan>12</loan><return>12</return></result>
    <result><dayOfWeek>Thursday</dayOfWeek><loan>10</loan><return>8</return></result>
    <!-- … -->
  </results>
</response>
```

**응답 예시 — 시간대별**
```xml
<response>
  <request><libCode>141321</libCode><type>H</type></request>
  <libNm>부천시립상동도서관</libNm>
  <results>
    <result><hour>00</hour><loan>0</loan><return>1</return></result>
    <result><hour>09</hour><loan>5</loan><return>7</return></result>
    <result><hour>10</hour><loan>7</loan><return>8</return></result>
    <result><hour>11</hour><loan>8</loan><return>8</return></result>
    <result><hour>12</hour><loan>8</loan><return>8</return></result>
    <!-- … -->
  </results>
</response>
```

---

## 11. 도서관별 도서 소장여부 및 대출 가능여부 조회 (`bookExist`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 대출정보를 기반으로 특정 도서관의 도서 소장여부와 대출 가능여부 정보를 제공합니다.

**엔드포인트**: `http://data4library.kr/api/bookExist`

**호출 예**
```
http://data4library.kr/api/bookExist?authKey=[발급받은키]&libCode=[도서관코드]&isbn13=[ISBN]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관코드 | **필수** | 숫자(코드) |
| `isbn13` | 13자리 ISBN | **필수** | 숫자 |

**응답 트리**
```
result                  조회결과
  hasBook               도서 소장여부
  loanAvailable         대출 가능여부
```
- 도서 소장여부는 ISBN 기준으로 제공
- 대출 가능여부는 **조회일 기준 전날의 대출 상태**를 기준으로 제공

**응답 예시**
```xml
<response>
  <request><isbn13>9791191056556</isbn13><libCode>050001</libCode></request>
  <result>
    <hasBook>Y</hasBook>
    <loanAvailable>Y</loanAvailable>
  </result>
</response>
```
> 📝 예시 기준으로 값은 `Y`/`N` 형태로 보입니다(원문 예시는 Y만 있음).

---

## 12. 대출 급상승 도서 (`hotTrend`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 대출정보를 기반으로, 검색일자 기준 최근 7일간 대출순위가 급상승한 도서 정보를 제공합니다.
- 검색일자를 포함한 최근 3일치의 대출급상승 도서를 한 번에 조회할 수 있습니다.

**엔드포인트**: `http://data4library.kr/api/hotTrend`

**호출 예**
```
http://data4library.kr/api/hotTrend?authKey=[발급받은키]&searchDt=[검색일자]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `searchDt` | 검색일자 | **필수** | yyyy-mm-dd |

**응답 트리**
```
results                 조회결과
  result[]              일자별 결과
    date                기준일자
    docs                목록
      doc[]             도서
        no                  순번
        difference          대출순위 상승폭
        baseWeekRank        기준일 순위
        pastWeekRank        전주 순위
        bookname            도서명
        authors             저자명
        publisher           출판사
        publication_year    출판년도
        isbn13              13자리 ISBN
        addition_symbol     ISBN 부가기호
        vol                 권
        class_no            주제분류
        class_nm            주제분류명
        bookImageURL        책표지 URL
        bookDtlUrl          도서 상세 페이지 URL
```
- 검색일자를 포함한 최근 3일치의 대출급상승 도서 데이터를 제공
- 일자별 최대 5위까지의 대출급상승 도서 데이터를 제공
- 대출급상승 도서는 기준일자 당시 도서관 빅데이터 사업에 참여한 도서관의 대출건수를 반영하여 생성. 기준일자 이후 사업에 참여한 도서관의 대출건수는 반영하지 않음
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <request><searchDt>2022-05-08</searchDt></request>
  <results>
    <result>
      <date>2022-05-08</date>
      <docs>
        <doc>
          <no>1</no>
          <difference>153</difference>
          <baseWeekRank>91</baseWeekRank>
          <pastWeekRank>244</pastWeekRank>
          <bookname>여행의 이유 :김영하 산문</bookname>
          <authors>지은이: 김영하</authors>
          <publisher>문학동네</publisher>
          <publication_year>2019</publication_year>
          <isbn13>9788954655972</isbn13>
          <addition_symbol>03810</addition_symbol>
          <vol/>
          <!-- …(스크린샷에서 잘림) -->
        </doc>
      </docs>
    </result>
    <!-- result는 3일치 반복 -->
  </results>
</response>
```
> 📝 `difference` = `pastWeekRank` − `baseWeekRank` (예: 244 − 91 = 153). 예시 값으로 확인한 관계입니다.

---

## 13. 도서 소장 도서관 조회 (`libSrchByBook`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 장서정보를 기반으로 특정 도서를 소장한 도서관 정보를 제공합니다.

**엔드포인트**: `http://data4library.kr/api/libSrchByBook`

**호출 예**
```
http://data4library.kr/api/libSrchByBook?authKey=[발급받은키]&isbn=[ISBN]&region=[지역코드]
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `isbn` | 13자리 ISBN | **필수** | 숫자 |
| `region` | 지역 | **필수** | 숫자(코드) |
| `dtl_region` | 세부지역 | 선택 | 숫자(코드) |

> 📝 이 API는 ISBN 파라미터 이름이 `isbn13`이 아니라 **`isbn`** 입니다(원문 그대로). 원문에는 `pageSize` 기본값이 적혀 있지 않습니다.

**응답 트리**
```
pageNo                  페이지번호
pageSize                페이지크기
numFound                전체 검색결과 건수
resultNum               응답결과 건수
libs                    목록
  lib[]                 도서관
    libCode             도서관코드
    libName             도서관명
    address             주소
    tel                 전화번호
    fax                 FAX 번호
    latitude            위도
    longitude           경도
    homepage            홈페이지 URL
    closed              휴관일
    operatingTime       운영시간
```

**응답 예시**
```xml
<response>
  <pageNo/>
  <pageSize>10</pageSize>
  <numFound>3</numFound>
  <resultNum>3</resultNum>
  <libs>
    <lib>
      <libCode>111017</libCode>
      <libName>서울특별시교육청서울시립어린이도서관</libName>
      <address>서울특별시 종로구 사직로 9길 7</address>
      <tel>02-731-2300</tel>
      <fax>02-736-8914</fax>
      <latitude>37.5763001</latitude>
      <longitude>126.968237</longitude>
      <homepage>http://childlib.sen.go.kr/</homepage>
      <closed>매월 첫째주, 셋째주 월요일 / 일요일을 제외한 법정공휴일, 도서관 사정으로 임시로 정하는 휴…(잘림)</closed>
      <operatingTime>평일 09:00~18:00, 주말 09:00~17:00</operatingTime>
    </lib>
  </libs>
</response>
```
> 📝 예시에는 `pageSize=10`이 찍혀 있지만, 원문 규칙에 명시된 기본값은 아닙니다.

---

## 14. 도서관별 통합정보 (`extends/libSrch`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 장서 및 대출정보를 기반으로 도서관 정보, 대출반납추이, 신착도서 정보를 통합하여 제공합니다.

**엔드포인트**: `http://data4library.kr/api/extends/libSrch`

**호출 예**
```
http://data4library.kr/api/extends/libSrch?authKey=[발급받은키]&pageNo=1&pageSize=10
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관 코드 | 선택 | 숫자(코드) |
| `region` | 지역 | 선택 | 숫자(코드) |
| `dtl_region` | 세부지역 | 선택 | 숫자(코드) |

**규칙**
- `pageSize` 기본값: 페이지당 **10개** 도서관 목록 제공

**응답 트리**
```
pageNo                  페이지 번호
pageSize                페이지 크기
numFound                전체 검색결과 건수
resultNum               응답결과 건수
libs                    목록
  lib[]                 도서관
    libInfo             도서관 정보
      libCode           도서관코드
      libName           도서관명
      address           주소
      tel               전화번호
      fax               FAX 번호
      latitude          위도
      longitude         경도
      homepage          홈페이지 URL
      closed            휴관일
      operatingTime     운영시간
      BookCount         단행본수
    loanByhours         시간대별 대출추이
      result[]          시간대별 추이
        hour            시간대
        loan            대출 상대적 수치(%)
        return          반납 상대적 수치(%)
    loanByDayofWeek     요일별 대출추이
      result[]          요일별 추이
        dayOfWeek       요일
        loan            대출 상대적 수치(%)
        return          반납 상대적 수치(%)
    newBooks            신착도서
      book[]            도서
        bookname            도서명
        authors             저자명
        publisher           출판사
        publication_year    출판년도
        isbn13              13자리 ISBN
        set_isbn13          세트 13자리 ISBN
        bookImageURL        책표지 URL
        addition_symbol     ISBN 부가기호
        vol                 권
        class_no            주제분류
        class_nm            주제분류명
        reg_date            등록일자
```
- 단행본수(`BookCount`)는 도서관이 소장한 도서의 권수
- 요일별·시간대별 대출반납추이는 최근 30일간 총 대출량, 반납량을 100으로 하여 상대적 비율을 제공
- `dayOfWeek`는 영문명(Sunday ~ Saturday), `hour` 값은 [10번 표](#10-도서관별-대출반납추이-usagetrend)와 같음(00: 0~9시, 09~19: 각 시간대, 20: 20~23시)
- 신착도서(`newBooks`)는 등록일 기준 최신도서 10권 제공
- `bookImageURL` 이용 제한 적용

> 📝 원문 명세 표는 `loanByhours` 중간에서 페이지가 나뉘어 `loanByDayofWeek`·`newBooks`의 들여쓰기 기준이 바뀝니다. 위 트리는 첫 페이지의 `loanByhours` 위치와 의미를 근거로 `loanByDayofWeek`, `newBooks`를 `lib` 아래(`libInfo`와 같은 단계)에 두었습니다. 대소문자도 원문 그대로입니다(`loanByhours`, `loanByDayofWeek`).

**응답 예시**
```xml
<response>
  <request><libCode>050001</libCode></request>
  <numFound>1</numFound>
  <resultNum>1</resultNum>
  <libs>
    <lib>
      <libInfo>
        <libCode>050001</libCode>
        <libName>국립세종도서관</libName>
        <address>세종특별자치시 다솜3로 48</address>
        <tel>044-900-9114</tel>
        <fax>044-900-9055</fax>
        <latitude>36.4989631</latitude>
        <longitude>127.268342</longitude>
        <homepage>http://sejong.nl.go.kr/</homepage>
        <closed>매월 둘째주, 넷째주 월요일 / 일요일을 제외한 관공서의 공휴일 (단, 설, 추석 연휴기간 중의 일요일은 휴관), 기타 관장이 필요하다고 인정하는 날</closed>
        <operatingTime>주중 10:00~17:30, 주말 10:00~17:30</operatingTime>
        <BookCount>771724</BookCount>
      </libInfo>
      <loanByhours>
        <result><hour>00</hour><loan>0</loan><return>2</return></result>
        <result><hour>09</hour><loan>1</loan><return>11</return></result>
        <result><hour>10</hour><loan>17</loan><return>12</return></result>
        <result><hour>11</hour><loan>15</loan><return>13</return></result>
        <result><hour>12</hour><loan>16</loan><return>12</return></result>
        <!-- … -->
      </loanByhours>
      <loanByDayofWeek>
        <result><dayOfWeek>Sunday</dayOfWeek><loan>11</loan><return>12</return></result>
        <result><dayOfWeek>Monday</dayOfWeek><loan>2</loan><return>16</return></result>
        <result><dayOfWeek>Tuesday</dayOfWeek><loan>7</loan><return>14</return></result>
        <result><dayOfWeek>Wednesday</dayOfWeek><loan>24</loan><return>16</return></result>
        <result><dayOfWeek>Thursday</dayOfWeek><loan>22</loan><return>15</return></result>
        <!-- … -->
      </loanByDayofWeek>
      <newBooks>
        <book>
          <bookname>순환형 경제를 만든다</bookname>
          <authors>지음: 후지야마 코,아리타 쇼이치로,도요타 토모요,고스가 요시타케,시게토 사와코 ;옮김: 민범식</authors>
          <publisher>국토연구원</publisher>
          <publication_year>2020</publication_year>
          <isbn13>9791158986377</isbn13>
          <set_isbn13/>
          <bookImageURL>https://bookthumb-phinf.pstatic.net/cover/189/926/18992684.jpg?type=m1&amp;udate=20211218</bookImageURL>
          <addition_symbol/>
          <vol/>
          <class_no>539.7</class_no>
          <class_nm>기술과학 > 공학, 공업일반 > 위생, 도시, 환경공학</class_nm>
          <reg_date>2022-05-06</reg_date>
        </book>
      </newBooks>
    </lib>
  </libs>
</response>
```

---

## 15. 도서관별 인기대출도서 통합 (`extends/loanItemSrchByLib`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 장서 및 대출정보를 기반으로 도서관별 인기대출도서를 통합하여 제공합니다.
- 도서관별 인기대출도서를 다양한 조건으로 조회할 수 있습니다. 제공 정보는 대출순위, 도서명, 저자명, 출판사, 출판년도, ISBN, KDC, 대출횟수 등입니다.
- 도서관별 인기대출도서는 ISBN을 기준으로 집계되며, 이용자 그룹별(전체/영유아/유아/초등/청소년/성인) 상위 20권의 도서 목록을 제공합니다.

**엔드포인트**: `http://data4library.kr/api/extends/loanItemSrchByLib`

**호출 예**
```
http://data4library.kr/api/extends/loanItemSrchByLib?authKey=[발급받은키]&libCode=[도서관코드]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관 코드 | **필수** | 숫자(코드) |

**응답 트리**

최상위에 이용자 그룹별 목록 6개가 있고, 구조는 모두 같습니다.

| 최상위 요소 | 설명 |
|---|---|
| `loanBooks` | 전체 인기대출목록 |
| `age0Books` | 영유아 인기대출목록 |
| `age6Books` | 유아 인기대출목록 |
| `age8Books` | 초등 인기대출목록 |
| `age14Books` | 청소년 인기대출목록 |
| `age20Books` | 성인 인기대출목록 |

```
{loanBooks | age0Books | age6Books | age8Books | age14Books | age20Books}
  book[]                도서
    no                  순번
    ranking             순위
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     ISBN 부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
    bookDtlUrl          도서 상세 페이지 URL
```
- 인기대출도서는 최근 30일을 기준으로 상위 20권 제공
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <request><libCode>050001</libCode></request>
  <loanBooks>
    <book>
      <no>1</no>
      <ranking>1</ranking>
      <bookname>마법의 설탕 두 조각</bookname>
      <authors>미하엘 엔데 글;유혜자 옮김</authors>
      <publisher>한길사</publisher>
      <publication_year>2001</publication_year>
      <isbn13>9788935652792</isbn13>
      <addition_symbol>74850</addition_symbol>
      <vol/>
      <class_no>853</class_no>
      <class_nm>문학 > 독일문학 > 소설</class_nm>
      <loan_count>4</loan_count>
      <bookImageURL>http://image.aladin.co.kr/product/27/73/cover/8935652792_2.jpg</bookImageURL>
    </book>
  </loanBooks>
  <age0Books>
    <book>
      <no>1</no>
      <ranking>1</ranking>
      <bookname>온 세상 국기가 펄럭펄럭</bookname>
      <authors>서정훈 글 ;김성희 그림</authors>
      <publisher>웅진씽크빅</publisher>
      <publication_year>2010</publication_year>
      <isbn13>9788901109237</isbn13>
      <addition_symbol>74300</addition_symbol>
      <vol/>
      <class_no>300</class_no>
      <class_nm>사회과학 > 사회과학 > 사회과학</class_nm>
      <loan_count>1</loan_count>
      <bookImageURL>https://bookthumb-phinf.pstatic.net/cover/…(잘림)</bookImageURL>
    </book>
  </age0Books>
  <age6Books>
    <book>
      <no>1</no>
      <ranking>1</ranking>
      <bookname>Froggy goes to school</bookname>
      <authors>by Jonathan London;illustrated by Frank Re…(잘림)</authors>
      <publisher>Puffin Books</publisher>
      <publication_year/>
      <isbn13>9780140562477</isbn13>
      <addition_symbol/>
      <vol/>
      <class_no/>
      <class_nm/>
      <loan_count>1</loan_count>
      <bookImageURL>http://image.aladin.co.kr/product/95/20/co…(잘림)</bookImageURL>
    </book>
  </age6Books>
  <!-- age8Books, age14Books, age20Books 동일 구조 -->
</response>
```
> 📝 예시에는 명세 표에 없는 **`loan_count`** 가 나옵니다. 반대로 명세 표에 있는 `bookDtlUrl`은 예시 화면에 보이지 않습니다.

---

## 16. 도서 검색 (`srchBooks`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 장서 및 대출정보를 기반으로 도서를 검색합니다.

**엔드포인트**: `http://data4library.kr/api/srchBooks`

**호출 예**
```
http://data4library.kr/api/srchBooks?authKey=[발급받은키]&keyword=[검색어]&pageNo=1&pageSize=10
```

**요청 파라미터** (공통: `authKey`, `format`, `pageNo`, `pageSize`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `title` | 도서명 | 선택 | 문자열 |
| `author` | 저자명 | 선택 | 문자열 |
| `isbn13` | 13자리 ISBN | 선택 | 숫자 |
| `keyword` | 키워드(다중선택가능) | 선택 | 문자열 |
| `publisher` | 출판사 | 선택 | 문자열 |
| `sort` | 정렬필드 `[title, author, pub, pubYear, isbn, loan 택 1]` | 선택 | 문자열 |
| `order` | 정렬순서 `[asc, desc 택 1]` | 선택 | 문자열 |
| `exactMatch` | 일치검색여부 `[true, false 택 1]` | 선택 | 문자열 |

**규칙**
- `title`, `author`, `isbn13`, `keyword`, `publisher`가 모두 없으면 전체 대출데이터를 기준으로 조회
- 이 다섯 항목 중 2개 이상을 입력하면 AND 검색
  - 예: `title=알사탕&author=백희나` 입력 시, 도서명이 "알사탕"이고 저자명이 "백희나"인 조건을 동시에 충족하는 결과 제공
- 키워드는 `;`로 구분하여 다중 조회 가능
- `sort`가 없으면 대출건수 순으로 정렬

  | sort 값 | 의미 |
  |---|---|
  | `title` | 도서명 순 |
  | `author` | 저자명 순 |
  | `pub` | 출판사 순 |
  | `pubYear` | 출판년도 순 |
  | `isbn` | ISBN 순 |
  | `loan` | 대출건수 순 |

- `order`가 없으면 내림차순으로 정렬. `asc`는 오름차순, `desc`는 내림차순
- `exactMatch`가 없으면 일치검색이 아닌 결과를 제공. `true`는 일치검색 O, `false`는 일치검색 X
  - 단, `keyword`를 입력하면 일치검색 결과만 제공
- `pageSize` 기본값: 페이지당 **20개** 제공

> 📝 원문은 "페이지당 20 개 **키워드** 제공"이라고 적었는데, 문맥상 도서 목록 20건을 뜻하는 것으로 보입니다.

**응답 트리**
```
numFound                전체 검색결과 건수
docs                    목록
  doc[]                 도서
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    addition_symbol     부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    bookImageURL        책표지 URL
    bookDtlUrl          도서 상세 페이지 URL
    loan_count          대출건수
```
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <request><keyword>사피엔스</keyword><pageNo>1</pageNo><pageSize>20</pageSize></request>
  <docs>
    <doc>
      <bookname>사피엔스 :유인원에서 사이보그까지, 인간 역사의 대담하고 위대한 질문</bookname>
      <authors>지은이: 유발 하라리 ;옮긴이: 조현욱</authors>
      <publisher>김영사</publisher>
      <publication_year>2015</publication_year>
      <isbn13>9788934972464</isbn13>
      <vol/>
      <loan_count>131458</loan_count>
    </doc>
  </docs>
</response>
```
> 📝 위 예시는 원문 스크린샷에 보이는 필드만 옮긴 것입니다. 명세상의 다른 필드는 화면에 나오지 않았습니다.

---

## 17. 이달의 키워드 (`monthlyKeywords`)

**주요기능**
- 빅데이터 분석 플랫폼에서 분석한 이달의 키워드를 제공합니다.
- 월별 대출급상승 도서의 책 소개, 서평 등에서 추출한 단어에 TF-IDF를 적용하여 도출한 키워드로, 100건까지 제공합니다.

**엔드포인트**: `http://data4library.kr/api/monthlyKeywords`

**호출 예**
```
http://data4library.kr/api/monthlyKeywords?authKey=[발급받은키]&month=2022-06
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `month` | 검색월 | 선택 | yyyy-mm |

**규칙**
- 검색월은 검색일 기준 직전월까지 조회 가능
  - 예: 2022년 12월 31일 검색 시, 2020-01 ~ 2022-11 데이터까지 조회
- `month`를 입력하지 않으면 검색일 직전월의 키워드를 제공
  - 예: 2022년 12월 31일 검색 시, 2022-11 키워드 제공

**응답 트리**
```
keywords                항목
  keyword[]             기본항목
    word                단어
    weight              가중치
```
- 이달의 키워드는 100건 제공

**응답 예시**
```xml
<response>
  <request><month>2022-06</month><resultNum>100</resultNum></request>
  <keywords>
    <keyword><word>다양</word><weight>470</weight></keyword>
    <keyword><word>어린이</word><weight>450</weight></keyword>
    <keyword><word>사람</word><weight>421</weight></keyword>
    <!-- keyword 반복 -->
  </keywords>
</response>
```

---

## 18. 지역별 독서량/독서율 (`readQt`)

**주요기능**
- 빅데이터 분석 플랫폼에서 분석한 지역별 독서량과 독서율을 제공합니다.

**엔드포인트**: `http://data4library.kr/api/readQt`

**호출 예**
```
http://data4library.kr/api/readQt?authKey=[발급받은키]&region=11&dtl_region=11230
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `region` | 지역 | 선택 | 숫자(코드) |
| `dtl_region` | 세부지역 | 선택 | 숫자(코드) |
| `year` | 분석연도 | 선택 | yyyy |
| `month` | 분석월 | 선택 | mm |

**규칙**
- 지역(`region`)이 없을 경우 모든 지역을 대상으로 설정
- 분석연도(`year`)와 분석월(`month`)이 없으면 조회일 직전연도로 자동 설정
  - 예: 분석연월을 입력하지 않고 2023년 12월 31일에 조회 시, 2022년 정보 제공
- 분석연도(`year`)는 2016년부터 조회일 직전연도까지 입력 가능
- 분석월(`month`)을 입력하면 분석연도(`year`)는 필수 입력

**응답 트리**
```
results                 목록
  result[]              지역별 독서량/독서율
    age                 연령
    quantity            독서량
    rate                독서율
```
- 독서량(`quantity`): 대출 회원 1명이 읽은 일반도서의 권수 (대출 권수 / 대출 회원수)
- 독서율(`rate`): 일반도서를 1권 이상 읽은 사람의 비율 (대출 회원수 / 전체 회원수)

**응답 예시** (`region=11&dtl_region=11230`)
```xml
<response>
  <request><region>서울특별시</region><dtl_region>강남구</dtl_region></request>
  <results>
    <result><age>영유아</age><quantity>35.48</quantity><rate>3.88</rate></result>
    <result><age>유아</age><quantity>40.79</quantity><rate>3.65</rate></result>
    <result><age>초등</age><quantity>30.2</quantity><rate>2.66</rate></result>
    <result><age>청소년</age><quantity>10.93</quantity><rate>0.69</rate></result>
    <result><age>20대</age><quantity>7.76</quantity><rate>0.27</rate></result>
    <!-- … -->
  </results>
</response>
```
> 📝 예시에서 `request`의 지역은 코드가 아니라 명칭(`서울특별시`, `강남구`)으로 되돌아오고, `age`도 한글 명칭으로 옵니다.

---

## 19. 신착도서 조회 (`newArrivalBook`)

**주요기능**
- 빅데이터 분석 플랫폼에서 수집된 도서관의 신착도서 정보를 제공합니다.

**엔드포인트**: `http://data4library.kr/api/newArrivalBook`

**호출 예**
```
http://data4library.kr/api/newArrivalBook?authKey=[발급받은키]&libCode=[도서관코드]
```

**요청 파라미터** (공통: `authKey`, `format`)

| 파라미터 | 설명 | 필수여부 | 입력형태 |
|---|---|---|---|
| `libCode` | 도서관 코드 | **필수** | 숫자 |
| `searchDt` | 검색일자 | 선택 | yyyy-mm |

**규칙**
- `searchDt`가 없을 경우 조회일의 연월로 자동 설정
  - 예: 검색일자를 입력하지 않고 2023년 12월 31일에 조회 시, 2023년 12월 정보 제공

> 📝 이름은 '검색일자'지만 입력형태는 **`yyyy-mm`(연월)** 입니다(원문 그대로). 응답에 `pageNo`·`pageSize`가 있으나 원문 요청 표에는 페이지 파라미터가 없습니다.

**응답 트리**
```
libNm                   도서관명
pageNo                  페이지 번호
pageSize                페이지 크기
numFound                전체 검색결과 건수
resultNum               응답결과 건수
docs                    목록
  doc[]                 도서
    bookname            도서명
    authors             저자명
    publisher           출판사
    publication_year    출판년도
    isbn13              13자리 ISBN
    set_isbn13          13자리 세트 ISBN
    bookImageURL        책표지 URL
    addition_symbol     부가기호
    vol                 권
    class_no            주제분류
    class_nm            주제분류명
    reg_date            등록일자
```
- `bookImageURL` 이용 제한 적용

**응답 예시**
```xml
<response>
  <script/>
  <request><libCode>148042</libCode></request>
  <libNm>장유도서관</libNm>
  <pageNo>1</pageNo>
  <pageSize>100</pageSize>
  <numFound>100</numFound>
  <resultNum>10</resultNum>
  <docs>
    <doc>
      <bookname>박지운의 오페라와 인생</bookname>
      <authors>박지운 (지은이)</authors>
      <publisher>SUN(도서출판썬)</publisher>
      <publication_year>2024</publication_year>
      <isbn13>9791188270767</isbn13>
      <set_isbn13/>
      <bookImageURL>https://image.aladin.co.kr/product/33880/45/cover200/k652930719_1.jpg</bookImageURL>
      <addition_symbol/>
      <vol/>
      <class_no>670.4</class_no>
      <class_nm>예술 > 음악 > 음악</class_nm>
      <book_count/>
      <loan_count/>
      <reg_date>2024-06-19</reg_date>
    </doc>
  </docs>
</response>
```
> 📝 예시에는 명세에 없는 `<script/>`, `book_count`, `loan_count`가 보입니다. 예시상 `pageSize=100`이지만 원문 규칙에 기본값은 적혀 있지 않습니다.

---

## 20. 코드

코드값은 요청 파라미터와 응답 해석에 쓰입니다. 표의 첫 칸이 파라미터에 넣는 값입니다.

### 20.1 도서관 코드 (`libCode`)

정보나루의 참여도서관 목록을 참조합니다.

> 📝 [1. 정보공개 도서관 조회](#1-정보공개-도서관-조회-libsrch)(`libSrch`)의 응답 `libCode`로 얻을 수 있습니다. 예시의 `050001`처럼 앞자리 0이 붙는 코드가 있으니 **문자열로 다루는 것이 안전합니다**.

### 20.2 성별 코드 (`gender`)

| 코드값 | 상세 |
|---|---|
| `0` | 남성 |
| `1` | 여성 |
| `2` | 미상 |

### 20.3 연령 코드 (`age`)

| 코드값 | 상세 |
|---|---|
| `0` | 영유아(0~5세) |
| `6` | 유아(6~7세) |
| `8` | 초등(8~13세) |
| `14` | 청소년(14~19세) |
| `20` | 20대 |
| `30` | 30대 |
| `40` | 40대 |
| `50` | 50대 |
| `60` | 60세 이상 |
| `-1` | 미상 |
| `a8` | 1,2학년(8~9세) |
| `a10` | 3,4학년(10~11세) |
| `a12` | 5,6학년(12~13세) |
| `a14` | 중등(14~16세) |
| `a17` | 고등(17~19세) |

> 📝 원문 표의 입력형태는 '숫자(코드)'이지만 `a8` 같은 문자 코드도 포함되어 있습니다.

### 20.4 ISBN 부가기호 코드 (`addCode` / `addition_symbol`)

| 코드값 | 상세 |
|---|---|
| `0` | 교양 |
| `1` | 실용 |
| `2` | 여성 |
| `4` | 청소년 |
| `5` | 학습참고서1(중고) |
| `6` | 학습참고서2(초등) |
| `7` | 아동 |
| `9` | 전문 |

> 📝 응답 예시의 `addition_symbol`은 `03830`, `74850`처럼 5자리 전체 부가기호로 옵니다. 위 코드는 그 **첫 자리**(독자대상)에 해당하는 것으로 보입니다(추정). 원문에는 3, 8이 없습니다.

### 20.5 대주제 코드 (`kdc`)

| 코드값 | 상세 |
|---|---|
| `0` | 총류 |
| `1` | 철학 |
| `2` | 종교 |
| `3` | 사회과학 |
| `4` | 자연과학 |
| `5` | 기술과학 |
| `6` | 예술 |
| `7` | 언어 |
| `8` | 문학 |
| `9` | 역사 |

### 20.6 세부주제 코드 (`dtl_kdc`)

> 📝 세부주제 코드의 첫 자리는 대주제 코드와 같습니다(예: `81` 한국문학 → `kdc=8` 문학).

| 코드값 | 상세 |
|---|---|
| `00` | 총류 |
| `01` | 도서학, 서지학 |
| `02` | 문헌정보학 |
| `03` | 백과사전 |
| `04` | 일반 논문집 |
| `05` | 일반 연속간행물 |
| `06` | 학·협회,기관 |
| `07` | 신문, 언론, 저널리즘 |
| `08` | 일반 전집, 총서 |
| `09` | 향토자료 |
| `10` | 철학 |
| `11` | 형이상학 |
| `12` | 인식론, 인과론, 인간학 |
| `13` | 철학의 체계 |
| `14` | 경학 |
| `15` | 동양 철학, 사상 |
| `16` | 서양철학 |
| `17` | 논리학 |
| `18` | 심리학 |
| `19` | 윤리학, 도덕철학 |
| `20` | 종교 |
| `21` | 비교종교학 |
| `22` | 불교 |
| `23` | 기독교 |
| `24` | 도교 |
| `25` | 천도교 |
| `26` | 신도 |
| `27` | 바라문교, 인도교 |
| `28` | 회교(이슬람교) |
| `29` | 기타 제종교 |
| `30` | 사회과학 |
| `31` | 통계학 |
| `32` | 경제학 |
| `33` | 사회학, 사회문제 |
| `34` | 정치학 |
| `35` | 행정학 |
| `36` | 법학 |
| `37` | 교육학 |
| `38` | 풍속, 민속학 |
| `39` | 국방, 군사학 |
| `40` | 자연과학 |
| `41` | 수학 |
| `42` | 물리학 |
| `43` | 화학 |
| `44` | 천문학 |
| `45` | 지학 |
| `46` | 광물학 |
| `47` | 생물과학 |
| `48` | 식물학 |
| `49` | 동물학 |
| `50` | 기술과학 |
| `51` | 의학 |
| `52` | 농업, 농학 |
| `53` | 공학, 공업일반 |
| `54` | 건축공학 |
| `55` | 기계공학 |
| `56` | 전기공학, 전자공학 |
| `57` | 화학공학 |
| `58` | 제조업 |
| `59` | 가정학 및 가정생활 |
| `60` | 예술 |
| `61` | 건축술 |
| `62` | 조각 |
| `63` | 공예, 장식미술 |
| `64` | 서예 |
| `65` | 회화, 도화 |
| `66` | 사진술 |
| `67` | 음악 |
| `68` | 연극 |
| `69` | 오락, 운동 |
| `70` | 언어 |
| `71` | 한국어 |
| `72` | 중국어 |
| `73` | 일본어 |
| `74` | 영어 |
| `75` | 독일어 |
| `76` | 프랑스어 |
| `77` | 스페인어 |
| `78` | 이탈리아어 |
| `79` | 기타 제어 |
| `80` | 문학 |
| `81` | 한국문학 |
| `82` | 중국문학 |
| `83` | 일본문학 |
| `84` | 영미문학 |
| `85` | 독일문학 |
| `86` | 프랑스문학 |
| `87` | 스페인문학 |
| `88` | 이탈리아문학 |
| `89` | 기타 제문학 |
| `90` | 역사 |
| `91` | 아시아(아세아) |
| `92` | 유럽(구라파) |
| `93` | 아프리카 |
| `94` | 북아메리카(북미) |
| `95` | 남아메리카(남미) |
| `96` | 오세아니아(대양주) |
| `97` | 양극지방 |
| `98` | 지리 |
| `99` | 전기 |

### 20.7 지역 코드 (`region`)

| 코드값 | 광역시도명 |
|---|---|
| `11` | 서울 |
| `21` | 부산 |
| `22` | 대구 |
| `23` | 인천 |
| `24` | 광주 |
| `25` | 대전 |
| `26` | 울산 |
| `29` | 세종 |
| `31` | 경기 |
| `32` | 강원 |
| `33` | 충북 |
| `34` | 충남 |
| `35` | 전북 |
| `36` | 전남 |
| `37` | 경북 |
| `38` | 경남 |
| `39` | 제주 |

### 20.8 세부지역 코드 (`dtl_region`)

> 📝 세부지역 코드의 앞 두 자리는 지역 코드와 같습니다(예: `21010` → `region=21` 부산).

| 코드값 | 광역시도명 | 세부지역명 |
|---|---|---|
| `11010` | 서울특별시 | 종로구 |
| `11020` | 서울특별시 | 중구 |
| `11030` | 서울특별시 | 용산구 |
| `11040` | 서울특별시 | 성동구 |
| `11050` | 서울특별시 | 광진구 |
| `11060` | 서울특별시 | 동대문구 |
| `11070` | 서울특별시 | 중랑구 |
| `11080` | 서울특별시 | 성북구 |
| `11090` | 서울특별시 | 강북구 |
| `11100` | 서울특별시 | 도봉구 |
| `11110` | 서울특별시 | 노원구 |
| `11120` | 서울특별시 | 은평구 |
| `11130` | 서울특별시 | 서대문구 |
| `11140` | 서울특별시 | 마포구 |
| `11150` | 서울특별시 | 양천구 |
| `11160` | 서울특별시 | 강서구 |
| `11170` | 서울특별시 | 구로구 |
| `11180` | 서울특별시 | 금천구 |
| `11190` | 서울특별시 | 영등포구 |
| `11200` | 서울특별시 | 동작구 |
| `11210` | 서울특별시 | 관악구 |
| `11220` | 서울특별시 | 서초구 |
| `11230` | 서울특별시 | 강남구 |
| `11240` | 서울특별시 | 송파구 |
| `11250` | 서울특별시 | 강동구 |
| `21010` | 부산광역시 | 중구 |
| `21020` | 부산광역시 | 서구 |
| `21030` | 부산광역시 | 동구 |
| `21040` | 부산광역시 | 영도구 |
| `21050` | 부산광역시 | 부산진구 |
| `21060` | 부산광역시 | 동래구 |
| `21070` | 부산광역시 | 남구 |
| `21080` | 부산광역시 | 북구 |
| `21090` | 부산광역시 | 해운대구 |
| `21100` | 부산광역시 | 사하구 |
| `21110` | 부산광역시 | 금정구 |
| `21120` | 부산광역시 | 강서구 |
| `21130` | 부산광역시 | 연제구 |
| `21140` | 부산광역시 | 수영구 |
| `21150` | 부산광역시 | 사상구 |
| `21510` | 부산광역시 | 기장군 |
| `22010` | 대구광역시 | 중구 |
| `22020` | 대구광역시 | 동구 |
| `22030` | 대구광역시 | 서구 |
| `22040` | 대구광역시 | 남구 |
| `22050` | 대구광역시 | 북구 |
| `22060` | 대구광역시 | 수성구 |
| `22070` | 대구광역시 | 달서구 |
| `22510` | 대구광역시 | 달성군 |
| `22520` | 대구광역시 | 군위군 |
| `23010` | 인천광역시 | 중구 |
| `23020` | 인천광역시 | 동구 |
| `23030` | 인천광역시 | 남구 (코드삭제) |
| `23040` | 인천광역시 | 연수구 |
| `23050` | 인천광역시 | 남동구 |
| `23060` | 인천광역시 | 부평구 |
| `23070` | 인천광역시 | 계양구 |
| `23080` | 인천광역시 | 서구 |
| `23090` | 인천광역시 | 미추홀구 |
| `23510` | 인천광역시 | 강화군 |
| `23520` | 인천광역시 | 옹진군 |
| `24010` | 광주광역시 | 동구 |
| `24020` | 광주광역시 | 서구 |
| `24030` | 광주광역시 | 남구 |
| `24040` | 광주광역시 | 북구 |
| `24050` | 광주광역시 | 광산구 |
| `25010` | 대전광역시 | 동구 |
| `25020` | 대전광역시 | 중구 |
| `25030` | 대전광역시 | 서구 |
| `25040` | 대전광역시 | 유성구 |
| `25050` | 대전광역시 | 대덕구 |
| `26010` | 울산광역시 | 중구 |
| `26020` | 울산광역시 | 남구 |
| `26030` | 울산광역시 | 동구 |
| `26040` | 울산광역시 | 북구 |
| `26510` | 울산광역시 | 울주군 |
| `29010` | 세종특별자치시 | 세종시 |
| `31010` | 경기도 | 수원시 |
| `31011` | 경기도 | 수원시 장안구 |
| `31012` | 경기도 | 수원시 권선구 |
| `31013` | 경기도 | 수원시 팔달구 |
| `31014` | 경기도 | 수원시 영통구 |
| `31020` | 경기도 | 성남시 |
| `31021` | 경기도 | 성남시 수정구 |
| `31022` | 경기도 | 성남시 중원구 |
| `31023` | 경기도 | 성남시 분당구 |
| `31030` | 경기도 | 의정부시 |
| `31040` | 경기도 | 안양시 |
| `31041` | 경기도 | 안양시 만안구 |
| `31042` | 경기도 | 안양시 동안구 |
| `31050` | 경기도 | 부천시 |
| `31051` | 경기도 | 부천시 원미구 |
| `31052` | 경기도 | 부천시 소사구 |
| `31053` | 경기도 | 부천시 오정구 |
| `31060` | 경기도 | 광명시 |
| `31070` | 경기도 | 평택시 |
| `31080` | 경기도 | 동두천시 |
| `31090` | 경기도 | 안산시 |
| `31091` | 경기도 | 안산시 상록구 |
| `31092` | 경기도 | 안산시 단원구 |
| `31100` | 경기도 | 고양시 |
| `31101` | 경기도 | 고양시 덕양구 |
| `31103` | 경기도 | 고양시 일산동구 |
| `31104` | 경기도 | 고양시 일산서구 |
| `31110` | 경기도 | 과천시 |
| `31120` | 경기도 | 구리시 |
| `31130` | 경기도 | 남양주시 |
| `31140` | 경기도 | 오산시 |
| `31150` | 경기도 | 시흥시 |
| `31160` | 경기도 | 군포시 |
| `31170` | 경기도 | 의왕시 |
| `31180` | 경기도 | 하남시 |
| `31190` | 경기도 | 용인시 |
| `31191` | 경기도 | 용인시 처인구 |
| `31192` | 경기도 | 용인시 기흥구 |
| `31193` | 경기도 | 용인시 수지구 |
| `31200` | 경기도 | 파주시 |
| `31210` | 경기도 | 이천시 |
| `31220` | 경기도 | 안성시 |
| `31230` | 경기도 | 김포시 |
| `31240` | 경기도 | 화성시 |
| `31250` | 경기도 | 광주시 |
| `31260` | 경기도 | 양주시 |
| `31270` | 경기도 | 포천시 |
| `31280` | 경기도 | 여주시 |
| `31550` | 경기도 | 연천군 |
| `31570` | 경기도 | 가평군 |
| `31580` | 경기도 | 양평군 |
| `32010` | 강원특별자치도 | 춘천시 |
| `32020` | 강원특별자치도 | 원주시 |
| `32030` | 강원특별자치도 | 강릉시 |
| `32040` | 강원특별자치도 | 동해시 |
| `32050` | 강원특별자치도 | 태백시 |
| `32060` | 강원특별자치도 | 속초시 |
| `32070` | 강원특별자치도 | 삼척시 |
| `32510` | 강원특별자치도 | 홍천군 |
| `32520` | 강원특별자치도 | 횡성군 |
| `32530` | 강원특별자치도 | 영월군 |
| `32540` | 강원특별자치도 | 평창군 |
| `32550` | 강원특별자치도 | 정선군 |
| `32560` | 강원특별자치도 | 철원군 |
| `32570` | 강원특별자치도 | 화천군 |
| `32580` | 강원특별자치도 | 양구군 |
| `32590` | 강원특별자치도 | 인제군 |
| `32600` | 강원특별자치도 | 고성군 |
| `32610` | 강원특별자치도 | 양양군 |
| `33020` | 충청북도 | 충주시 |
| `33030` | 충청북도 | 제천시 |
| `33040` | 충청북도 | 청주시 |
| `33041` | 충청북도 | 청주시 상당구 |
| `33042` | 충청북도 | 청주시 서원구 |
| `33043` | 충청북도 | 청주시 흥덕구 |
| `33044` | 충청북도 | 청주시 청원구 |
| `33520` | 충청북도 | 보은군 |
| `33530` | 충청북도 | 옥천군 |
| `33540` | 충청북도 | 영동군 |
| `33550` | 충청북도 | 진천군 |
| `33560` | 충청북도 | 괴산군 |
| `33570` | 충청북도 | 음성군 |
| `33580` | 충청북도 | 단양군 |
| `33590` | 충청북도 | 증평군 |
| `34010` | 충청남도 | 천안시 |
| `34011` | 충청남도 | 천안시 동남구 |
| `34012` | 충청남도 | 천안시 서북구 |
| `34020` | 충청남도 | 공주시 |
| `34030` | 충청남도 | 보령시 |
| `34040` | 충청남도 | 아산시 |
| `34050` | 충청남도 | 서산시 |
| `34060` | 충청남도 | 논산시 |
| `34070` | 충청남도 | 계룡시 |
| `34080` | 충청남도 | 당진시 |
| `34510` | 충청남도 | 금산군 |
| `34530` | 충청남도 | 부여군 |
| `34540` | 충청남도 | 서천군 |
| `34550` | 충청남도 | 청양군 |
| `34560` | 충청남도 | 홍성군 |
| `34570` | 충청남도 | 예산군 |
| `34580` | 충청남도 | 태안군 |
| `35010` | 전북특별자치도 | 전주시 |
| `35011` | 전북특별자치도 | 전주시 완산구 |
| `35012` | 전북특별자치도 | 전주시 덕진구 |
| `35020` | 전북특별자치도 | 군산시 |
| `35030` | 전북특별자치도 | 익산시 |
| `35040` | 전북특별자치도 | 정읍시 |
| `35050` | 전북특별자치도 | 남원시 |
| `35060` | 전북특별자치도 | 김제시 |
| `35510` | 전북특별자치도 | 완주군 |
| `35520` | 전북특별자치도 | 진안군 |
| `35530` | 전북특별자치도 | 무주군 |
| `35540` | 전북특별자치도 | 장수군 |
| `35550` | 전북특별자치도 | 임실군 |
| `35560` | 전북특별자치도 | 순창군 |
| `35570` | 전북특별자치도 | 고창군 |
| `35580` | 전북특별자치도 | 부안군 |
| `36010` | 전라남도 | 목포시 |
| `36020` | 전라남도 | 여수시 |
| `36030` | 전라남도 | 순천시 |
| `36040` | 전라남도 | 나주시 |
| `36060` | 전라남도 | 광양시 |
| `36510` | 전라남도 | 담양군 |
| `36520` | 전라남도 | 곡성군 |
| `36530` | 전라남도 | 구례군 |
| `36550` | 전라남도 | 고흥군 |
| `36560` | 전라남도 | 보성군 |
| `36570` | 전라남도 | 화순군 |
| `36580` | 전라남도 | 장흥군 |
| `36590` | 전라남도 | 강진군 |
| `36600` | 전라남도 | 해남군 |
| `36610` | 전라남도 | 영암군 |
| `36620` | 전라남도 | 무안군 |
| `36630` | 전라남도 | 함평군 |
| `36640` | 전라남도 | 영광군 |
| `36650` | 전라남도 | 장성군 |
| `36660` | 전라남도 | 완도군 |
| `36670` | 전라남도 | 진도군 |
| `36680` | 전라남도 | 신안군 |
| `37010` | 경상북도 | 포항시 |
| `37011` | 경상북도 | 포항시 남구 |
| `37012` | 경상북도 | 포항시 북구 |
| `37020` | 경상북도 | 경주시 |
| `37030` | 경상북도 | 김천시 |
| `37040` | 경상북도 | 안동시 |
| `37050` | 경상북도 | 구미시 |
| `37060` | 경상북도 | 영주시 |
| `37070` | 경상북도 | 영천시 |
| `37080` | 경상북도 | 상주시 |
| `37090` | 경상북도 | 문경시 |
| `37100` | 경상북도 | 경산시 |
| `37310` | 경상북도 | 군위군 (코드삭제) |
| `37520` | 경상북도 | 의성군 |
| `37530` | 경상북도 | 청송군 |
| `37540` | 경상북도 | 영양군 |
| `37550` | 경상북도 | 영덕군 |
| `37560` | 경상북도 | 청도군 |
| `37570` | 경상북도 | 고령군 |
| `37580` | 경상북도 | 성주군 |
| `37590` | 경상북도 | 칠곡군 |
| `37600` | 경상북도 | 예천군 |
| `37610` | 경상북도 | 봉화군 |
| `37620` | 경상북도 | 울진군 |
| `37630` | 경상북도 | 울릉군 |
| `38030` | 경상남도 | 진주시 |
| `38050` | 경상남도 | 통영시 |
| `38060` | 경상남도 | 사천시 |
| `38070` | 경상남도 | 김해시 |
| `38080` | 경상남도 | 밀양시 |
| `38090` | 경상남도 | 거제시 |
| `38100` | 경상남도 | 양산시 |
| `38110` | 경상남도 | 창원시 |
| `38111` | 경상남도 | 창원시 의창구 |
| `38112` | 경상남도 | 창원시 성산구 |
| `38113` | 경상남도 | 창원시 마산합포구 |
| `38114` | 경상남도 | 창원시 마산회원구 |
| `38115` | 경상남도 | 창원시 진해구 |
| `38510` | 경상남도 | 의령군 |
| `38520` | 경상남도 | 함안군 |
| `38530` | 경상남도 | 창녕군 |
| `38540` | 경상남도 | 고성군 |
| `38550` | 경상남도 | 남해군 |
| `38560` | 경상남도 | 하동군 |
| `38570` | 경상남도 | 산청군 |
| `38580` | 경상남도 | 함양군 |
| `38590` | 경상남도 | 거창군 |
| `38600` | 경상남도 | 합천군 |
| `39010` | 제주특별자치도 | 제주시 |
| `39020` | 제주특별자치도 | 서귀포시 |

---

## 부록. 변환 주석 모음

원문과 예시 화면을 대조하면서 발견한 내용입니다. 각 API 본문의 📝 주석을 한곳에 모았습니다.

### A. 원문 오기·불일치 (원문은 그대로 두고 주석만 담)
| API | 내용 |
|---|---|
| 6 `srchDtlList` | 예시의 `IoaninfoYN=Y`는 `loaninfoYN=Y`의 오기 |
| 6 `srchDtlList` | 표에는 isbn13이 '13자리 ISBN'이지만, 규칙에는 10자리·13자리 혼용 가능으로 적혀 있음(7, 8번도 같음) |
| 16 `srchBooks` | "페이지당 20개 **키워드**"는 문맥상 도서 목록 20건 |
| 19 `newArrivalBook` | 이름은 '검색일자'(`searchDt`)지만 형식은 `yyyy-mm` |
| 20 연령 코드 | 입력형태가 '숫자(코드)'인데 `a8` 같은 문자 코드가 있음 |

### B. 이름이 다른 곳 (헷갈리기 쉬움)
| API | 내용 |
|---|---|
| 4·5 `recommandList` | 엔드포인트 철자가 `recommand`. `docs` 아래 원소 이름이 `doc`이 아니라 `book` |
| 13 `libSrchByBook` | ISBN 파라미터 이름이 `isbn13`이 아니라 `isbn` |
| 3·9·15·16 | 대출건수 필드가 `loan_count`(스네이크). 6·8번은 `loanCnt`(카멜) |
| 14 `extends/libSrch` | `loanByhours`(h 소문자), `loanByDayofWeek`(of 소문자) |
| 9 `loanItemSrchByLib` | 세부지역명 필드가 `dtlregionNm` |

### C. 명세 표에 없지만 예시 응답에 나오는 것
| API | 내용 |
|---|---|
| 전체 | `<response>` 아래 `<request>` 블록(요청 파라미터 반환) |
| 8 `usageAnalysisList` | `coLoanBooks > book > loanCnt` |
| 15 `extends/loanItemSrchByLib` | `book > loan_count` |
| 19 `newArrivalBook` | `<script/>`, `doc > book_count`, `doc > loan_count` |

### D. 예시에서 관찰한 값 형식
| 항목 | 관찰 |
|---|---|
| 문자열 값 | `<![CDATA[ 값 ]]>`이고 앞뒤 공백 포함 → trim 필요 |
| 8번 `loanGrp`, 18번 `result` | `age`, `gender`가 코드가 아니라 한글 명칭(예: `40대`, `여성`, `영유아`) |
| 18번 `request` | `region`, `dtl_region`이 명칭으로 반환됨 |
| `addition_symbol` | 5자리 전체 부가기호(예: `03830`) |
| `libCode` | 앞자리 0 있음(예: `050001`) → 문자열로 처리 |
| 12번 `difference` | `pastWeekRank − baseWeekRank`와 일치 (예: 244 − 91 = 153) |
| JSON 응답 | 원문에 예시 없음 → 실제 호출로 구조 확인 필요 |

### E. 원문에 기본값이 없는 것
| API | 내용 |
|---|---|
| 13 `libSrchByBook` | `pageSize` 기본값 미기재(예시는 10) |
| 19 `newArrivalBook` | 페이지 파라미터 없음. 응답에는 `pageNo`·`pageSize` 있음(예시 100) |