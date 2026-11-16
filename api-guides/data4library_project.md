# 도서관 정보나루 API: 이 프로젝트에 쓰는 부분

원문은 `data4library.md`(매뉴얼 PDF v20260620을 옮긴 것)다. 이 문서는 그중 `add-bibliographic-sources`와 다음 change에 필요한 API, 필드, 규칙만 추렸다. 원문과 다르면 원문과 실제 응답을 따른다.

## 무엇에 쓰나

| 프로젝트에서 필요한 것 | API | 쓰는 필드 |
| --- | --- | --- |
| 공식 서지 채움 (서명·저자·출판사·소개·KDC) | 6 `srchDtlList` | `bookname`, `authors`, `publisher`, `publication_date`, `isbn13`, `class_no`, `class_nm`, `description`, `vol`, `addition_symbol` |
| 같은 KDC 세목 신호 | 6 `srchDtlList` | `class_no` (예 `813.7`) |
| 어린이 도서 분류 근거 | 6 `srchDtlList` | `addition_symbol`의 첫 자리 (`7` 아동) |
| 함께 대출된 책 | 8 `usageAnalysisList` | `coLoanBooks` (최대 10권, 최근 36개월) |
| 인기 대출 (전국, 연령 조건) | 3 `loanItemSrch` | `ranking`, `isbn13`, `loan_count`, `class_no` |

## 공통 규칙

- 호출은 `http://data4library.kr/api/{엔드포인트}?authKey=…&format=json` 꼴이다. 키는 `.env`의 `LIBRARY_BIGDATA_KEY`에 둔다.
- `format`이 없으면 XML로 온다. 원문에 JSON 예시가 없어, 배열이 어떤 키 구조로 오는지는 실제 호출로 확인해야 한다.
- ISBN 파라미터 `isbn13`에는 10자리와 13자리를 섞어 넣을 수 있다.
- 다중 선택 값은 `;`로 나눈다(예 `age=6;8`).
- **표지(`bookImageURL`) 이용 제한(원문)**: "비영리 서비스의 화면 표시에 한하여 이용 가능하며, 영리적 목적의 이용과 복사저장재배포 및 AI 입력학습 등 그 밖의 활용을 금함."
  → 표지는 URL만 두고 화면 표시에만 쓴다. 임베딩 텍스트나 LLM 입력에 넣지 않는다.

## 6. 도서 상세 조회 `srchDtlList`

- 요청: `isbn13`(필수). 대출 통계가 필요하면 `loaninfoYN=Y`, `displayInfo=gender|age|region`.
- `isbn13`만 주면 서지만 온다(도서명, 저자명, 출판사, 출판년, 권, KDC, 책소개, 표지 URL).
- 응답 `detail > book`: `bookname`, `authors`, `publisher`, `publication_date`, `publication_year`, `isbn`, `isbn13`, `addition_symbol`, `vol`, `class_no`, `class_nm`, `description`, `bookImageURL`
- `loanInfo`(`loaninfoYN=Y`일 때): `Total`, `ageResult`, `genderResult`, `regionResult`마다 `ranking`, `name`, `loanCnt`. 최근 90일 기준이고, 조건마다 상위 1,000위까지만 온다.

## 8. 도서별 이용 분석 `usageAnalysisList`

- 요청: `isbn13`(필수).
- 한 번 부르면 서지(`book`), 월별 대출 추이(`loanHistory`, 최근 12개월), 다대출 이용자 그룹(`loanGrps`, 최근 30일), 키워드(`keywords`, 최대 50), 함께 대출된 도서(`coLoanBooks`), 마니아 추천(`maniaRecBooks`), 다독자 추천(`readerRecBooks`)이 함께 온다.
- `book`: `bookname`, `authors`, `publisher`, `publication_year`, `isbn13`, `addition_symbol`, `vol`, `class_no`, `class_nm`, `description`, `bookImageURL`, `loanCnt`
  - `publication_date`가 없다. 출판일까지 필요하면 6번을 쓴다.
- `coLoanBooks > book[]`: `bookname`, `authors`, `publisher`, `publication_year`, `isbn13`, `vol`, `loanCnt`(명세에는 없고 예시에 있다). 최근 36개월의 동시 대출 빈도 순으로 최대 10권이다.
- `maniaRecBooks`·`readerRecBooks`: 최근 36개월, 조건부 확률로 고른 책 최대 10권(필드는 `coLoanBooks`와 같고 `loanCnt`가 없다).
- `loanGrps`의 `age`·`gender`는 코드가 아니라 한글 명칭이다(`40대`, `여성`).

