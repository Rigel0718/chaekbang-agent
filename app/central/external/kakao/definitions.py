"""카카오 책 검색 API 정의. 엔드포인트와 응답 필드는 여기에만 둔다.

근거: api-guides/kakao_search_api_guide.md와 실제 응답.
판매가(`sale_price`)와 판매 상태(`status`)는 변동 값이라 읽지 않고 원본 파일에도 넣지 않는다.
"""

from dataclasses import dataclass

SOURCE_NAME = "kakao"


@dataclass(frozen=True)
class Endpoint:
    path: str


BOOK_SEARCH = Endpoint("/v3/search/book")

API_KEY_HEADER = "Authorization"
API_KEY_PREFIX = "KakaoAK "
QUERY_PARAM = "query"
TARGET_PARAM = "target"
TARGET_ISBN = "isbn"
REQUEST_TIMEOUT_SECONDS = 10.0
MIN_CALL_INTERVAL_SECONDS = 0.2

DOCUMENTS_KEY = "documents"
ISBN_KEY = "isbn"  # "ISBN10 ISBN13"처럼 공백으로 이어 온다
AUTHORS_KEY = "authors"
TRANSLATORS_KEY = "translators"
ISBN13_LENGTH = 13
# 저장하지 않는 변동 값. 원본 파일에도 넣지 않는다
VOLATILE_DOCUMENT_KEYS = ("sale_price", "status")

# 배열을 저자 원문 하나로 잇는 꼴. 기관 파일 해석기가 다시 읽는다
NAME_SEPARATOR = ", "
TRANSLATOR_LABEL = " ;옮긴이: "
AUTHOR_MAX_LENGTH = 300


@dataclass(frozen=True)
class DocumentField:
    """응답 문서에서 값을 꺼낼 키와 저장할 수 있는 최대 길이."""

    key: str
    max_length: int | None = None


# 필드 이름은 KakaoRecord의 필드 이름이다. max_length는 공식 서지의 열 길이와 같다.
DOCUMENT_FIELDS = {
    "title": DocumentField("title", 500),
    "publisher": DocumentField("publisher", 200),
    "published_date": DocumentField("datetime"),
    "list_price": DocumentField("price"),
    "description": DocumentField("contents"),
    "cover_url": DocumentField("thumbnail", 1000),
    "url": DocumentField("url", 1000),
}
