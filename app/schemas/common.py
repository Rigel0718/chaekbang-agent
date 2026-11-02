from typing import Annotated, Any, ClassVar, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.matching.isbn import normalize_isbn

# 하이픈·공백을 받아 13자리로 정규화하고 체크 디지트를 검증한다.
Isbn = Annotated[str, AfterValidator(normalize_isbn)]

# 원 단위 금액. float를 받지 않는다.
Won = Annotated[int, Field(ge=0, strict=True)]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Pagination(BaseModel):
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatchModel(BaseModel):
    """부분 수정 요청. NOT_NULL_FIELDS에 든 필드는 생략은 되지만 null로 보낼 수는 없다."""

    NOT_NULL_FIELDS: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _reject_nulls(self) -> Self:
        for name in self.NOT_NULL_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}은(는) null일 수 없습니다")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)
