"""서명·저자 찾기와 자동완성. 이용자가 아는 책을 LLM 없이 찾는다.

찾을 수 있는 책은 추천 가능 조건과 같다(대출 가능이나 대출 중 사본). 어린이 구분으로 거르지 않는다.
이용자가 직접 찾는 책이고 추천이 아니기 때문이다. 비교는 DB가 계산해 둔 낱말 시작 키
(`title_jamo_starts`, `author_jamo_starts`. 규칙은 `app/core/text.py`의 `jamo_starts`)로 하고,
오타는 자모 편집 거리(`fuzzystrmatch`의 `levenshtein`)로 본다. 방식을 고른 근거는
`openspec/changes/add-catalog-search/design.md`의 2·3절에 있다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import (
    ColumnElement,
    Integer,
    Select,
    Text,
    case,
    func,
    literal,
    select,
    type_coerce,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core.errors import NotFoundError
from app.core.text import compact_sql, jamo, jamo_starts
from app.library.models.catalog import LibraryBook
from app.library.recommendation.search import LABEL, Candidate, _counts, get_candidates

FIND_LIMIT = 10
SUGGEST_LIMIT = 8
FOUND_LIMIT = 3
# 오타 점수의 문턱. 값은 검색 평가(`evals/catalog_search`)로 정한다.
FUZZY_THRESHOLD = 0.7
FOUND_THRESHOLD = 0.85  # 문장 속 서명은 더 엄격하게 본다
FUZZY_MIN_JAMO = 4  # 이보다 짧은 질의는 오타로 비교하지 않는다(한 음절은 잡음이 크다)
FOUND_MIN_TITLE = 2  # 문장 속 서명으로 볼 서명의 최소 글자 수(공백 제외)


class Stage:
    """찾기 결과의 맞은 방식. 작을수록 앞이다."""

    TITLE_EXACT = 1
    TITLE_PREFIX = 2
    TITLE_CONTAINS = 3
    AUTHOR_CONTAINS = 4
    FUZZY = 5


@dataclass(frozen=True)
class Found:
    candidate: Candidate
    stage: int
    score: float


@dataclass(frozen=True)
class Suggestion:
    library_book_id: int
    title: str
    author: str


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


Starts = ARRAY(Text)


def _starts(field: str) -> ColumnElement:
    """표시 값의 낱말 시작 키: 공식 서지 키를 먼저 쓴다(표시 값 `coalesce`와 같은 규칙)."""
    official = getattr(Book, f"{field}_jamo_starts")
    own = getattr(LibraryBook, f"{field}_jamo_starts")
    return type_coerce(func.coalesce(official, own, literal([], Starts)), Starts)


def _keyed(library_id: int, within: Select | None = None):
    """그 기관의 찾을 수 있는 책과 서명·저자의 낱말 시작 키."""
    counts = _counts(library_id)
    query = (
        select(
            LibraryBook.id.label("id"),
            func.coalesce(Book.title, LibraryBook.title).label("title"),
            func.coalesce(Book.author, LibraryBook.author).label("author"),
            _starts("title").label("title_starts"),
            _starts("author").label("author_starts"),
            (counts.c.available > 0).label("has_available"),
        )
        .join(counts, counts.c.library_book_id == LibraryBook.id)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id)
    )
    if within is not None:
        query = query.where(LibraryBook.id.in_(within))
    return query.subquery()


def _key(starts: ColumnElement) -> ColumnElement:
    """첫 낱말 시작 키가 공백 없는 자모 키(`jamo`)다."""
    return func.coalesce(type_coerce(starts, Starts)[1], "")


def _similarity(
    query: ColumnElement, target: ColumnElement, n: ColumnElement, threshold: float
) -> ColumnElement:
    """1 - (질의와 대상 앞부분 길이 n-1, n, n+1의 편집 거리 중 가장 작은 값) / n.

    문턱을 넘을 수 없는 거리에서는 계산을 멈춘다(`levenshtein_less_equal`). 이 함수는 상한을 넘으면
    "상한+1"을 돌려주므로, 그 값은 점수 0으로 본다. 상한은 부동소수 오차로 한 칸 작아지지 않게
    작은 여유를 더해 내림한다.
    """
    most = func.floor(n * (1 - threshold) + 1e-9).cast(Integer)
    distance = func.least(
        *(func.levenshtein_less_equal(query, func.left(target, n + d), most) for d in (-1, 0, 1))
    )
    return case((distance > most, 0.0), else_=1.0 - distance * 1.0 / n)


def _best(
    query: ColumnElement, starts: ColumnElement, n: ColumnElement, threshold: float
) -> ColumnElement:
    """낱말 시작 키마다 잰 유사도 중 가장 높은 값. 각 행에 붙는 부분 질의다."""
    each = func.unnest(starts).table_valued("s").render_derived()
    return (
        select(func.coalesce(func.max(_similarity(query, each.c.s, n, threshold)), 0.0))
        .select_from(each)
        .scalar_subquery()
    )


def _any_prefix(starts: ColumnElement, pattern: str) -> ColumnElement:
    each = func.unnest(starts).table_valued("s").render_derived()
    return select(each.c.s).select_from(each).where(each.c.s.like(pattern, escape="\\")).exists()


async def _with_candidates(
    session: AsyncSession, library_id: int, rows: Sequence[tuple[int, int, float]]
) -> list[Found]:
    candidates = await get_candidates(session, library_id, [r[0] for r in rows])
    return [Found(candidates[i], stage, score) for i, stage, score in rows if i in candidates]


async def find_books(
    session: AsyncSession, library_id: int, query: str, *, limit: int = FIND_LIMIT
) -> list[Found]:
    """서명·저자로 찾는다. 서명 전체, 서명 앞부분, 서명 포함, 저자 포함, 오타 유사 순이다."""
    q = jamo(query)
    if not q:
        return []
    limit = min(limit, FIND_LIMIT)
    books = _keyed(library_id)
    title, author = _key(books.c.title_starts), _key(books.c.author_starts)
    pattern = _like(q)
    stage = case(
        (title == q, Stage.TITLE_EXACT),
        (title.like(f"{pattern}%", escape="\\"), Stage.TITLE_PREFIX),
        (title.like(f"%{pattern}%", escape="\\"), Stage.TITLE_CONTAINS),
        (author.like(f"%{pattern}%", escape="\\"), Stage.AUTHOR_CONTAINS),
        else_=None,
    ).label("stage")
    exact = (
        select(books.c.id, stage, literal(1.0).label("score"))
        .where(stage.is_not(None))
        .order_by(stage, books.c.has_available.desc(), books.c.title, books.c.id)
        .limit(limit)
    )
    rows = [(i, s, sc) for i, s, sc in (await session.execute(exact)).all()]
    if len(rows) < limit and len(q) >= FUZZY_MIN_JAMO:
        n = literal(len(q))
        score = func.greatest(
            _best(literal(q), books.c.title_starts, n, FUZZY_THRESHOLD),
            _best(literal(q), books.c.author_starts, n, FUZZY_THRESHOLD),
        )
        scored = select(books.c.id, books.c.title, books.c.has_available, score.label("score"))
        if rows:
            scored = scored.where(books.c.id.not_in([r[0] for r in rows]))
        inner = scored.subquery()
        similar = (
            select(inner.c.id, literal(Stage.FUZZY), inner.c.score)
            .where(inner.c.score >= FUZZY_THRESHOLD)
            .order_by(inner.c.score.desc(), inner.c.has_available.desc(), inner.c.title, inner.c.id)
            .limit(limit - len(rows))
        )
        rows += [(i, s, sc) for i, s, sc in (await session.execute(similar)).all()]
    return await _with_candidates(session, library_id, rows)


async def suggest_books(
    session: AsyncSession, library_id: int, query: str, *, limit: int = SUGGEST_LIMIT
) -> list[Suggestion]:
    """자동완성: 서명 앞부분, 서명 낱말 앞부분, 저자(낱말) 앞부분 순이다. 오타는 보지 않는다."""
    q = jamo(query)
    if not q:
        return []
    books = _keyed(library_id)
    prefix = f"{_like(q)}%"
    stage = case(
        (_key(books.c.title_starts).like(prefix, escape="\\"), 1),
        (_any_prefix(books.c.title_starts, prefix), 2),
        (_any_prefix(books.c.author_starts, prefix), 3),
        else_=None,
    ).label("stage")
    rows = await session.execute(
        select(books.c.id, books.c.title, books.c.author)
        .where(stage.is_not(None))
        .order_by(stage, books.c.title, books.c.id)
        .limit(min(limit, SUGGEST_LIMIT))
    )
    return [Suggestion(i, t, a) for i, t, a in rows.all()]


async def get_findable(session: AsyncSession, library_id: int, library_book_id: int) -> Candidate:
    """고른 책 확인. 그 기관의 찾을 수 있는 책이 아니면 NotFoundError다."""
    candidate = (await get_candidates(session, library_id, [library_book_id])).get(library_book_id)
    if candidate is None or not candidate.recommendable:
        raise NotFoundError(f"{LABEL}를 찾을 수 없습니다")
    return candidate


async def found_in_text(
    session: AsyncSession, library_id: int, text: str, *, limit: int = FOUND_LIMIT
) -> list[Candidate]:
    """문장 속 서명. 서명 전체가 문장에 들어 있거나, 한 글자 안팎의 차이로 들어 있는 책."""
    message, message_starts = jamo(text), jamo_starts(text)
    if not message:
        return []
    books = _keyed(library_id)
    title = _key(books.c.title_starts)
    long_enough = func.char_length(compact_sql(books.c.title)) >= FOUND_MIN_TITLE
    order = (func.char_length(title).desc(), books.c.title, books.c.id)
    contained = (
        select(books.c.id)
        .where(long_enough, func.strpos(literal(message), title) > 0)
        .order_by(*order)
        .limit(limit)
    )
    ids = list(await session.scalars(contained))
    if not ids:
        n = func.char_length(title)
        score = _best(title, literal(message_starts, Starts), n, FOUND_THRESHOLD)
        scored = select(books.c.id, books.c.title, title.label("key"), score.label("score")).where(
            long_enough, func.char_length(title) >= FUZZY_MIN_JAMO
        )
        inner = scored.subquery()
        similar = (
            select(inner.c.id)
            .where(inner.c.score >= FOUND_THRESHOLD)
            .order_by(func.char_length(inner.c.key).desc(), inner.c.title, inner.c.id)
            .limit(limit)
        )
        ids = list(await session.scalars(similar))
    candidates = await get_candidates(session, library_id, ids)
    return [candidates[i] for i in ids if i in candidates]
