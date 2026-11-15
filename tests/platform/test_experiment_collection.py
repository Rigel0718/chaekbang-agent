"""[platform/experiment-collection] 실험 장서 적재.

테스트 안에서 만든 작은 문서(지어낸 서지)로 돈다. 저장소에 YES24 값을 넣지 않는다.

[catalog/books] 공식 서지 쓰기 제한 / 두 경로의 같은 결과도 여기서 확인한다.
"""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.contributors import author_keys
from app.seed.experiment import (
    LIBRARY_NAME,
    Collection,
    layout,
    seed_experiment,
)
from scripts import seed_experiment as script
from tests.conftest import Tenant
from tests.helpers import add_book, add_held_book, add_holding, add_loan, add_member, make_isbn
from tests.yes24_helpers import FakeYes24, enrich, item, ok

SHELVES = {"toddler": "유아 자료실", "children": "어린이 자료실", "general": "일반 자료실"}
TABLES = (
    "libraries",
    "staff_users",
    "books",
    "book_contributors",
    "library_books",
    "library_book_audiences",
    "holdings",
    "members",
    "loans",
)


def _rows(count: int, start: int = 100, overrides: dict[int, dict] | None = None) -> list[dict]:
    """ISBN 순서가 i와 같은 책 count권. overrides는 {i: {필드: 값}}."""
    rows = []
    for i in range(count):
        isbn = make_isbn(start + i)
        values = {
            "title": f"실험 책 {i}",
            "author": f"작가{i} 지음",
            "goodsSortNm": "국내도서-인문",
            "series": [],
            **(overrides or {}).get(i, {}),
        }
        field = values.pop("field", "general")
        rows.append({"field": field, "rank": i + 1, "item": item(isbn, **values)})
    return rows


def _collection(rows: list[dict]) -> Collection:
    return Collection("2026-11-15", SHELVES, rows)


async def _seed(session: AsyncSession, rows: list[dict]) -> dict:
    return await seed_experiment(session, _collection(rows), "admin-password", "kiosk-password")


async def _library_id(session: AsyncSession) -> int:
    return await session.scalar(
        text("SELECT id FROM libraries WHERE name = :n"), {"n": LIBRARY_NAME}
    )


async def _library_books(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            "SELECT lb.*, b.id AS official_id FROM library_books lb"
            " LEFT JOIN books b ON b.id = lb.book_id"
            " WHERE lb.library_id = :l ORDER BY lb.id"
        ),
        {"l": await _library_id(session)},
    )
    return list(result.mappings())


async def _counts(session: AsyncSession) -> dict[str, int]:
    return {t: await session.scalar(text(f"SELECT count(*) FROM {t}")) for t in TABLES}


async def test_load_into_empty_db(session: AsyncSession) -> None:
    """[platform/experiment-collection] 공식 서지와 가상 기관으로 적재 / 빈 DB에 적재"""
    await _seed(session, _rows(10))
    libraries = await session.scalar(
        text("SELECT count(*) FROM libraries WHERE name = :n"), {"n": LIBRARY_NAME}
    )
    staff = (
        await session.execute(
            text("SELECT login_id, role FROM staff_users WHERE library_id = :l ORDER BY login_id"),
            {"l": await _library_id(session)},
        )
    ).all()
    assert libraries == 1
    assert [tuple(r) for r in staff] == [
        ("experiment-admin", "admin"),
        ("experiment-kiosk", "kiosk"),
    ]
    library = (
        await session.execute(
            text("SELECT loan_mode, type FROM libraries WHERE name = :n"), {"n": LIBRARY_NAME}
        )
    ).one()
    assert tuple(library) == ("internal", "small_library")
    books = await _library_books(session)
    assert len(books) == 10
    without_isbn = [i for i in range(10) if not layout(i).with_isbn]
    assert without_isbn == [3]
    for i, row in enumerate(books):
        assert (row["official_id"] is None) == (i in without_isbn)
        assert row["kdc"] is None
    calls = await session.scalar(
        text("SELECT count(*) FROM holdings WHERE library_id = :l AND call_number IS NOT NULL"),
        {"l": await _library_id(session)},
    )
    assert calls == 0


async def test_contributors_and_series_keys(session: AsyncSession) -> None:
    """[platform/experiment-collection] 공식 서지와 가상 기관으로 적재 / 기여자와 시리즈 키"""
    series = [{"seriesName": "민들레그림책"}, {"seriesName": "읽고, 쓰고"}]
    await _seed(
        session,
        _rows(1, overrides={0: {"author": "칼 멜링 글/브라이트 스타 그림", "series": series}}),
    )
    book = (
        (await session.execute(text("SELECT id, series_keys, series_name FROM books")))
        .mappings()
        .one()
    )
    roles = (
        await session.execute(
            text("SELECT name, role FROM book_contributors WHERE book_id = :b ORDER BY position"),
            {"b": book["id"]},
        )
    ).all()
    assert [tuple(r) for r in roles] == [("칼 멜링", "author"), ("브라이트 스타", "illustrator")]
    assert book["series_keys"] == ["민들레그림책", "읽고쓰고"]
    assert book["series_name"] == "민들레그림책, 읽고, 쓰고"


