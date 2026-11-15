"""[platform/experiment-collection] 실험 장서 받기. 가짜 YES24(`httpx.MockTransport`)로 돈다."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.central.external.yes24.category import steady_sellers
from app.central.external.yes24.client import StopReason, Yes24Stopped
from evals.collection import fetch as fetch_module
from evals.collection.fetch import (
    EXIT_OK,
    EXIT_PRECONDITION,
    EXIT_STOPPED,
    SkipReason,
    collect,
    expected_calls,
    fetch,
)
from evals.collection.plan import FIELDS, Field
from tests.helpers import make_isbn
from tests.yes24_helpers import error, item, make_client

_numbers = iter(range(400, 1000))


def book(n: int | None = None, **overrides) -> dict:
    isbn = make_isbn(n if n is not None else next(_numbers))
    return item(isbn, title=f"책 {isbn}", **overrides)


def page(*items: dict, total: int | None = None) -> httpx.Response:
    data = {
        "items": list(items),
        "currentPage": 1,
        "pageSize": 100,
        "totalCount": len(items) if total is None else total,
    }
    return httpx.Response(200, json={"success": True, "message": "성공", "data": data})


class FakeCategories:
    """카테고리 id와 쪽 번호마다 응답을 정해 두고 호출을 기록한다."""

    def __init__(self, pages: dict[tuple[str, int], httpx.Response | Callable]) -> None:
        self.pages = pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.url.params["categoryId"], int(request.url.params["page"]))
        response = self.pages.get(key, page())
        return response() if callable(response) else response

    def client(self):
        return make_client(self)


def _plan(*targets: int) -> tuple[Field, ...]:
    return tuple(Field(f"f{i}", f"분야{i}", f"00100100{i}", t) for i, t in enumerate(targets))


async def test_request_parameters() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 (요청 파라미터)"""
    fake = FakeCategories({("001001027", 2): page(book(), total=150)})
    items, total = await steady_sellers(fake.client(), "001001027", page=2)
    assert (len(items), total) == (1, 150)
    request = fake.requests[0]
    assert request.url.path.endswith("/category/bestsellerSteady")
    assert dict(request.url.params) == {
        "categoryId": "001001027",
        "page": "2",
        "pageSize": "100",
        "detail": "Y",
    }


async def test_empty_and_not_found_results() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 (빈 결과)"""
    fake = FakeCategories({("1", 1): page(), ("2", 1): error(404, "BEST_001")})
    assert await steady_sellers(fake.client(), "1") == ([], 0)
    assert await steady_sellers(fake.client(), "2") == ([], 0)


async def test_upstream_failure_stops() -> None:
    """[platform/experiment-collection] 한 번만 받기 (외부 장애)"""
    fake = FakeCategories({("1", 1): error(500)})
    with pytest.raises(Yes24Stopped) as caught:
        await steady_sellers(fake.client(), "1")
    assert caught.value.reason is StopReason.UPSTREAM_UNAVAILABLE


async def test_cut_at_target() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 / 목표 권수에서 자름"""
    items = [book() for _ in range(5)]
    fake = FakeCategories({("001001000", 1): page(*items)})
    records, books = await collect(fake.client(), _plan(3))
    assert [b["item"]["isbn13"] for b in books] == [i["isbn13"] for i in items[:3]]
    assert [b["rank"] for b in books] == [1, 2, 3]
    assert records[0].fetched == 3


async def test_non_books_are_skipped() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 / 책이 아닌 상품 제외"""
    bad = [
        item("8801234567890", title="음반"),
        book(author=""),
        book(goodsSortNm="국내도서-잡지"),
        book(adultYn="Y"),
    ]
    good = [book(), book()]
    fake = FakeCategories({("001001000", 1): page(*bad, *good)})
    records, books = await collect(fake.client(), _plan(2))
    assert [b["item"]["isbn13"] for b in books] == [g["isbn13"] for g in good]
    assert records[0].skipped == {
        SkipReason.NOT_ISBN: 1,
        SkipReason.NO_TITLE_AUTHOR: 1,
        SkipReason.NOT_BOOK: 1,
        SkipReason.ADULT: 1,
    }


async def test_duplicate_between_fields() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 / 분야 사이의 중복"""
    shared = book()
    first, second = book(), book()
    fake = FakeCategories(
        {("001001000", 1): page(shared, first), ("001001001", 1): page(shared, second)}
    )
    records, books = await collect(fake.client(), _plan(2, 1))
    assert [(b["field"], b["item"]["isbn13"]) for b in books] == [
        ("f0", shared["isbn13"]),
        ("f0", first["isbn13"]),
        ("f1", second["isbn13"]),
    ]
    assert records[1].skipped == {SkipReason.DUPLICATE: 1}


async def test_field_with_fewer_books() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 / 목표보다 적은 분야"""
    fake = FakeCategories(
        {
            ("001001000", 1): page(*[book() for _ in range(7)]),
            ("001001001", 1): page(book()),
        }
    )
    records, books = await collect(fake.client(), _plan(10, 1))
    assert [r.fetched for r in records] == [7, 1]
    assert len(books) == 8
    assert len(fake.requests) == 2  # 전체 수가 한 쪽 안이라 다음 쪽을 부르지 않는다


async def test_next_page_when_short() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 (거른 만큼 다음 쪽에서 채움)"""
    fake = FakeCategories(
        {
            ("001001000", 1): page(book(adultYn="Y"), book(), total=150),
            ("001001000", 2): page(book(), book(), total=150),
        }
    )
    records, books = await collect(fake.client(), _plan(2))
    assert (records[0].fetched, records[0].pages, len(fake.requests)) == (2, 2, 2)


