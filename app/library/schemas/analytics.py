"""분석 결과 스키마. 필드는 허용 목록 테스트(`tests/library/test_analytics_privacy.py`)가 고정한다.

회원 이름·회원번호·회원 id·기증자는 넣지 않는다. 필드를 더하면 허용 목록 테스트가 실패하므로, 그
필드가 개인정보가 아닌지 보고 목록에 넣는다.
"""

from datetime import datetime

from pydantic import BaseModel

from app.library.analytics.periods import Period
from app.library.models.catalog import HoldingStatus

TOP_N_DEFAULT = 10
TOP_N_MAX = 20
LIMIT_DEFAULT = 20
LIMIT_MAX = 50


class CountGroup(BaseModel):
    key: str
    label: str
    copies: int  # 사본 수(제적 제외)
    titles: int  # 서명 수(제적 아닌 사본이 있는 기관 도서)


class CollectionStatus(BaseModel):
    group_by: str | None
    copies: int
    titles: int
    withdrawn_copies: int  # 제적 사본. 위 수와 그룹에 들어가지 않는다
    groups: list[CountGroup]


class HoldingItem(BaseModel):
    library_book_id: int
    title: str
    author: str
    accession_number: str
    call_number: str | None
    status: HoldingStatus
    updated_at: datetime  # 사본의 마지막 수정 시각(상태가 바뀐 시각과 다를 수 있다)
    last_synced_at: datetime | None  # 외부 대출 기관: 마지막 가져오기 시각


class HoldingList(BaseModel):
    status: HoldingStatus
    total: int
    shown: int
    truncated: bool
    items: list[HoldingItem]


class LoanGroup(BaseModel):
    key: str
    label: str
    loans: int
    copies: int | None  # 분야로 묶을 때만: 지금 사본 수(제적 제외)
    loans_per_copy: float | None  # 분야로 묶을 때만: 대출 ÷ 사본, 소수 첫째 자리. 사본 0이면 null


class RankedBook(BaseModel):
    library_book_id: int
    title: str
    author: str
    loans: int
    in_collection: bool  # 제적 아닌 사본이 있으면 true


class BookRanking(BaseModel):
    total: int  # 기간에 한 번 이상 빌린 서명 수
    shown: int
    truncated: bool
    items: list[RankedBook]


class CurrentLoans(BaseModel):
    on_loan: int  # 지금 반납 안 된 대출
    overdue: int  # 그중 반납 예정일이 오늘보다 앞


class LoanStats(BaseModel):
    period: Period
    group_by: str | None
    loans: int
    groups: list[LoanGroup]
    ranking: BookRanking | None  # 책으로 묶을 때만
    current: CurrentLoans


class UnborrowedBook(BaseModel):
    library_book_id: int
    title: str
    author: str
    copies: int


class UnborrowedBooks(BaseModel):
    period: Period
    total: int
    shown: int
    truncated: bool
    items: list[UnborrowedBook]
