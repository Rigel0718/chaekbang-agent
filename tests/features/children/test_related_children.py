"""[features/children] 어린이 관련 책 tool, 어린이 기준 책의 관련 책 범위."""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.features.children.service import related_scope
from app.features.children.tools import children_extension
from app.library import hooks
from app.library.models.library import LoanMode
from app.library.services.related import SESSION_BOOKS, related_for_session, similar_for_book
from tests.agent.fakes import FakeLlm, answers
from tests.conftest import Tenant
from tests.helpers import add_audience
from tests.library.librarian_helpers import librarian, run_librarian, submit
from tests.library.test_related_books import load_product
from tests.library.test_related_recommendation import linked, unlinked
from tests.library.test_related_tool import related

WRITER = "한작가 저"


@pytest.fixture
def children_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """서버와 같게 어린이 범위 제공자만 등록한다."""
    monkeypatch.setattr(hooks, "_related_scopes", [related_scope])


def _profile():
    return librarian(LoanMode.INTERNAL, children_extension())


async def _mixed(session: AsyncSession, library_id: int) -> dict[str, int]:
    """기준 그림책 하나와 비슷한 어린이 도서·일반 도서."""
    ids = {
        "kid_base": await linked(session, library_id, "기준 그림책", author=WRITER),
        "kid_near": await unlinked(session, library_id, "가까운 그림책"),
        "general_near": await linked(session, library_id, "가까운 일반책", author=WRITER),
        "general_base": await unlinked(session, library_id, "기준 일반책"),
    }
    for key in ("kid_base", "kid_near"):
        await add_audience(session, library_id, ids[key], "children")
    await load_product(
        session, library_id, {"가까운 그림책": 0.8, "가까운 일반책": 0.9, "일반책": 0.95}
    )
    return ids


def _result(llm: FakeLlm) -> dict:
    [result] = [m for m in llm.requests[1]["messages"] if isinstance(m, ToolResult)]
    assert not result.is_error, result.content
    return json.loads(result.content)


def _book_ids(items) -> list[int]:
    return [item.candidate.library_book.id for item in items]


# --- 어린이 관련 책 tool ---


async def test_children_related_tool_only_children(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[features/children] 어린이 관련 책 tool / 어린이 도서만 나옴"""
    monkeypatch.setattr(hooks, "_related_scopes", [])
    ids = await _mixed(session, library_a.id)
    llm = FakeLlm([related(ids["general_base"], "find_related_children_books"), submit("있어요.")])
    await run_librarian(session, llm, library_a.id, "비슷한 거", prof=_profile())
    found = [b["library_book_id"] for b in _result(llm)["books"]]
    assert found and set(found) <= {ids["kid_base"], ids["kid_near"]}


async def test_children_related_tool_from_session(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[features/children] 어린이 관련 책 tool / 비워서 부름"""
    monkeypatch.setattr(hooks, "_related_scopes", [])
    ids = await _mixed(session, library_a.id)
    llm = FakeLlm([related(None, "find_related_children_books"), submit("있어요.")])
    await run_librarian(
        session,
        llm,
        library_a.id,
        "더 없어요?",
        prof=_profile(),
        tool_values={SESSION_BOOKS: (ids["general_base"],)},
    )
    found = [b["library_book_id"] for b in _result(llm)["books"]]
    assert found and set(found) <= {ids["kid_base"], ids["kid_near"]}


async def test_children_related_tool_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[features/children] 어린이 관련 책 tool / 다른 기관의 어린이 구분"""
    monkeypatch.setattr(hooks, "_related_scopes", [])
    ids = await _mixed(session, library_a.id)
    shared = await linked(session, library_a.id, "가까운 공유책", author=WRITER)
    theirs = await unlinked(session, library_b.id, "가까운 공유책")
    await add_audience(session, library_b.id, theirs, "children")
    await load_product(session, library_a.id, {"공유책": 0.99})
    llm = FakeLlm([related(ids["general_base"], "find_related_children_books"), submit("있어요.")])
    await run_librarian(session, llm, library_a.id, "비슷한 거", prof=_profile())
    assert shared not in [b["library_book_id"] for b in _result(llm)["books"]]


async def test_children_related_tool_makes_children_request(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[features/children] 어린이 요청 판단 / LLM이 어린이 관련 책 tool을 씀"""
    monkeypatch.setattr(hooks, "_related_scopes", [])
    ids = await _mixed(session, library_a.id)
    llm = FakeLlm(
        [
            related(ids["general_base"], "find_related_children_books"),
            submit("이 책요", ids["general_near"]),
            submit("이 책요", ids["kid_near"]),
        ]
    )
    events = await run_librarian(session, llm, library_a.id, "비슷한 거", prof=_profile())
    assert answers(events)[0].recommendations[0].library_book_id == ids["kid_near"]


# --- 어린이 기준 책의 관련 책 범위 ---


async def test_children_base_narrows(
    session: AsyncSession, library_a: Tenant, children_scope: None
) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 어린이 기준 책(service)"""
    ids = await _mixed(session, library_a.id)
    found = _book_ids(await similar_for_book(session, library_a.id, ids["kid_base"]))
    assert found == [ids["kid_near"]]


async def test_children_base_narrows_api(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, children_scope: None
) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 어린이 기준 책(API)"""
    ids = await _mixed(session, library_a.id)
    body = (await kiosk_client.get(f"/catalog/books/{ids['kid_base']}/similar")).json()
    assert [item["library_book_id"] for item in body] == [ids["kid_near"]]


async def test_general_base_not_narrowed(
    session: AsyncSession, library_a: Tenant, children_scope: None
) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 일반 기준 책"""
    ids = await _mixed(session, library_a.id)
    found = set(_book_ids(await similar_for_book(session, library_a.id, ids["general_base"])))
    assert {ids["kid_near"], ids["general_near"]} <= found


async def test_mixed_history_not_narrowed(
    session: AsyncSession, library_a: Tenant, children_scope: None
) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 섞인 기록"""
    ids = await _mixed(session, library_a.id)
    assert (
        await related_scope(session, library_a.id, [ids["kid_base"], ids["general_base"]]) is None
    )
    found = set(
        _book_ids(
            await related_for_session(session, library_a.id, [ids["kid_base"], ids["general_base"]])
        )
    )
    assert ids["general_near"] in found


async def test_other_library_children_not_used(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, children_scope: None
) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 다른 기관의 어린이 구분"""
    await _mixed(session, library_a.id)
    mine = await unlinked(session, library_a.id, "기준 공유책")
    theirs = await unlinked(session, library_b.id, "기준 공유책")
    await add_audience(session, library_b.id, theirs, "children")
    assert await related_scope(session, library_a.id, [mine]) is None
    assert await related_scope(session, library_b.id, [theirs]) is not None


async def test_no_base_not_narrowed(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 기준 책 없음(보조)"""
    assert await related_scope(session, library_a.id, []) is None


def test_scope_registered_for_server_and_eval() -> None:
    """[features/children] 어린이 기준 책의 관련 책 범위 / 서버와 평가 진입점의 등록"""
    import app.main  # noqa: F401  등록은 import 때 한다

    assert related_scope in hooks._related_scopes
    before = list(hooks._related_scopes)
    hooks.register_related_scope(related_scope)
    assert hooks._related_scopes == before  # 두 번 등록해도 한 번
    source = Path("evals/librarian/__main__.py").read_text(encoding="utf-8")
    assert "register_related_scope(children_related_scope)" in source
