"""AI 사서 대화 요청과 답 사건의 스키마. 카드는 코드가 DB 값으로 만든다."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.library.models.library import LoanMode

MAX_MESSAGE_LENGTH = 500


class MessageRequest(BaseModel):
    """기관은 토큰으로 정한다. 정의되지 않은 값(library_id 등)은 받지 않는다."""

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class BookCard(BaseModel):
    library_book_id: int
    title: str
    author: str
    publisher: str | None
    available_count: int
    on_loan_count: int
    shelf_location: str | None
    call_number: str | None
    reason: str  # LLM이 쓴 추천 이유
    cover_url: str | None  # 원본 URL. 저장하지 않는다
    cover_source: str | None  # 표지 출처
    product_url: str | None  # 출처의 상품 링크
    status_synced_at: datetime | None  # 가져오기 기관의 대출 상태 갱신 시각


class AnswerPayload(BaseModel):
    message: str
    recommendations: list[BookCard]
    suggest_book_request: bool
    loan_mode: LoanMode
