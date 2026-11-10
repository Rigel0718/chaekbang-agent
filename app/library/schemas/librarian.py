"""AI 사서 대화 요청과 답 사건의 스키마. 카드는 코드가 DB 값으로 만든다."""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.library.models.library import LoanMode
from app.library.schemas.catalog import BookSummary

MAX_MESSAGE_LENGTH = 500


class MessageRequest(BaseModel):
    """기관은 토큰으로 정한다. 정의되지 않은 값(library_id 등)은 받지 않는다.

    문장과 고른 책(자동완성에서 고른 기관 도서) 중 하나 이상이 있어야 한다. 고른 책만 보내면 LLM을
    부르지 않고 그 책의 카드만 보낸다.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID | None = None
    message: str | None = Field(default=None, min_length=1, max_length=MAX_MESSAGE_LENGTH)
    selected_library_book_id: int | None = None

    @model_validator(mode="after")
    def _message_or_selected(self) -> Self:
        if self.message is None and self.selected_library_book_id is None:
            raise ValueError("message나 selected_library_book_id가 있어야 합니다")
        return self


class BookCard(BookSummary):
    reason: str  # LLM이 쓴 추천 이유


class AnswerPayload(BaseModel):
    message: str
    recommendations: list[BookCard]
    suggest_book_request: bool
    loan_mode: LoanMode
