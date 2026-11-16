"""출처 중립의 공식 서지 값과, 세 출처(정보나루·카카오·YES24)를 필드별 기준 출처로 합치는 규칙.

공식 서지를 만드는 모든 경로가 `OfficialValues`를 `create_official`에 넘긴다. 채움과 실험 장서
적재는 `merge`로, 평가 표본처럼 YES24 응답 하나만 쓰는 경로는 `from_yes24`로 만든다.

기준 출처(design 결정 3). 앞의 출처에 값이 없으면 다음 출처를 본다.
- 서명·부제·저자: YES24 → 정보나루 → 카카오. 셋은 한 출처에서만 가져온다(섞지 않는다).
  정보나루 서명은 권차를 빼고 대등 서명을 붙여 와 정리 규칙을 거친다(`split_title`).
- 출판사: 정보나루 → YES24 → 카카오.
- 소개: YES24 → 정보나루 → 카카오(카카오는 약 250자에서 잘려 온다).
- 목차, 시리즈, 분류 원문: YES24.
- KDC, KDC 분류명, 부가기호, 권: 정보나루.
- 출간일: 카카오 → YES24 → 정보나루(정보나루는 날짜까지 있을 때만).
- 정가: 카카오 → YES24.
- 표지 URL과 상품 링크: YES24 → 카카오. 둘은 한 출처에서 가져온다(정보나루 표지는 쓰지 않는다).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.central.external.data4library.parsing import Data4LibraryRecord
from app.central.external.kakao.parsing import KakaoRecord
from app.central.external.yes24.parsing import Yes24Item
from app.central.models import ExternalSource


class LookupOutcome(StrEnum):
    """공식 서지를 만들지 못한 이유."""

    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class OfficialValues:
    """공식 서지 하나의 값. `source`는 서명·저자의 출처다."""

    title: str
    author: str
    source: ExternalSource
    publisher: str | None = None
    published_date: date | None = None
    list_price: int | None = None
    description: str | None = None
    subtitle: str | None = None
    table_of_contents: str | None = None
    kdc: str | None = None
    kdc_name: str | None = None  # KDC 분류명 원문(`문학 > 한국문학 > 소설`)
    category: str | None = None  # 분류 원문(YES24 관리 분류)
    addition_symbol: str | None = None
    volume: str | None = None
    cover_url: str | None = None
    url: str | None = None
    series_name: str | None = None  # 표시용
    series_names: tuple[str, ...] = ()  # 시리즈 키는 이 목록으로 만든다
    # 값이 있는 필드(서명·저자 빼고)마다 출처. 열 이름을 키로 쓴다
    field_sources: dict[str, str] = field(default_factory=dict)


def from_yes24(item: Yes24Item) -> OfficialValues | None:
    """YES24 상품의 값. 서명·저자가 없으면 None이다. 필드별 출처는 남기지 않는다(모두 YES24)."""
    if not item.title or not item.author:
        return None
    return OfficialValues(
        title=item.title,
        author=item.author,
        source=ExternalSource.YES24,
        publisher=item.publisher,
        published_date=item.published_date,
        list_price=item.list_price,
        description=item.description,
        subtitle=item.subtitle,
        table_of_contents=item.table_of_contents,
        category=item.category,
        cover_url=item.cover_url,
        url=item.url,
        series_name=item.series_name,
        series_names=item.series_names,
    )


def _same_isbn[T: (Data4LibraryRecord, KakaoRecord, Yes24Item)](
    isbn: str, records: Sequence[T]
) -> T | None:
    return next((record for record in records if record.isbn13 == isbn), None)


D4L, KAKAO, YES24 = ExternalSource.DATA4LIBRARY, ExternalSource.KAKAO, ExternalSource.YES24


def merge(
    isbn: str,
    d4l_records: Sequence[Data4LibraryRecord] = (),
    kakao_records: Sequence[KakaoRecord] = (),
    yes24_records: Sequence[Yes24Item] = (),
) -> OfficialValues | LookupOutcome:
    """한 ISBN의 세 출처 결과를 합친다. 만들 수 없으면 그 이유를 돌려준다.

    요청한 ISBN과 같은 ISBN13의 결과만 쓴다. 같은 ISBN의 결과가 어느 출처에도 없는데 다른 ISBN의
    결과가 왔으면 `MISMATCH`, 그 밖에 서명·저자를 얻지 못하면 `NOT_FOUND`다.
    """
    d4l = _same_isbn(isbn, d4l_records)
    kakao = _same_isbn(isbn, kakao_records)
    yes24 = _same_isbn(isbn, yes24_records)
    if d4l is None and kakao is None and yes24 is None:
        answered = bool(d4l_records) or bool(kakao_records) or bool(yes24_records)
        return LookupOutcome.MISMATCH if answered else LookupOutcome.NOT_FOUND

    # 서명·부제·저자는 한 출처에서만 가져온다
    heads: list[tuple[str | None, str | None, str | None, ExternalSource]] = []
    if yes24 is not None:
        heads.append((yes24.title, yes24.subtitle, yes24.author, YES24))
    if d4l is not None:
        heads.append((d4l.title, d4l.subtitle, d4l.author, D4L))
    if kakao is not None:
        heads.append((kakao.title, None, kakao.author, KAKAO))
    head = next(((t, st, a, src) for t, st, a, src in heads if t and a), None)
    if head is None:
        return LookupOutcome.NOT_FOUND
    title, subtitle, author, source = head

    picked: dict[str, tuple[object, ExternalSource]] = {}

    def pick(name: str, *candidates: tuple[object, ExternalSource]) -> None:
        for value, origin in candidates:
            if value is not None:
                picked[name] = (value, origin)
                return

    def of(record, attr: str, origin: ExternalSource) -> tuple[object, ExternalSource]:  # noqa: ANN001
        return (getattr(record, attr) if record is not None else None, origin)

    if subtitle is not None:
        picked["subtitle"] = (subtitle, source)
    pick(
        "publisher",
        of(d4l, "publisher", D4L),
        of(yes24, "publisher", YES24),
        of(kakao, "publisher", KAKAO),
    )
    pick(
        "description",
        of(yes24, "description", YES24),
        of(d4l, "description", D4L),
        of(kakao, "description", KAKAO),
    )
    pick("table_of_contents", of(yes24, "table_of_contents", YES24))
    pick("series_name", of(yes24, "series_name", YES24))
    pick("external_category", of(yes24, "category", YES24))
    pick("kdc", of(d4l, "kdc", D4L))
    pick("kdc_name", of(d4l, "category", D4L))
    pick("addition_symbol", of(d4l, "addition_symbol", D4L))
    pick("volume", of(d4l, "volume", D4L))
    pick(
        "published_date",
        of(kakao, "published_date", KAKAO),
        of(yes24, "published_date", YES24),
        of(d4l, "published_date", D4L),
    )
    pick("list_price", of(kakao, "list_price", KAKAO), of(yes24, "list_price", YES24))
    # 표지와 상품 링크는 한 출처에서 가져온다(출처 표시가 표지와 링크를 함께 보여 준다)
    for record, origin in ((yes24, YES24), (kakao, KAKAO)):
        if record is not None and (record.cover_url or record.url):
            pick("cover_url", (record.cover_url, origin))
            pick("external_url", (record.url, origin))
            break

    def value(name: str):  # noqa: ANN202 - 필드마다 타입이 다르다
        return picked[name][0] if name in picked else None

    return OfficialValues(
        title=title,
        author=author,
        source=source,
        publisher=value("publisher"),
        published_date=value("published_date"),
        list_price=value("list_price"),
        description=value("description"),
        subtitle=value("subtitle"),
        table_of_contents=value("table_of_contents"),
        kdc=value("kdc"),
        kdc_name=value("kdc_name"),
        category=value("external_category"),
        addition_symbol=value("addition_symbol"),
        volume=value("volume"),
        cover_url=value("cover_url"),
        url=value("external_url"),
        series_name=value("series_name"),
        series_names=yes24.series_names if "series_name" in picked and yes24 else (),
        field_sources={name: origin.value for name, (_, origin) in sorted(picked.items())},
    )
