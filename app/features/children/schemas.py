from pydantic import BaseModel

from app.features.children.models import Audience, AudienceSource


class AudienceRead(BaseModel):
    library_book_id: int
    audience: Audience
    audience_source: AudienceSource


class AudienceUpdate(BaseModel):
    audience: Audience


class RefreshResult(BaseModel):
    updated: int  # 어린이 구분이 바뀐 건수
