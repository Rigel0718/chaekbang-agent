"""도서관 정보나루 Open API 정의. 엔드포인트와 응답 필드는 여기에만 둔다.

근거: api-guides/data4library_project.md(매뉴얼 v20260620)와 실제 응답.
표지(`bookImageURL`)는 이용 제한(비영리 화면 표시만, 저장·재배포·AI 입력 금지) 때문에 읽지 않는다.
"""

from dataclasses import dataclass

SOURCE_NAME = "data4library"


@dataclass(frozen=True)
class Endpoint:
    path: str


BOOK_DETAIL = Endpoint("/srchDtlList")

# 이 API는 키를 쿼리 파라미터로만 받는다. 키가 든 URL은 출력·로그·오류에 남기지 않는다
API_KEY_PARAM = "authKey"
FORMAT_PARAM = "format"
FORMAT_JSON = "json"
ISBN_PARAM = "isbn13"
REQUEST_TIMEOUT_SECONDS = 10.0
MIN_CALL_INTERVAL_SECONDS = 0.5  # 한도가 문서에 없어 보수적으로 둔다

RESPONSE_KEY = "response"
ERROR_KEY = "error"
ERROR_CODE_KEY = "errCode"
# 찾지 못한 도서도 HTTP 200에 오류로 온다(확인 2026-11-16: "ISBN에 해당하는 도서가 없습니다.")
NOT_FOUND_ERROR_CODES = frozenset({"isbnMpngErr"})
DETAIL_KEY = "detail"
BOOK_KEY = "book"
# 오류 문구에 이 낱말이 있으면 그 사유로 본다. 그 밖의 오류는 외부 장애다
AUTH_ERROR_WORDS = ("인증", "authKey")
LIMIT_ERROR_WORDS = ("초과", "한도", "제한")


@dataclass(frozen=True)
class BookField:
    """응답 도서에서 값을 꺼낼 키와 저장할 수 있는 최대 길이."""

    key: str
    max_length: int | None = None


# 필드 이름은 Data4LibraryRecord의 필드 이름이다. max_length는 공식 서지의 열 길이와 같다.
BOOK_FIELDS = {
    "isbn13": BookField("isbn13"),
    "bookname": BookField("bookname"),
    "author": BookField("authors", 300),
    "publisher": BookField("publisher", 200),
    "published_date": BookField("publication_date"),
    "kdc": BookField("class_no", 20),
    "category": BookField("class_nm", 100),
    "addition_symbol": BookField("addition_symbol"),
    "volume": BookField("vol", 50),
    "description": BookField("description"),
}
TITLE_MAX_LENGTH = 500
SUBTITLE_MAX_LENGTH = 500
ADDITION_SYMBOL_LENGTH = 5

# --- 대출 신호 (`add-loan-signals`) ---
# 도서별 이용 분석(8번): 함께 대출된 책·마니아 추천·다독자 추천(최근 36개월, 최대 10권씩)
USAGE_ANALYSIS = Endpoint("/usageAnalysisList")
# 인기대출도서(3번): 전국 공공도서관, 연령·기간 조건
POPULAR_LOANS = Endpoint("/loanItemSrch")

USAGE_BOOK_KEY = "book"  # 기준 책
USAGE_LOAN_COUNT_KEY = "loanCnt"
CO_LOANS_KEY = "coLoanBooks"
MANIA_KEY = "maniaRecBooks"
READER_KEY = "readerRecBooks"
POPULAR_DOCS_KEY = "docs"
POPULAR_DOC_KEY = "doc"
POPULAR_LOAN_COUNT_KEY = "loan_count"
LIST_ISBN_KEY = "isbn13"

AGE_PARAM = "age"
START_PARAM = "startDt"
END_PARAM = "endDt"
PAGE_SIZE_PARAM = "pageSize"


@dataclass(frozen=True)
class AgeGroup:
    """인기대출도서의 연령 묶음. `age`가 None이면 연령 조건이 없다(전체)."""

    key: str
    age: str | None


# 어린이 조건은 나이를 나누지 않으므로 영유아·유아·초등을 한 번에 부른다
AGE_ALL = AgeGroup("all", None)
AGE_CHILDREN = AgeGroup("children", "0;6;8")
AGE_TEEN = AgeGroup("teen", "14")
AGE_ADULT = AgeGroup("adult", "20;30;40;50;60")
AGE_GROUPS = (AGE_ALL, AGE_CHILDREN, AGE_TEEN, AGE_ADULT)