async def test_existing_official_kept(session: AsyncSession) -> None:
    """[platform/experiment-collection] 공식 서지와 가상 기관으로 적재 / 이미 있는 공식 서지"""
    existing = await add_book(session, make_isbn(100), title="원래 있던 서명")
    await _seed(session, _rows(2))
    first = (await _library_books(session))[0]
    assert first["book_id"] == existing["id"]
    title = await session.scalar(
        text("SELECT title FROM books WHERE id = :b"), {"b": existing["id"]}
    )
    assert title == "원래 있던 서명"


async def test_layout_mix(session: AsyncSession) -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 / 상태 구성"""
    await _seed(session, _rows(40))
    result = await session.execute(
        text(
            "SELECT lb.id, lb.isbn, lb.book_id,"
            " array_agg(h.status::text ORDER BY h.accession_number) AS statuses"
            " FROM library_books lb JOIN holdings h ON h.library_book_id = lb.id"
            " WHERE lb.library_id = :l GROUP BY lb.id ORDER BY lb.id"
        ),
        {"l": await _library_id(session)},
    )
    rows = list(result.mappings())
    shapes = [r["statuses"] for r in rows]
    assert ["available", "on_loan"] in shapes
    assert ["on_loan"] in shapes
    assert ["lost"] in shapes
    assert ["withdrawn"] in shapes
    assert any(r["isbn"] is None and r["book_id"] is None for r in rows)
    assert len(rows) == 40


async def test_layout_is_deterministic() -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 (ISBN 순서로 정하고 난수 없음)"""
    first = [layout(i) for i in range(200)]
    assert first == [layout(i) for i in range(200)]
    assert sum(not shape.with_isbn for shape in first) == 20  # 10%


async def test_book_without_isbn_values(session: AsyncSession) -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 / ISBN 없는 책의 값"""
    author = "작가삼 글/화가삼 그림"
    await _seed(session, _rows(4, overrides={3: {"author": author}}))
    row = (await _library_books(session))[3]
    assert (row["isbn"], row["book_id"]) == (None, None)
    assert (row["title"], row["author"]) == ("실험 책 3", author)
    assert row["description"] == "강아지똥이 민들레 꽃을 피워 내는 이야기"
    assert row["author_keys"] == author_keys(author)
    assert row["author_keys"] == ["작가삼"]
    acquisition = await session.scalar(
        text("SELECT acquisition_type FROM holdings WHERE library_book_id = :b"), {"b": row["id"]}
    )
    assert acquisition == "donated"


async def test_purchase_price_from_list_price(session: AsyncSession) -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 (매입 사본의 구입가 = 정가의 90%)"""
    await _seed(session, _rows(2, overrides={1: {"shopPrice": 13999}}))
    second = (await _library_books(session))[1]
    row = (
        await session.execute(
            text(
                "SELECT acquisition_type, purchase_price FROM holdings WHERE library_book_id = :b"
            ),
            {"b": second["id"]},
        )
    ).one()
    assert tuple(row) == ("purchased", 12599)


async def _children(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        text(
            "SELECT lb.title, a.audience_source FROM library_book_audiences a"
            " JOIN library_books lb ON lb.id = a.library_book_id"
            " WHERE a.library_id = :l AND a.audience = 'children'"
        ),
        {"l": await _library_id(session)},
    )
    return {title: source for title, source in result}


