"""[platform/web-ui] 화면 서빙과 화면 코드의 계약. 화면 동작은 design의 브라우저 확인이 본다."""

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.library.schemas.catalog import BookSummary, RelatedBook
from app.library.schemas.librarian import BookCard
from app.main import app

WEB = Path(__file__).resolve().parents[2] / "app" / "web"
PUBLIC = WEB / "public"
INDEX = PUBLIC / "librarian" / "index.html"


def _js_files() -> list[Path]:
    return sorted(PUBLIC.rglob("*.js"))


def _reference(base: Path, ref: str) -> Path | None:
    """HTML이 참조하거나 JS가 불러오는 같은 출처의 파일."""
    if ref.startswith(("http:", "https:", "data:", "#")):
        return None
    if ref.startswith("/ui/"):
        return PUBLIC / ref.removeprefix("/ui/")
    return (base.parent / ref).resolve()


def _local_references(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        refs = re.findall(r"""(?:src|href)=["']([^"']+)["']""", text)
    elif path.suffix == ".js":
        refs = re.findall(r"""(?:from|import)\s*\(?\s*["'](\.{1,2}/[^"']+)["']""", text)
    else:
        refs = []
    found = [_reference(path, ref.split("?")[0]) for ref in refs]
    return [p for p in found if p is not None]


def _reachable() -> set[Path]:
    seen: set[Path] = set()
    todo = [INDEX]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        todo.extend(_local_references(current))
    return seen


# 이용자 화면 내주기


async def test_screen_html_is_served_without_token(client: AsyncClient):
    """[web-ui] 화면 HTML: 토큰 없이 200이고 HTML이다."""
    response = await client.get("/ui/librarian/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


async def test_every_referenced_file_is_served(client: AsyncClient):
    """[web-ui] 화면이 참조하는 파일: 스타일, 스크립트, 불러오는 모듈이 모두 200이다."""
    files = _reachable()
    assert len(files) > 1  # 틀 말고 참조가 있어야 이 검사가 뜻이 있다
    for path in files:
        assert path.exists(), f"참조하는 파일이 없다: {path}"
        url = "/ui/" + path.relative_to(PUBLIC).as_posix()
        assert (await client.get(url)).status_code == 200, url


async def test_missing_screen_file_is_404(client: AsyncClient):
    """[web-ui] 없는 화면 파일: 404다."""
    assert (await client.get("/ui/librarian/없는파일.js")).status_code == 404


@pytest.mark.parametrize("name", ["README.md", "CLAUDE.md"])
async def test_package_docs_are_not_served(client: AsyncClient, name: str):
    """[web-ui] 화면 패키지 문서는 내주지 않는다."""
    assert (WEB / name).exists()
    assert (await client.get(f"/ui/{name}")).status_code == 404


# 화면 경로가 API를 가리지 않음


async def test_librarian_messages_still_requires_token(client: AsyncClient):
    """[web-ui] AI 사서 대화 경로: 토큰 없이 401이다(화면이 가리지 않는다)."""
    assert (await client.post("/librarian/messages", json={"message": "안녕"})).status_code == 401


async def test_catalog_suggest_still_requires_token(client: AsyncClient):
    """[web-ui] 검색 경로: 토큰 없이 401이다."""
    assert (await client.get("/catalog/suggest", params={"q": "데"})).status_code == 401


async def test_api_docs_still_served(client: AsyncClient):
    """[web-ui] API 문서: 200이다."""
    assert (await client.get("/docs")).status_code == 200


# 기존 API만 사용

ALLOWED_PATHS = {
    "/catalog/suggest",
    "/catalog/search",
    "/catalog/books/{id}/similar",
    "/librarian/messages",
    "/librarian/sessions/{id}",
    "/library/guide",
}


def test_ui_has_one_static_mount_and_no_api_route():
    """[web-ui] 서버 경로: /ui 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다."""
    ui = [r for r in app.routes if getattr(r, "path", "").startswith("/ui")]
    assert len(ui) == 1
    assert not isinstance(ui[0], APIRoute)
    assert not [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/ui")]


def test_screen_requests_only_allowed_paths():
    """[web-ui] 화면이 부르는 경로: 소스의 서버 경로가 모두 허용 목록 안이고 빠짐없이 쓰인다."""
    used: set[str] = set()
    for path in _js_files():
        text = path.read_text(encoding="utf-8")
        for raw in re.findall(r"""[`'"](/[a-z][^`'"\s]*)[`'"]""", text):
            used.add(re.sub(r"\$\{[^}]*\}", "{id}", raw).split("?")[0])
    assert used <= ALLOWED_PATHS, f"허용 목록에 없는 경로: {used - ALLOWED_PATHS}"
    assert used == ALLOWED_PATHS, f"쓰지 않는 허용 경로: {ALLOWED_PATHS - used}"


# 브라우저 저장


def test_only_token_key_in_local_storage():
    """[web-ui] 저장소 사용: localStorage는 토큰 키를 읽고 쓰고 지우는 곳뿐, 다른 저장소는 없다."""
    token_calls = 0
    for path in _js_files():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"sessionStorage|indexedDB|document\.cookie|caches\.", text), path
        uses = len(re.findall(r"localStorage", text))
        token_uses = len(re.findall(r"localStorage\.(?:get|set|remove)Item\(\s*TOKEN_KEY\b", text))
        assert uses == token_uses, f"토큰 키 말고 localStorage를 쓴다: {path}"
        token_calls += token_uses
    assert token_calls == 3  # 읽기, 쓰기, 지우기
    api = (PUBLIC / "shared" / "api.js").read_text(encoding="utf-8")
    assert re.search(r"const TOKEN_KEY = \"[^\"]+\";", api)


# 서버 값의 안전한 표시


def test_no_html_interpretation():
    """[web-ui] HTML 해석 없음: 해석하는 API가 소스에 없다."""
    pattern = r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function|srcdoc"
    for path in _js_files():
        assert not re.search(pattern, path.read_text(encoding="utf-8")), path


def test_urls_go_through_safe_url():
    """[web-ui] 주소 형식: src·href에 넣는 값은 모두 safeUrl이 거른 값이다."""
    guarded = 0
    for path in _js_files():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"setAttribute\(\s*[\"'](?:src|href)", text), path
        safe_names = set(re.findall(r"const (\w+) = safeUrl\(", text))
        for name in re.findall(r"\.(?:src|href)\s*=\s*([^;]+);", text):
            assert name.strip() in safe_names, f"safeUrl을 거치지 않은 주소: {path} {name}"
            guarded += 1
    assert guarded >= 2  # 표지와 상품 링크


# 카드 필드와 응답 스키마 일치


def _card_schema_fields() -> set[str]:
    return (
        set(BookSummary.model_fields) | set(BookCard.model_fields) | set(RelatedBook.model_fields)
    )


def _card_fields_read(text: str) -> set[str]:
    return set(re.findall(r"\bbook\.(\w+)", text))


def test_card_fields_exist_in_schemas():
    """[web-ui] 카드 필드: 화면이 책 값에서 읽는 필드는 모두 응답 스키마에 있다."""
    read: set[str] = set()
    for path in _js_files():
        read |= _card_fields_read(path.read_text(encoding="utf-8"))
    assert {"title", "library_book_id", "cover_url", "reason", "basis_text"} <= read
    assert read <= _card_schema_fields(), f"스키마에 없는 필드: {read - _card_schema_fields()}"


def test_unknown_card_field_is_reported():
    """[web-ui] 필드 이름이 바뀜: 스키마에 없는 필드를 읽는 소스는 그 이름이 걸러진다."""
    renamed = "const text = book.title + book.cover_image_url;"
    assert _card_fields_read(renamed) - _card_schema_fields() == {"cover_image_url"}