## 3. 인기대출도서 조회 `loanItemSrch`

- 전국 공공도서관이 대상이다(우리 도서관의 인기가 아니다).
- 필터(모두 선택): `startDt`·`endDt`(`yyyy-mm-dd`), `gender`, `age` 또는 `from_age`·`to_age`, `region`·`dtl_region`, `addCode`, `kdc`·`dtl_kdc`, `book_dvsn`
  - `startDt`만 주면 `endDt`는 어제다. `endDt`만 주면 `startDt`는 2014-01-01이다.
  - `dtl_kdc`를 주면 `kdc`는 하나만 고를 수 있다.
- `pageSize` 기본 200이고 최대 5,000권까지 준다(ISBN 기준 집계).
- `docs > doc[]`: `ranking`, `bookname`, `authors`, `publisher`, `publication_year`, `isbn13`, `addition_symbol`, `vol`, `class_no`, `class_nm`, `bookImageURL`, `bookDtlUrl`, `loan_count`

## 코드

**연령 `age`**: `0` 영유아(0~5) · `6` 유아(6~7) · `8` 초등(8~13) · `14` 청소년(14~19) · `20`~`50` 각 연대 · `60` 60세 이상 · `-1` 미상. 학년 단위(`a8` 1·2학년, `a10` 3·4학년, `a12` 5·6학년, `a14` 중등, `a17` 고등)도 있다.

**ISBN 부가기호 `addCode` / `addition_symbol`**: `0` 교양 · `1` 실용 · `2` 여성 · `4` 청소년 · `5` 학습참고서(중고) · `6` 학습참고서(초등) · `7` 아동 · `9` 전문.
응답의 `addition_symbol`은 5자리 전체(`03830`, `74850`)로 온다. 위 코드는 그 첫 자리로 보인다(원문 주석의 추정).

**KDC 대주제 `kdc`**: `0` 총류 · `1` 철학 · `2` 종교 · `3` 사회과학 · `4` 자연과학 · `5` 기술과학 · `6` 예술 · `7` 언어 · `8` 문학 · `9` 역사. 세부주제 `dtl_kdc`(두 자리, 예 `81` 한국문학)는 원문 20.6에 있다.

## 값을 읽을 때 주의할 것

- **서명에 부제가 붙어 온다**: `아몬드 :손원평 장편소설`, `사피엔스 :유인원에서 사이보그까지, …`. ` :` 앞뒤를 서명과 부제로 나눌지 정해야 한다.
- **저자 표기가 두 꼴이다**
  - 이름표 꼴 `지은이: 히가시노 게이고 ;옮긴이: 양윤옥`: 기관 파일 해석기의 이름표 꼴로 읽는다.
  - 괄호 꼴 `정세랑 (지은이)`: `coLoanBooks`에서 보인다. 괄호 꼴 규칙으로 읽는다.
- XML의 문자열은 CDATA 안에 앞뒤 공백이 붙어 온다. trim해야 한다. JSON에서도 같은지는 확인이 필요하다.
- `description` 안의 `<`, `>`는 `&lt;`, `&gt;`로 이스케이프되어 온다.
- 값이 없으면 빈 요소(`<vol/>`)로 온다.
- `class_no`는 `813.7`처럼 소수점까지 온다. `class_nm`은 `문학 > 한국문학 > 소설`이다.
- 대출 건수 필드 이름이 API마다 다르다: 3·9·16번은 `loan_count`, 6·8번은 `loanCnt`.
- 4·5번 `recommandList`는 철자가 `recommand`이고, 목록 원소 이름이 `doc`이 아니라 `book`이다.

## 문서에 없는 것 (확인 필요)

- **일일 호출 한도**: 매뉴얼에 없다. 정보나루 마이페이지에서 확인한다.
- **이용약관**(데이터 저장, 재배포, 출처 표기): 매뉴얼에는 표지 조항만 있다. 사이트 약관을 확인한다.
- **시리즈**: 어느 API에도 시리즈 필드가 없다. 권(`vol`)만 있다.
- **정가**: 어느 API에도 없다. 카카오 `price`로 채운다.
- **JSON 응답의 구조**: 실제 호출로 확인한다.
