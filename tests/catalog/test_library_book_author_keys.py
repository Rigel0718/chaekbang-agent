"""[catalog/book-contributors] 기관 도서 저자 키, [catalog/library-books] 분류기호 정규화.

저자 키와 분류기호는 기관 도서를 쓰는 모든 경로(등록, 수정, 가져오기)가 같은 규칙으로 정한다.
"""

import ast
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contributors import author_keys
from tests.catalog.import_helpers import import_file
from tests.conftest import Tenant
from tests.helpers import fetch

HEADER = ["등록번호", "서명", "저자"]
APP = Path(__file__).resolve().parents[2] / "app"


async def _create(client: AsyncClient, **values) -> dict:
    res = await client.post("/library-books", json={"title": "책", "author": "김주민", **values})
    assert res.status_code == 201, res.text
    return res.json()


async def _keys(session: AsyncSession, library_book_id: int) -> list[str]:
    return (await fetch(session, "library_books", library_book_id))["author_keys"]


async def _imported(session: AsyncSession, accession: str):
    result = await session.execute(
        text(
            "SELECT b.* FROM holdings h JOIN library_books b ON b.id = h.library_book_id"
            " WHERE h.accession_number = :a"
        ),
        {"a": accession},
    )
    return result.mappings().one()


async def _assert_invariant(session: AsyncSession, library_id: int) -> None:
    rows = await session.execute(
        text("SELECT author, author_keys FROM library_books WHERE library_id = :id"),
        {"id": library_id},
    )
    for author, keys in rows:
        assert keys == author_keys(author), author


# --- 저자 키 ---


async def test_author_keys_on_create(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 / 등록"""
    book = await _create(admin_client, author="한 강 지음 ; 데보라 스미스 옮김")
    assert await _keys(session, book["id"]) == ["한강"]


async def test_author_keys_on_update(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 / 저자 수정"""
    book = await _create(admin_client, author="김주민")
    assert await _keys(session, book["id"]) == ["김주민"]
    res = await admin_client.patch(
        f"/library-books/{book['id']}", json={"author": "박마을, 김주민"}
    )
    assert res.status_code == 200, res.text
    assert await _keys(session, book["id"]) == ["박마을", "김주민"]


async def test_author_keys_on_import(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 / 가져오기"""
    await import_file(admin_client_b, HEADER, ["AK1", "검은 꽃", "김영하 지음"])
    assert (await _imported(session, "AK1"))["author_keys"] == ["김영하"]


async def test_author_keys_without_writer(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 / 지은이가 없는 원문"""
    book = await _create(admin_client, author="홍길동 역")
    assert await _keys(session, book["id"]) == []


async def test_author_keys_not_in_response(admin_client: AsyncClient) -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 / 응답에 없음"""
    book = await _create(admin_client)
    assert "author_keys" not in book
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert "author_keys" not in body
    listed = (await admin_client.get("/library-books")).json()["items"]
    assert all("author_keys" not in item for item in listed)


async def test_every_write_path_keeps_author_keys(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """등록, 수정, 가져오기 적용 뒤 모든 행에서 저자 키가 저자 원문으로 계산한 값과 같다."""
    first = await _create(admin_client, author="칼 멜링 글/브라이트 스타 그림")
    await _create(admin_client, title="둘", author="백희나 (지은이), 김소연 (옮긴이)")
    await admin_client.patch(f"/library-books/{first['id']}", json={"author": "지은이: 한강"})
    await import_file(
        admin_client_b,
        HEADER,
        ["AK1", "검은 꽃", "김영하 지음"],
        ["AK2", "마을 이야기", "김주민 글 / 박마을 그림"],
    )
    await _assert_invariant(session, library_a.id)
    await _assert_invariant(session, library_b.id)


def test_no_core_update_writes_author() -> None:
    """`app/`에 저자를 값으로 주는 Core `update(LibraryBook)`가 없다(저자 키를 건너뛰는 경로)."""
    offenders = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "values":
                continue
            base = node.func.value
            while isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute):
                base = base.func.value
            is_update = (
                isinstance(base, ast.Call)
                and getattr(base.func, "id", None) in {"update", "insert"}
                and any(getattr(a, "id", None) == "LibraryBook" for a in base.args)
            )
            sets_author = any(k.arg == "author" for k in node.keywords) or any(
                isinstance(a, ast.Dict)
                and any(getattr(k, "value", None) == "author" for k in a.keys)
                for a in node.args
            )
            if is_update and sets_author:
                offenders.append(f"{path.relative_to(APP)}:{node.lineno}")
    assert offenders == []


# --- 분류기호 정규화 ---


async def test_kdc_on_create(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 분류기호 정규화 / 등록할 때 맞춤"""
    book = await _create(admin_client, kdc="KDC 813.7")
    assert book["kdc"] == "813.7"
    assert (await fetch(session, "library_books", book["id"]))["kdc"] == "813.7"


async def test_kdc_on_update(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 분류기호 정규화 / 수정할 때 맞춤"""
    book = await _create(admin_client)
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"kdc": "８１３．７"})
    assert res.status_code == 200, res.text
    assert (await fetch(session, "library_books", book["id"]))["kdc"] == "813.7"


async def test_kdc_on_import(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 분류기호 정규화 / 가져오기에서 맞춤"""
    await import_file(
        admin_client_b, [*HEADER, "분류기호"], ["AK1", "검은 꽃", "김영하", "813.7-한232ㅊ"]
    )
    assert (await _imported(session, "AK1"))["kdc"] == "813.7"


async def test_kdc_unreadable(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 분류기호 정규화 / 읽을 수 없는 값"""
    book = await _create(admin_client, kdc=" 향토  자료 ")
    assert book["kdc"] == "향토 자료"
