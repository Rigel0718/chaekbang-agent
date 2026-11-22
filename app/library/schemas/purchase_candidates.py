"""구매 후보 응답. REST(`GET /purchase-requests/candidates`)와 운영 에이전트 tool이 함께 쓴다.

필드는 허용 목록이다(`tests/library/test_purchase_candidates.py`가 고정한다): 회원 값과 가격은
어디에도 없다. 희망도서는 ISBN별로 묶어 신청 건수만 낸다.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.library.analytics.periods import Period


class PopularBasis(StrEnum):
    LOAN_COUNT = "loan_count"  # 자체 대출 기관: 기간 대출 수 순위
    IMPORTED_STATUS = "imported_status"  # 외부 대출 기관: 가져온 파일의 대출 중 상태


class WishCandidate(BaseModel):
    isbn: str
    title: str
    author: str | None
    request_count: int  # 같은 ISBN의 처리 전 신청 건수


class LoanPopular(BaseModel):
    """자체 대출 기관의 인기 후보. 기간의 대출 수와 지금 사본 수·대출 중 수."""

    isbn: str
    title: str
    author: str | None
    loans: int
    copies: int  # 제적을 뺀 사본 수
    on_loan: int


class ImportedPopular(BaseModel):
    """외부 대출 기관의 인기 후보. 기간 대출 수는 없고 마지막으로 가져온 파일 기준 상태다."""

    isbn: str
    title: str
    author: str | None
    copies: int
    on_loan: int
    synced_at: datetime | None  # 그 책 사본의 가장 늦은 가져오기 시각


class FieldFigure(BaseModel):
    """분야별 숫자. 책은 없고 숫자만이다(살 책은 관리자가 ISBN으로 넣는다)."""

    field: str
    titles: int
    copies: int
    loans: int | None  # 자체 대출 기관만
    loans_per_copy: float | None


class PurchaseCandidates(BaseModel):
    basis: PopularBasis
    period: Period | None  # 자체 대출 기관만
    wishes: list[WishCandidate]
    wishes_without_isbn: int
    popular: list[LoanPopular] | list[ImportedPopular]
    fields: list[FieldFigure]
