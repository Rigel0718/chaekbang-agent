"""운영 에이전트 대화 요청과 답 사건의 스키마."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.library.admin_agent import Unsupported
from app.library.schemas.librarian import MAX_MESSAGE_LENGTH


class AdminMessageRequest(BaseModel):
    """기관은 토큰으로 정한다. 정의되지 않은 값(library_id 등)은 받지 않는다."""

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class AdminAnswerPayload(BaseModel):
    message: str
    unsupported: Unsupported | None