async def test_children_from_category(session: AsyncSession) -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 / 어린이 구분"""
    await _seed(
        session,
        _rows(
            3,
            overrides={
                1: {"goodsSortNm": "국내도서-유아", "field": "toddler"},
                2: {"goodsSortNm": "국내도서-인문"},
            },
        ),
    )
    assert await _children(session) == {"실험 책 1": "external_category"}


async def test_children_without_isbn_from_shelf(session: AsyncSession) -> None:
    """[platform/experiment-collection] 실제 장서를 닮은 구성 / ISBN 없는 어린이 책"""
    await _seed(
        session, _rows(4, overrides={3: {"goodsSortNm": "국내도서-유아", "field": "toddler"}})
    )
    assert await _children(session) == {"실험 책 3": "import_label"}
    shelf = await session.scalar(
        text(
            "SELECT h.shelf_location FROM holdings h JOIN library_books lb"
            " ON lb.id = h.library_book_id WHERE lb.title = '실험 책 3'"
        )
    )
    assert shelf == "유아 자료실"


async def test_run_twice(session: AsyncSession) -> None:
    """[platform/experiment-collection] 반복 실행과 다른 데이터 보호 / 두 번 실행"""
    rows = _rows(20)
    first_report = await _seed(session, rows)
    first = await _counts(session)
    statuses = "SELECT accession_number, status FROM holdings WHERE library_id = :l ORDER BY 1"
    library_id = await _library_id(session)
    before = (await session.execute(text(statuses), {"l": library_id})).all()
    second_report = await _seed(session, rows)
    assert await _counts(session) == first
    assert (await session.execute(text(statuses), {"l": library_id})).all() == before
    assert all(created == 0 for created, _ in second_report.values())
    assert first_report["library_books"] == (20, 0)


async def test_other_libraries_untouched(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/experiment-collection] 반복 실행과 다른 데이터 보호 / 다른 기관은 그대로"""
    shared_isbn = make_isbn(100)  # 실험 장서의 첫 책과 같은 ISBN을 시드 기관도 가진다
    held = await add_held_book(session, library_a.id, isbn=shared_isbn, title="A의 책")
    holding = await add_holding(session, library_a.id, held["id"], "A-0001")
    member = await add_member(session, library_a.id, "M-1")
    await add_loan(session, holding, member)
    await add_held_book(session, library_b.id, title="B의 책")
    query = (
        "SELECT (SELECT count(*) FROM library_books WHERE library_id = :l),"
        " (SELECT count(*) FROM holdings WHERE library_id = :l),"
        " (SELECT count(*) FROM members WHERE library_id = :l),"
        " (SELECT count(*) FROM loans WHERE library_id = :l),"
        " (SELECT string_agg(title || coalesce(book_id::text, '-'), ',') FROM library_books"
        "  WHERE library_id = :l)"
    )
    before = {
        t.id: tuple((await session.execute(text(query), {"l": t.id})).one())
        for t in (library_a, library_b)
    }
    await _seed(session, _rows(10))
    after = {
        t.id: tuple((await session.execute(text(query), {"l": t.id})).one())
        for t in (library_a, library_b)
    }
    assert after == before


async def test_missing_file(
    session: AsyncSession, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 반복 실행과 다른 데이터 보호 / 파일 없음"""
    before = await _counts(session)
    assert await script.execute(session, tmp_path / "없음.json") == script.EXIT_PRECONDITION
    assert "evals.collection.fetch" in capsys.readouterr().err
    assert await _counts(session) == before


async def test_script_run(
    session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """[platform/experiment-collection] 공식 서지와 가상 기관으로 적재 (명령줄 출력)"""
    settings = get_settings()
    monkeypatch.setattr(settings, "seed_admin_password", "admin-password")
    monkeypatch.setattr(settings, "seed_kiosk_password", "kiosk-password")
    path = tmp_path / "collection.json"
    path.write_text(
        json.dumps({"fetched_on": "2026-11-15", "books": _rows(5)}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert await script.execute(session, path) == script.EXIT_OK
    out = capsys.readouterr().out
    assert "받은 날 2026-11-15, 파일의 책 5권" in out
    assert "library_books: 생성 5건, 건너뜀 0건" in out
    assert "books: 생성 4건, 건너뜀 0건" in out


async def test_two_paths_same_official(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/books] 공식 서지 쓰기 제한 / 두 경로의 같은 결과"""
    values = {
        "title": "같은 응답",
        "author": "앤디 위어 저/박아람 역",
        "subTitle": "부제",
        "series": [{"seriesName": "우주 소설"}, {"seriesName": "읽고, 쓰고"}],
        "goodsSortNm": "국내도서-소설/시/희곡",
    }
    enriched_isbn, loaded_isbn = make_isbn(150), make_isbn(151)
    await add_held_book(session, library_a.id, isbn=enriched_isbn, title="기관 서명")
    yes24 = FakeYes24()
    yes24.responses[enriched_isbn] = ok(item(enriched_isbn, **values))
    await enrich(session, yes24.client())
    await seed_experiment(
        session,
        _collection([{"field": "general", "rank": 1, "item": item(loaded_isbn, **values)}]),
        "admin-password",
        "kiosk-password",
    )

    async def snapshot(isbn: str):
        book = (
            await session.execute(
                text(
                    "SELECT to_jsonb(b) - 'id' - 'isbn' - 'created_at' - 'updated_at' AS v"
                    " FROM books b WHERE isbn = :i"
                ),
                {"i": isbn},
            )
        ).scalar_one()
        contributors = (
            await session.execute(
                text(
                    "SELECT position, name, name_key, role, role_text FROM book_contributors c"
                    " JOIN books b ON b.id = c.book_id WHERE b.isbn = :i ORDER BY position"
                ),
                {"i": isbn},
            )
        ).all()
        return book, [tuple(c) for c in contributors]

    enriched, loaded = await snapshot(enriched_isbn), await snapshot(loaded_isbn)
    assert enriched == loaded
    assert enriched[0]["series_keys"] == ["우주소설", "읽고쓰고"]
    assert len(enriched[1]) == 2