async def test_record_contents(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/experiment-collection] 받은 기록과 원본 파일 / 기록 내용"""
    monkeypatch.setattr(fetch_module, "FIELDS", _plan(1, 1))
    monkeypatch.setattr(
        fetch_module.clock, "today", lambda: __import__("datetime").date(2026, 11, 15)
    )
    fake = FakeCategories({("001001000", 1): page(book()), ("001001001", 1): page(book())})
    path = tmp_path / "data" / "collection.json"
    assert await fetch(fake.client(), path) == EXIT_OK
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert (saved["fetched_on"], saved["source"], saved["method"]) == (
        "2026-11-15",
        "yes24",
        "category/bestsellerSteady",
    )
    assert [(f["key"], f["category_id"], f["target"], f["fetched"]) for f in saved["fields"]] == [
        ("f0", "001001000", 1, 1),
        ("f1", "001001001", 1, 1),
    ]
    assert [b["field"] for b in saved["books"]] == ["f0", "f1"]


async def test_volatile_values_not_saved(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/experiment-collection] 받은 기록과 원본 파일 / 변동 정보 미저장"""
    monkeypatch.setattr(fetch_module, "FIELDS", _plan(1))
    volatile = book(salePrice=98765, itemStatus="품절임박", starScore=8.7, salePoint=55443)
    fake = FakeCategories({("001001000", 1): page(volatile)})
    path = tmp_path / "collection.json"
    assert await fetch(fake.client(), path) == EXIT_OK
    raw = path.read_text(encoding="utf-8")
    for value in ("98765", "품절임박", "8.7", "55443", "yesPoint", "salePrice", "starScore"):
        assert value not in raw
    assert json.loads(raw)["books"][0]["item"]["shopPrice"] == 14000  # 정가는 남는다


async def test_series_list_kept(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/experiment-collection] 받은 기록과 원본 파일 / 시리즈 목록 유지"""
    monkeypatch.setattr(fetch_module, "FIELDS", _plan(1))
    series = [{"seriesId": 1, "seriesName": "읽고, 쓰고"}, {"seriesId": 2, "seriesName": "둘째"}]
    fake = FakeCategories({("001001000", 1): page(book(series=series))})
    path = tmp_path / "collection.json"
    assert await fetch(fake.client(), path) == EXIT_OK
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["books"][0]["item"]["series"] == series


async def test_existing_file_stops_without_calls(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 한 번만 받기 / 파일이 이미 있음"""
    path = tmp_path / "collection.json"
    path.write_text("기존", encoding="utf-8")
    fake = FakeCategories({})
    assert await fetch(fake.client(), path) == EXIT_PRECONDITION
    assert fake.requests == []
    assert path.read_text(encoding="utf-8") == "기존"
    assert "한 번만" in capsys.readouterr().err


async def test_existing_file_stops_before_key_check(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[platform/experiment-collection] 한 번만 받기 / 파일이 이미 있음 (명령줄)"""
    path = tmp_path / "collection.json"
    path.write_text("기존", encoding="utf-8")
    monkeypatch.setattr(fetch_module, "DATA_FILE", path)
    assert await fetch_module.run([]) == EXIT_PRECONDITION


async def test_upstream_failure_mid_run(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/experiment-collection] 한 번만 받기 / 중간에 외부 장애"""
    monkeypatch.setattr(fetch_module, "FIELDS", _plan(1, 1, 1))
    fake = FakeCategories(
        {
            ("001001000", 1): page(book()),
            ("001001001", 1): page(book()),
            ("001001002", 1): httpx.Response(429),
        }
    )
    path = tmp_path / "collection.json"
    assert await fetch(fake.client(), path) == EXIT_STOPPED
    assert not path.exists()


async def test_dry_run_makes_no_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 한 번만 받기 / 호출 수 미리 보기"""

    def no_network(*_args, **_kwargs):
        raise AssertionError("외부를 불렀다")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    assert await fetch_module.run(["--dry-run"]) == EXIT_OK
    out = capsys.readouterr().out
    least, most = expected_calls()
    assert f"예상 호출 {least}회" in out and f"최대 {most}회" in out
    assert "유아 (001001027): 목표 75권" in out
    assert least == len(FIELDS)


def test_plan_shape() -> None:
    """[platform/experiment-collection] 분야 구성대로 받기 (분야 구성: design 결정 12)"""
    assert sum(f.target for f in FIELDS) == 525
    assert all(len(f.category_id) in (9, 12) and f.category_id.isdigit() for f in FIELDS)
    assert len({f.key for f in FIELDS}) == len({f.category_id for f in FIELDS}) == len(FIELDS)
    assert {f.name for f in FIELDS if f.holdout} == {"종교", "예술", "건강 취미", "여행"}
    order = [f.category_id for f in FIELDS]
    for f in FIELDS:  # 하위 카테고리가 상위보다 앞
        parents = [p for p in order if p != f.category_id and f.category_id.startswith(p)]
        assert all(order.index(p) > order.index(f.category_id) for p in parents)
