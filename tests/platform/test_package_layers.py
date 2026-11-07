"""[platform/package-layers] 패키지 의존 방향과 경계."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import RunStatus
from app.library import hooks
from tests.agent.fakes import (
    FakeLlm,
    answer_turn,
    answers,
    call,
    collect,
    done,
    echo_tool,
    profile,
    tool_turn,
)
from tests.catalog.import_helpers import import_file
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, VALID_ISBN_2

APP = Path(__file__).resolve().parents[2] / "app"

# 패키지별로 import하면 안 되는 위 층
FORBIDDEN = {
    "core": ("app.agent", "app.central", "app.library", "app.features"),
    "agent": ("app.central", "app.library", "app.features"),
    "central": ("app.library", "app.features"),
    "library": ("app.features",),
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("package", FORBIDDEN)
def test_no_upward_imports(package: str) -> None:
    """[platform/package-layers] 패키지 의존 방향 / 거꾸로 된 import 금지"""
    wrong = [
        f"{path.relative_to(APP)}: {name}"
        for path in (APP / package).rglob("*.py")
        for name in _imports(path)
        if name.startswith(FORBIDDEN[package])
    ]
    assert wrong == []


def test_agent_imports_only_core() -> None:
    """[platform/package-layers] 패키지 의존 방향 / 실행기의 import 제한"""
    names = {
        name
        for path in (APP / "agent").rglob("*.py")
        for name in _imports(path)
        if name.startswith("app.")
    }
    assert {name.split(".")[1] for name in names} <= {"agent", "core"}


def test_runner_import_loads_no_library_packages() -> None:
    """[platform/package-layers] 공통 실행기의 경계 / 실행기만 불러오기

    정적 검사가 놓치는 간접 import까지 보려고 새 프로세스에서 불러 본다.
    """
    code = (
        "import sys\n"
        "import app.agent.runner, app.agent.openai_client\n"
        "print([m for m in sys.modules if m.startswith(('app.central', 'app.library', "
        "'app.features'))])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=APP.parent,
    )
    assert result.stdout.strip() == "[]"


async def test_runner_works_with_fakes_only(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/package-layers] 공통 실행기의 경계 / 가짜 tool로 실행"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "공룡"})), answer_turn("찾았어요")])
    events = await collect(session, llm, profile(echo_tool()), library_a.id)
    assert [a.message for a in answers(events)] == ["찾았어요"]
    assert done(events).status == RunStatus.COMPLETED


def test_runner_names_no_specific_tool() -> None:
    """[platform/package-layers] 공통 실행기의 경계 / 가짜 tool로 실행 (특정 tool을 모른다)"""
    for path in (APP / "agent").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in ("search_collection", "get_book_detail", "submit_answer", "children"):
            assert name not in source, (path, name)


def test_central_has_no_library_models() -> None:
    """[platform/package-layers] 운영자 층의 경계 / 운영자 코드의 기관 모델 참조 없음"""
    for path in (APP / "central").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "LibraryBook" not in text and "Holding" not in text, path


async def test_common_works_without_features(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[platform/package-layers] 기관 개별 기능 없는 공통 동작 / 기능 없이 등록과 가져오기"""
    monkeypatch.setattr(hooks, "_hooks", [])
    await session.execute(
        text(
            "INSERT INTO books (isbn, title, author, external_category) VALUES (:i, 't', 'a', :c)"
        ),
        {"i": VALID_ISBN_2, "c": "국내도서-어린이"},
    )
    res = await admin_client.post(
        "/library-books", json={"isbn": VALID_ISBN_2, "title": "모모", "author": "엔데"}
    )
    assert res.status_code == 201
    await import_file(
        admin_client_b,
        ["등록번호", "서명", "저자", "ISBN", "별치기호"],
        ["EM1", "책", "저자", VALID_ISBN, "아"],
    )
    assert await session.scalar(text("SELECT count(*) FROM holdings")) == 1
    assert await session.scalar(text("SELECT count(*) FROM library_book_audiences")) == 0


async def test_common_response_has_no_audience(admin_client: AsyncClient) -> None:
    """[platform/package-layers] 기관 개별 기능 없는 공통 동작 / 공통 응답에 어린이 값 없음"""
    created = await admin_client.post(
        "/library-books", json={"isbn": VALID_ISBN, "title": "모모", "author": "엔데"}
    )
    body = (await admin_client.get(f"/library-books/{created.json()['id']}")).json()
    assert "audience" not in body and "audience_source" not in body
