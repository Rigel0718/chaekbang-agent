"""[platform/web-ui] 화면 서빙과 화면 코드의 계약. 화면 동작은 design의 브라우저 확인이 본다."""

import re
from pathlib import Path
from typing import get_args

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.core.config import get_settings
from app.library.api.catalog import MAX_QUERY_LENGTH
from app.library.importing import rows as import_rows
from app.library.importing.columns import LABELS
from app.library.schemas.admin_results import DraftKind, DraftLink, TableResult
from app.library.schemas.catalog import BookSummary, RelatedBook
from app.library.schemas.holding_imports import HoldingImportRead, HoldingImportRow
from app.library.schemas.librarian import BookCard
from app.main import app

WEB = Path(__file__).resolve().parents[2] / "app" / "web"
PUBLIC = WEB / "public"
INDEX = PUBLIC / "librarian" / "index.html"
LOGIN_INDEX = PUBLIC / "login" / "index.html"
ADMIN_INDEX = PUBLIC / "admin" / "index.html"
SCREEN_INDEXES = [INDEX, LOGIN_INDEX, ADMIN_INDEX]


def _js_files() -> list[Path]:
    return sorted(PUBLIC.rglob("*.js"))


def _code(path: Path) -> str:
    """주석 줄을 뺀 소스. 규칙 검사가 주석 속 낱말에 걸리지 않게 한다."""
    return re.sub(r"(?m)^\s*//.*$", "", path.read_text(encoding="utf-8"))


def _reference(base: Path, ref: str) -> Path | None:
    """HTML이 참조하거나 JS가 불러오는 같은 출처의 파일."""
    if ref.startswith(("http:", "https:", "data:", "#")):
        return None
    if ref.endswith("/"):  # 화면 이동 링크(/ui/login/). 화면 HTML은 따로 내주는지 본다
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
    todo = [index for index in SCREEN_INDEXES if index.exists()]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        todo.extend(_local_references(current))
    return seen


# 이용자 화면 내주기


@pytest.mark.parametrize("url", ["/ui/librarian/", "/ui/login/", "/ui/admin/"])
async def test_screen_html_is_served_without_token(client: AsyncClient, url: str):
    """[web-ui] 화면 HTML(이용자·로그인·관리자): 토큰 없이 200이고 HTML이다."""
    response = await client.get(url)
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

# 화면이 부르는 경로와 메서드. 서버의 OpenAPI 경로에 모두 있어야 한다.
ALLOWED_CALLS = {
    "/auth/login": {"POST"},
    "/auth/me": {"GET"},
    "/auth/logout": {"POST"},
    "/auth/member-login": {"POST"},
    "/auth/member-logout": {"POST"},
    "/catalog/suggest": {"GET"},
    "/catalog/search": {"GET"},
    "/catalog/topic": {"GET"},
    "/catalog/books/{id}/similar": {"GET"},
    "/librarian/messages": {"POST"},
    "/librarian/sessions/{id}": {"DELETE"},
    "/library": {"GET"},
    "/library/guide": {"GET"},
    "/basket": {"GET", "DELETE"},
    "/basket/{id}": {"PUT", "DELETE"},
    "/loans": {"POST"},
    "/loans/return": {"POST"},
    "/book-requests": {"GET", "POST"},
    "/book-requests/{id}": {"PATCH"},
    "/admin-agent/messages": {"POST"},
    "/admin-agent/sessions/{id}": {"DELETE"},
    "/curations": {"GET"},
    "/curations/{id}": {"GET"},
    "/curations/{id}/approve": {"POST"},
    "/curations/{id}/reject": {"POST"},
    "/curations/{id}/unpublish": {"POST"},
    "/overdue-notice-templates": {"GET"},
    "/overdue-notice-templates/{id}": {"GET"},
    "/overdue-notice-templates/{id}/approve": {"POST"},
    "/overdue-notice-templates/{id}/reject": {"POST"},
    "/purchase-requests": {"GET"},
    "/purchase-requests/{id}": {"GET"},
    "/purchase-requests/{id}/approve": {"POST"},
    "/purchase-requests/{id}/reject": {"POST"},
    "/overdue-notices/today": {"GET"},
    "/holding-imports": {"GET", "POST"},
    "/holding-imports/{id}": {"GET", "DELETE"},
    "/holding-imports/{id}/rows": {"GET"},
    "/holding-imports/{id}/apply": {"POST"},
}


def test_ui_has_one_static_mount_and_no_api_route():
    """[web-ui] 서버 경로: /ui 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다."""
    ui = [r for r in app.routes if getattr(r, "path", "").startswith("/ui")]
    assert len(ui) == 1
    assert not isinstance(ui[0], APIRoute)
    assert not [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/ui")]


API_JS = PUBLIC / "shared" / "api.js"


def _api_entries() -> dict[str, str]:
    """api.js의 `export const api = { ... }` 안의 항목 이름 → 소스."""
    text = API_JS.read_text(encoding="utf-8")
    body = text[text.index("export const api = {") :]
    parts = re.split(r"^  (\w+):", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _approval_bases() -> dict[str, str]:
    text = API_JS.read_text(encoding="utf-8")
    block = text[text.index("const APPROVAL_BASES = {") :].split("};")[0]
    return dict(re.findall(r"(\w+):\s*\"(/[^\"]+)\"", block))


def _entry_calls(source: str) -> set[tuple[str, str]]:
    """api 항목 하나가 부르는 (경로, 메서드). 승인 종류 자리는 종류마다 풀어 쓴다."""
    bases = _approval_bases()
    method = (re.search(r'method:\s*"(\w+)"', source) or [None, "GET"])[1]
    literal = re.search(r"(?:request|query)\(\s*`([^`]+)`", source) or re.search(
        r"(?:request|query)\(\s*[\"'](/[^\"']+)[\"']", source
    )
    assert literal, source
    raw = literal.group(1).split("?")[0]
    results: set[tuple[str, str]] = set()
    if "APPROVAL_BASES[kind]" in raw:
        for base in bases.values():
            results.add((raw.replace("${APPROVAL_BASES[kind]}", base), method))
    elif "APPROVAL_BASES.curations" in raw:
        results.add((raw.replace("${APPROVAL_BASES.curations}", bases["curations"]), method))
    else:
        results.add((raw, method))
    return {(re.sub(r"\$\{[^}]*\}", "{id}", path), m) for path, m in results}


def _screen_calls() -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for source in _api_entries().values():
        calls |= _entry_calls(source)
    return calls


def test_screen_requests_only_allowed_paths():
    """[web-ui] 화면이 부르는 경로: 소스의 서버 경로·메서드가 허용 목록과 같다."""
    calls = _screen_calls()
    expected = {(path, method) for path, methods in ALLOWED_CALLS.items() for method in methods}
    assert calls == expected, f"차이: {calls ^ expected}"
    # api.js 밖에는 서버 경로를 쓰는 곳이 없다(화면 이동 /ui/ 경로는 제외)
    for path in _js_files():
        if path == API_JS:
            continue
        text = path.read_text(encoding="utf-8")
        for raw in re.findall(r"""[`'"](/[a-z][^`'"\s]*)[`'"]""", text):
            assert raw.startswith("/ui/"), f"api.js 밖의 서버 경로: {path} {raw}"


def test_screen_requests_exist_on_server():
    """[web-ui] 부르는 경로가 서버에 있음: 모든 (경로, 메서드)가 서버 OpenAPI에 있다."""
    server: dict[tuple[str, str], bool] = {}
    for route, operations in app.openapi()["paths"].items():
        for method in operations:
            server[(re.sub(r"\{[^}]*\}", "{id}", route), method.upper())] = True
    missing = [call for call in _screen_calls() if call not in server]
    assert not missing, f"서버에 없는 경로: {missing}"


# 회원 토큰의 행선지


def test_member_token_header_only_in_loan_request_logout():
    """[web-ui] 회원 토큰의 행선지: `X-Member-Token`은 대출·신청·담은 책·로그아웃에만 붙는다."""
    entries = _api_entries()
    assert {name for name, src in entries.items() if "MEMBER_HEADER" in src} == {
        "memberLogout",
        "borrow",
        "requestBook",
        "basket",
        "addBasket",
        "removeBasket",
        "clearBasket",
    }
    # 헤더 이름을 쓰는 곳은 api.js의 상수 하나뿐이다
    for path in _js_files():
        text = _code(path)
        assert text.count("X-Member-Token") == (1 if path == API_JS else 0), path


def test_member_number_nowhere_but_admin_readers():
    """[web-ui] 회원 토큰의 행선지: `member_number`는 관리자 목록 두 파일 말고는 어디에도 없다."""
    readers = {PUBLIC / "admin" / "requests.js", PUBLIC / "admin" / "overdue.js"}
    for path in _js_files():
        if path not in readers:
            assert "member_number" not in _code(path), path


def test_member_required_error_kind():
    """[web-ui] 회원 로그인: 403은 회원 세션 오류(member_required)이고 401과 따로 다룬다."""
    code = _code(API_JS)
    assert '403: "member_required"' in code
    actions = _code(PUBLIC / "librarian" / "actions.js")
    assert 'error.kind === "member_required"' in actions
    assert actions.count("ui.onMemberLost()") == 1
    # 회원 세션 오류는 키오스크 토큰을 지우거나 로그인 화면으로 보내지 않는다
    block = actions[actions.index('error.kind === "member_required"') :].split("} else {")[0]
    assert not re.search(r"goLogin|clearToken|onUnauthorized", block)


def test_member_token_not_in_storage():
    """[web-ui] 회원 토큰은 저장소에 없음: 회원 토큰은 member.js의 변수 한 칸에만 있다."""
    member_js = _code(PUBLIC / "librarian" / "member.js")
    assert not re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie", member_js)
    assert "setToken" not in member_js
    for path in (PUBLIC / "librarian").glob("*.js"):
        assert "setToken" not in _code(path), path


def test_member_login_markup():
    """[web-ui] 회원 로그인: 로그인은 보이고 담은 책·로그아웃은 숨김으로 시작한다."""
    html = INDEX.read_text(encoding="utf-8")

    def tag(element_id: str) -> str:
        match = re.search(rf"<\w+\b[^>]*\bid=\"{element_id}\"[^>]*>", html)
        assert match, element_id
        return match.group(0)

    assert not re.search(r"\bhidden\b", tag("open-login"))
    for element_id in ("basket-toggle", "basket", "basket-clear", "member-status", "member-logout"):
        assert re.search(r"\bhidden\b", tag(element_id)), element_id
    # 회원번호 칸은 없고 휴대폰 번호 칸이 하나 있다
    assert 'id="in-member"' not in html and "회원번호" not in html
    assert len(re.findall(r"<input\b[^>]*\bid=\"in-phone\"", html)) == 1
    for field in re.findall(r"<input\b[^>]*>", html):
        if re.search(r'id="in-(phone|accession|title|author|isbn)"', field):
            assert 'autocomplete="off"' in field, field


def test_member_logout_also_clears_the_chat():
    """[web-ui] 이용자 화면의 무입력·이용 상한 비우기: 회원 로그아웃은 바로 시작 화면이다."""
    code = _code(LIBRARIAN_MAIN)
    # 버튼·무입력·이용 상한: 문구 없이 resetAll로 바로 시작 화면(익명 시계를 다시 세지 않음)
    body = code[code.index("function memberLogout(") :].split("\n}\n")[0]
    assert "idle.memberLoggedOut();" in body and "member.logout()" in body
    assert "resetAll({ toStart: true })" in body and "showNotice" not in body
    # 403은 시작 화면 없이 화면만 로그아웃하고 로그인 칸으로 간다
    lost = code[code.index("function memberLost(") :].split("\n}\n")[0]
    assert (
        "resetChat();" in lost and "idle.memberLoggedOut();" in lost and "basket.clear();" in lost
    )
    assert "toStart" not in lost
    # resetAll은 대화·담은 책·입력칸을 비운다
    reset_all = code[code.index("function resetAll(") :].split("\n}\n")[0]
    assert "chat.reset();" in reset_all and "basket.clear();" in reset_all
    # [새 대화]는 로그인과 담은 책을 남긴다
    reset_chat = code[code.index("function resetChat()") :].split("\n}\n")[0]
    assert "basket.clear" not in reset_chat and "member.logout" not in reset_chat


def test_staff_login_link():
    """[web-ui] 이용자 화면의 직원 로그인 이동: 로그인 화면으로 가는 링크는 이동만 한다."""
    html = INDEX.read_text(encoding="utf-8")
    link = re.search(r"<a\b[^>]*\bid=\"staff-login\"[^>]*>", html)
    assert link and 'href="/ui/login/"' in link.group(0)
    assert not re.search(r"\bhidden\b", link.group(0))
    # 링크는 HTML뿐이다: 직원 로그아웃도 토큰 지우기도 하지 않는다
    for path in (PUBLIC / "librarian").glob("*.js"):
        assert "staff-login" not in _code(path), path


def test_member_status_shows_no_member_value():
    """[web-ui] 이용자 화면의 회원 로그인: 위 띠에는 이름·번호 없이 "로그인 중"만 보인다."""
    main = _code(LIBRARIAN_MAIN)
    assert 'id="member-status"' in INDEX.read_text(encoding="utf-8")
    render = main[main.index("function renderMember") :].split("\n}\n")[0]
    assert "textContent" not in render  # 로그인 중 글자는 HTML의 고정 문구다
    assert "로그인 중" in INDEX.read_text(encoding="utf-8")


def test_chat_request_body_keys():
    """[web-ui] 대화 요청의 본문: 키는 session_id, message, selected_library_book_id뿐이다."""
    text = (PUBLIC / "librarian" / "chat.js").read_text(encoding="utf-8")
    keys = set(re.findall(r"runTurn\(\{\s*(\w+):", text)) | set(
        re.findall(r"\.\.\.body,\s*(\w+):", text)
    )
    assert keys == {"message", "selected_library_book_id", "session_id"}
    assert "openMessages" in _api_entries()


# 운영 방식에 따른 대출 버튼


def test_loan_button_starts_hidden_and_request_button_is_shown():
    """[web-ui] 처음 그린 화면: [대출·반납]은 숨김으로 시작하고 [희망도서 신청]은 숨김이 아니다."""
    html = INDEX.read_text(encoding="utf-8")
    loan = re.search(r"<button\b[^>]*\bid=\"open-loan\"[^>]*>", html)
    request = re.search(r"<button\b[^>]*\bid=\"open-request\"[^>]*>", html)
    assert loan and re.search(r"\bhidden\b", loan.group(0))
    assert request and not re.search(r"\bhidden\b", request.group(0))


def test_loan_button_shown_only_for_internal_library():
    """[web-ui] 버튼을 보이는 조건: [대출·반납]은 `loan_mode`가 internal인 한 곳에서만 보인다."""
    uses: list[str] = []
    assignments: list[str] = []
    for path in sorted((PUBLIC / "librarian").glob("*.js")):
        text = _code(path)
        uses += re.findall(r"[^\n]*\bloan_mode\b[^\n]*", text)
        assignments += re.findall(r"loanButton\.hidden\s*=[^;]*;", text)
    assert len(uses) == 1 and re.search(r'loan_mode === "internal"', uses[0])
    assert assignments == ["loanButton.hidden = !available;"]


def test_desk_inputs_disable_autocomplete():
    """[web-ui] 입력칸 자동 완성: 대출·희망도서 입력칸과 그 폼은 모두 autocomplete="off"다."""
    html = INDEX.read_text(encoding="utf-8")
    section = html[html.index('id="desk"') : html.index("</section>", html.index('id="desk"'))]
    inputs = re.findall(r"<input\b[^>]*>", section)
    assert len(inputs) == 5
    for tag in [*inputs, re.search(r"<form\b[^>]*>", section).group(0)]:
        assert 'autocomplete="off"' in tag, tag


# 브라우저 저장


def test_token_keys_one_per_screen():
    """[web-ui] 저장소 사용: localStorage는 키오스크 키, sessionStorage는 관리자 키뿐."""
    for path in _js_files():
        code = _code(path)
        assert not re.search(r"indexedDB|document\.cookie|caches\.", code), path
        if path != API_JS:
            assert not re.search(r"localStorage|sessionStorage", code), path
    api = _code(API_JS)
    assert re.findall(r'const (\w+_TOKEN_KEY) = "([^"]+)"', api) == [
        ("KIOSK_TOKEN_KEY", "chaekbang.kiosk.token"),
        ("ADMIN_TOKEN_KEY", "chaekbang.admin.token"),
    ]
    local = re.findall(r"localStorage\.(\w+)Item\(\s*(\w+)", api)
    session = re.findall(r"sessionStorage\.(\w+)Item\(\s*(\w+)", api)
    assert local == [(op, "KIOSK_TOKEN_KEY") for op in ("get", "set", "remove")]
    assert session == [(op, "ADMIN_TOKEN_KEY") for op in ("get", "set", "remove")]


def test_old_token_key_and_hash_token_are_gone():
    """[web-ui] 옛 토큰 키: 옛 키 chaekbang.token과 주소의 #token=을 읽는 곳이 없다."""
    for path in [*_js_files(), *PUBLIC.rglob("*.html")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"chaekbang\.token\b", text), path
        assert "#token=" not in text, path


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


# 로그인과 역할


LOGIN_JS = PUBLIC / "login" / "login.js"
LIBRARIAN_MAIN = PUBLIC / "librarian" / "main.js"


def test_login_destinations_by_role():
    """[web-ui] 역할별 행선지: kiosk·admin만 이동하고 그 밖의 역할은 이동하지 않는다."""
    code = _code(LOGIN_JS)
    table = re.search(r"const DESTINATIONS = \{(.*?)\};", code, re.DOTALL).group(1)
    assert dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", table)) == {
        "kiosk": "/ui/librarian/",
        "admin": "/ui/admin/",
    }
    assert "if (!destination)" in code
    assert len(re.findall(r"location\.assign\(", code)) == 1


def test_login_inputs_disable_autocomplete_and_note_exists():
    """[web-ui] 로그인 입력칸: 아이디·비밀번호 칸과 폼은 autocomplete off, 저장 안내가 있다."""
    html = LOGIN_INDEX.read_text(encoding="utf-8")
    inputs = re.findall(r"<input\b[^>]*>", html)
    assert len(inputs) == 2
    for tag in [*inputs, re.search(r"<form\b[^>]*>", html).group(0)]:
        assert 'autocomplete="off"' in tag, tag
    assert "비밀번호를 저장하지 마세요" in html


def test_kiosk_screen_requires_kiosk_role_and_has_no_logout():
    """[web-ui] 받는 역할(이용자 쪽)과 로그아웃: kiosk만 받고 이용자 화면에 로그아웃이 없다."""
    code = _code(LIBRARIAN_MAIN)
    assert code.index('await requireRole("kiosk")') < code.index("createChat(")
    # 직원 로그아웃(`/auth/logout`)은 없다. 있는 [로그아웃]은 회원 로그아웃이다.
    for path in (PUBLIC / "librarian").glob("*.js"):
        text = _code(path)
        assert "api.logout" not in text and "/auth/logout" not in text, path
        assert "clearToken" not in text, path


def test_require_role_clears_only_own_key_and_goes_to_login():
    """[web-ui] 화면의 역할 확인: 토큰 없음·401·다른 역할이면 이 화면의 키만 지우고 로그인으로."""
    code = _code(API_JS)
    body = code[code.index("export async function requireRole") :]
    assert body.count("goLogin()") == 3  # 토큰 없음, 401, 역할 다름
    assert "me.role !== role" in body
    assert re.search(r'const LOGIN_PATH = "/ui/login/"', code)
    assert re.search(r"export function goLogin\(\) \{\s*clearToken\(\);", code)


# 이용자 화면의 무입력·이용 상한 비우기

IDLE_JS = PUBLIC / "librarian" / "idle.js"


def _seconds(name: str) -> int:
    match = re.search(rf"export const {name} = (\d+) \* 1000;", _code(IDLE_JS))
    assert match, name
    return int(match.group(1))


def test_clearing_time_values():
    """[web-ui] 시간 값: 무입력 60초·알림 45초, 이용 상한 180초·알림 150초, 서버 세션보다 짧다."""
    assert _seconds("IDLE_MS") == 60
    assert _seconds("IDLE_WARN_MS") == 45
    assert _seconds("CAP_MS") == 180
    assert _seconds("CAP_WARN_MS") == 150
    session_seconds = get_settings().librarian_session_idle_minutes * 60
    assert _seconds("IDLE_MS") < session_seconds
    assert _seconds("CAP_MS") < session_seconds
    # 서버 회원 세션 수명은 이용 상한과 같다(화면이 로그아웃을 놓쳐도 서버가 같은 때 끊는다)
    assert get_settings().member_session_minutes * 60 == _seconds("CAP_MS")


def test_cap_clock_starts_at_login_and_does_not_pause_or_extend():
    """[web-ui] 이용 상한: 로그인에서 시작하고, 답 받는 중에 멈추지 않으며 입력해도 늘지 않는다."""
    code = _code(IDLE_JS)
    pause = code[code.index("pause() {") : code.index("resume() {")]
    assert "stopCap" not in pause and "armCap" not in pause
    # 상한을 거는 곳은 회원 로그인 한 곳뿐이다(첫 입력과 입력마다는 걸지 않는다)
    assert len(re.findall(r"armCap\(\)", code)) == 2  # 정의와 호출
    login = code[code.index("memberLoggedIn() {") : code.index("memberLoggedOut() {")]
    assert "armCap();" in login
    activity = code[code.index("function activity()") :].split("}\n")[0]
    assert "armCap" not in activity


def test_idle_clock_logs_out_member_only():
    """[web-ui] 이용 상한: 로그인 중에는 회원만 로그아웃하고 아니면 화면을 비운다."""
    code = _code(IDLE_JS)
    expire = code[code.index("function expire()") : code.index("function expireMember()")]
    assert "if (memberOn)" in expire and "onClear({ member: true })" in expire
    assert "reset();" in expire and "onClear({ member: false })" in expire
    assert code.count("onClear({ member: true })") == 2  # 무입력과 이용 상한


# 관리자 화면

ADMIN = PUBLIC / "admin"


def _admin_code(name: str) -> str:
    return _code(ADMIN / name)


def test_admin_screen_requires_admin_role():
    """[web-ui] 받는 역할(관리자 쪽): 관리자 화면은 admin만 받고 로그아웃이 있다."""
    code = _admin_code("main.js")
    assert code.index('await requireRole("admin")') < code.index("createChat(")
    assert "api.logout()" in code and "goLogin()" in code
    assert "persisted" in code and 'requireRole("admin")' in code.split("persisted")[1]


ADMIN_MODE_SHOWS = {
    "internal": ('$("tab-overdue").hidden = false;', '$("group-templates").hidden = false;'),
    "external": ('$("tab-imports").hidden = false;',),
}


def test_admin_mode_tabs_start_hidden():
    """[web-ui] 처음 그린 화면(관리자): 연체 탭·틀 묶음·장서 가져오기 탭은 숨김으로 시작한다."""
    html = ADMIN_INDEX.read_text(encoding="utf-8")
    for element_id in ("tab-overdue", "group-templates", "tab-imports"):
        tag = re.search(rf"<\w+\b[^>]*\bid=\"{element_id}\"[^>]*>", html)
        assert tag and re.search(r"\bhidden\b", tag.group(0)), element_id


def test_admin_mode_tabs_shown_in_one_place():
    """[web-ui] 보이는 조건(관리자): 운영 방식은 한 곳에서 읽고, 연체 탭·틀 묶음은 internal,
    장서 가져오기 탭은 external일 때만 보인다."""
    code = _admin_code("main.js")
    assert len(re.findall(r"loan_mode", code)) == 1
    for mode, shows in ADMIN_MODE_SHOWS.items():
        condition = f'mode === "{mode}"'
        assert code.count(condition) == 1, condition
        block = code[code.index(condition) :].split("}")[0]
        for show in shows:
            assert block.count(show) == 1, (mode, show)
            assert code.count(show) == 1, show


def test_admin_hidden_tab_hash_opens_chat():
    """[web-ui] 자체 대출 기관(관리자): 숨긴 탭의 주소는 운영 대화로 간다."""
    code = _admin_code("main.js")
    block = code[code.index("function tabName()") :].split("\n}")[0]
    assert 'if (name === "overdue" && !overdueEnabled) return DEFAULT_TAB;' in block
    assert 'if (name === "imports" && !importsEnabled) return DEFAULT_TAB;' in block
    assert 'const DEFAULT_TAB = "chat";' in code


def test_admin_chat_request_body_keys():
    """[web-ui] 대화 요청의 본문(운영 에이전트): 키는 session_id, message뿐이다."""
    code = _admin_code("chat.js")
    keys = set(re.findall(r"adminOpenMessages\(\s*sessionId \? \{ (\w+):", code))
    keys |= set(re.findall(r"\{ session_id: sessionId, (\w+):", code))
    keys |= set(re.findall(r": \{ (\w+): text \}", code))
    assert keys == {"session_id", "message"}
    assert "member_number" not in code


def test_admin_chat_draws_results_after_answer():
    """[web-ui] 운영 대화의 표 / 사건 처리: result는 모으기만 하고 answer에서 그리며,
    table과 draft 종류만 처리한다."""
    code = _admin_code("chat.js")
    assert 'else if (event.name === "result") results.push(event.data);' in code
    answer = code[code.index('event.name === "answer"') : code.index('event.name === "done"')]
    assert "showResults(reply, results);" in answer
    assert code.count("showResults(") == 2  # 정의 하나와 answer 갈래의 호출 하나
    kinds = set(re.findall(r'result\.kind === "(\w+)"', code))
    assert kinds == {
        TableResult.model_fields["kind"].default,
        DraftLink.model_fields["kind"].default,
    }


def test_admin_chat_result_table_reads_schema_fields():
    """[web-ui] 운영 대화의 표 / 사건 처리: 읽는 result 필드가 결과 모양에 있고, 잘리면 전체 수와
    보인 수를 보인다."""
    code = _admin_code("chat.js")
    read = set(re.findall(r"\bresult\.(\w+)", code))
    read |= set(re.findall(r"const \{ ([\w, ]+) \} = result;", code)[0].split(", "))
    assert read <= set(TableResult.model_fields) | set(DraftLink.model_fields)
    assert "if (result.truncated)" in code and "${result.total}건 중 ${rows.length}건" in code


def test_admin_draft_kinds_match_server_and_approval_groups():
    """[web-ui] 초안 보기 / 종류 이름 맞춤: 서버의 초안 종류 셋이 승인 목록 묶음 하나씩으로 간다."""
    code = _admin_code("chat.js")
    body = re.search(r"const DRAFT_KINDS = \{([^}]*)\};", code).group(1)
    pairs = dict(re.findall(r'(\w+): "(\w+)"', body))
    assert set(pairs) == set(get_args(DraftKind))
    approvals = _admin_code("approvals.js")
    groups = approvals[approvals.index("const KINDS = {") :].split("\n};")[0]
    assert set(pairs.values()) == set(re.findall(r"(?m)^  (\w+): \{", groups))
    html = ADMIN_INDEX.read_text(encoding="utf-8")
    for group in pairs.values():
        assert f'id="list-{group}"' in html, group


def test_admin_open_draft_button_and_reveal():
    """[web-ui] 초안 보기: [초안 보기]는 승인 목록의 reveal을 거쳐 탭을 바꾸고, 대기에 없으면 전체
    보기로 찾은 뒤 없으면 알린다."""
    chat = _admin_code("chat.js")
    assert 'button("초안 보기", () => ui.onOpenDraft(' in chat
    main = _admin_code("main.js")
    assert "onOpenDraft: openDraft" in main
    assert "tabs.approvals.reveal(kind, id);" in main and 'location.hash = "approvals"' in main
    approvals = _admin_code("approvals.js")
    assert "return { show: load, reveal };" in approvals
    show = approvals[approvals.index("async function showTarget") :].split("\n  }")[0]
    assert show.index('view = "all"') < show.index("ui.note.textContent = NOT_FOUND")
    assert "scrollIntoView" in show
    html = ADMIN_INDEX.read_text(encoding="utf-8")
    assert 'id="approvals-note"' in html


def test_admin_member_values_only_in_member_tabs():
    """[web-ui] 회원 값을 읽는 곳: member_number·phone은 두 목록 파일에서만, 입장마다 재조회."""
    allowed = {"requests.js", "overdue.js"}
    for path in ADMIN.glob("*.js"):
        code = _code(path)
        found = re.search(r"\.(member_number|phone)\b", code)
        assert bool(found) == (path.name in allowed), path
    # 탭에 들어올 때마다 비우고 서버에서 다시 읽는다(떠날 때 지우지는 않는다)
    for name, loader in (("requests.js", "loadMore();"), ("overdue.js", "load();")):
        code = _admin_code(name)
        shown = code[code.index("show() {") :]
        assert "replaceChildren()" in shown.split(loader)[0] or "clear();" in shown.split(loader)[0]
        assert loader in shown
        assert "hide" not in code.replace("hidden", "")
    assert "tabs[current].hide()" not in _admin_code("main.js")


def test_no_console_output_and_no_copy_buttons():
    """[web-ui] 콘솔 출력 없음: 화면 스크립트에 console 호출과 복사·출력·내려받기가 없다."""
    for path in _js_files():
        code = _code(path)
        assert not re.search(r"\bconsole\.", code), path
        assert not re.search(r"clipboard|window\.print|\bdownload\b|createObjectURL", code), path


def test_admin_approval_actions_guarded():
    """[web-ui] 승인 목록: 승인은 확인을 거치고 빈 반려 사유는 요청하지 않으며 고치기가 없다."""
    code = _admin_code("approvals.js")
    assert code.index("confirm(APPROVE_CONFIRM[kind])") < code.index("api.approve(kind, row.id)")
    assert code.index("if (!reason)") < code.index("api.reject(kind, row.id, reason)")
    assert "REJECT_LIMIT = 200" in code
    api_text = API_JS.read_text(encoding="utf-8")
    assert api_text.count('method: "PUT"') == 1  # 고치기 없음: PUT은 담은 책 담기뿐
    assert api_text.count('method: "PATCH"') == 1  # 희망도서 닫기뿐
    # 상태별 동작: 게시 내리기는 큐레이션의 게시 상태에서만
    assert 'kind === "curations" && row.status === "published"' in code
    assert 'row.status === "pending_approval"' in code


def test_admin_purchase_detail_shows_estimate_and_record():
    """[web-ui] 승인 목록(구매 요청서): 추정 금액·가격 없음·조회 불가·확정본 기록을 보인다."""
    code = _admin_code("approvals.js")
    for needle in (
        "estimate.estimated_total",
        "estimate.missing_price_count",
        "estimate.unavailable",
        "가격 없음",
        "조회 불가",
        "row.total_amount",
        "row.price_source",
        "error.status === 503",
    ):
        assert needle in code, needle


def test_admin_pending_count_skips_templates_for_external():
    """[web-ui] 운영 대화 화면: 답이 끝나면 승인 대기 수를 다시 세고 외부 대출은 틀을 뺀다."""
    main = _admin_code("main.js")
    chat = _admin_code("chat.js")
    assert "onDone: refreshPendingCount" in main and "ui.onDone()" in chat
    assert main.count('overdueEnabled ? ["curations", "templates", "purchases"]') == 2
    assert 'api.approvalPending("templates")' not in main


def test_start_screen_shown_first_and_clear_does_not_log_out():
    """[web-ui] 시작 화면: 처음엔 보이고 시간이 다 돼 비울 때만 다시 보이며 로그아웃하지 않는다."""
    html = INDEX.read_text(encoding="utf-8")
    tag = re.search(r"<button\b[^>]*\bid=\"start-screen\"[^>]*>", html)
    assert tag and not re.search(r"\bhidden\b", tag.group(0))
    code = _code(LIBRARIAN_MAIN)
    # 시작 화면을 다시 보이는 건 시계가 부르는 resetAll 하나뿐이고 다른 비우기는 보이지 않는다
    assert code.count("toStart: true") == 2  # 시계의 익명 비우기와 회원 로그아웃 둘
    assert "loggedIn ? memberLogout() : resetAll({ toStart: true })" in code
    assert "onSessionLost() {\n    resetChat();" in code
    assert '$("new-chat").addEventListener("click", () => resetChat());' in code
    # 비우는 길(resetAll, resetChat, memberLogout, showStart)에는 직원 토큰·로그인 화면 이동이 없다
    start = code.index("function showStart()")
    end = code.index('$("composer")')
    clearing = code[start:end]
    assert not re.search(r"goLogin|clearToken|api\.logout|/auth/logout|location\.", clearing)
    assert "if (toStart) showStart();" in clearing


# 이용자 화면의 두 단계 검색

SUGGEST_JS = PUBLIC / "librarian" / "suggest.js"
CHAT_JS = PUBLIC / "librarian" / "chat.js"


def test_two_step_query_limit_matches_server():
    """[web-ui] 긴 입력: 화면의 질의 상한은 서버의 질의 상한과 같고 Enter 갈림이 쓴다."""
    match = re.search(r"export const MAX_QUERY = (\d+);", _code(SUGGEST_JS))
    assert match
    assert int(match.group(1)) == MAX_QUERY_LENGTH
    main = _code(LIBRARIAN_MAIN)
    assert 'import { MAX_QUERY, createSuggest } from "./suggest.js";' in main
    assert "text.length > MAX_QUERY" in main


def test_two_step_top_count():
    """[web-ui] 위 단 권수: 두 단계 결과의 위 단은 찾기 결과의 앞 2권이다."""
    assert re.search(r"export const TWO_STEP_TOP_COUNT = 2;", _code(CHAT_JS))
    assert "found.slice(0, TWO_STEP_TOP_COUNT)" in _code(CHAT_JS)


def test_two_step_enter_flow_and_no_session():
    """[web-ui] 두 단계 결과: 찾기 먼저, 위 단 제외, 사서에게 한 번, 세션을 안 건드린다."""
    chat = _code(CHAT_JS)
    start = chat.index("async function fillLower")
    end = chat.index("function reset()")
    flow = chat[start:end]
    # 찾기 → 주제 검색 순서, 0권·실패는 대화, 401은 로그인 화면
    assert flow.index("api.search(") < flow.index("showTwoStep(text, found)")
    assert "return sendText(text)" in flow
    assert "ui.onUnauthorized()" in flow
    # 아래 단은 위 단의 책을 빼고, 비거나 실패하면 제목째 지운다
    assert "!shown.has(book.library_book_id)" in flow
    assert flow.count("lower.remove()") == 2
    # 사서에게 물어보기는 한 번만 보내고 꺼진다
    assert "if (busy || ask.disabled) return;" in flow
    assert "ask.disabled = true;" in flow
    # 두 단계 결과는 서버 세션을 만들거나 바꾸지 않는다
    assert "sessionId" not in flow and "openMessages" not in flow and "endSession" not in flow
    # 찾는 중의 Enter는 무시한다
    assert "chat.busy || chat.searching" in _code(LIBRARIAN_MAIN)


# 담은 책 화면


def test_basket_add_button_follows_login_class():
    """[web-ui] 담은 책 화면: 로그인 전에는 [담기]가 없고 바깥 클래스 하나로 바로 바뀐다."""
    css = (PUBLIC / "librarian" / "librarian.css").read_text(encoding="utf-8")
    assert re.search(r"\.btn-basket\s*\{\s*display:\s*none", css)
    assert re.search(r"\.app\.logged-in \.btn-basket\s*\{\s*display:\s*inline-block", css)
    code = _code(LIBRARIAN_MAIN)
    body = code[code.index("function renderMember(") :].split("\n}\n")[0]
    assert 'classList.toggle("logged-in", loggedIn)' in body
    # 로그인 전 담기를 로그인 뒤 이어서 하는 길은 없다
    assert "memberBasket" not in code
    assert "then:" not in _code(PUBLIC / "librarian" / "actions.js")


def test_basket_loads_after_login_and_logout_keeps_server_copy():
    """[web-ui] 담은 책 화면: 로그인하면 불러오고, 로그아웃·403은 화면의 사본만 비운다."""
    code = _code(LIBRARIAN_MAIN)
    login = code[code.index("onChange(loggedIn)") :].split("\n  },\n")[0]
    assert "basket.load()" in login
    for name in ("resetAll", "memberLost"):
        body = code[code.index(f"function {name}(") :].split("\n}\n")[0]
        assert "basket.clear();" in body and "clearBasket" not in body, name
    basket_js = _code(PUBLIC / "librarian" / "basket.js")
    clear = basket_js[basket_js.index("clear() {") :].split("\n    },")[0]
    assert "api." not in clear  # 비우기(clear)는 서버를 부르지 않는다
    assert not re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie", basket_js)


def test_basket_mutations_wait_for_server():
    """[web-ui] 담은 책 화면: 서버가 성공한 뒤에 사본을 바꾸고, 실패 문구는 둘뿐이다."""
    basket_js = _code(PUBLIC / "librarian" / "basket.js")
    change = basket_js[basket_js.index("async function change(") :].split("\n  }\n")[0]
    assert change.index("await api.") < change.index("entries.set(") < change.index("catch")
    code = _code(LIBRARIAN_MAIN)
    assert '"담은 책은 10권까지예요"' in code and '"잠시 뒤 다시 눌러 주세요"' in code
    # 401은 로그인 화면, 403은 회원 로그아웃과 로그인 칸
    handler = code[code.index("function basketError(") :].split("\n}\n")[0]
    assert "onUnauthorized()" in handler and "memberLost()" in handler
    assert "actions.openLogin()" in handler


# 장서 가져오기 화면


def _js_table(code: str, name: str) -> dict[str, str]:
    block = code[code.index(f"const {name} = {{") :].split("};")[0]
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block))


def test_import_screen_reads_only_schema_fields():
    """[web-ui] 화면이 읽는 값: 가져오기 화면의 record.·row. 필드는 응답 스키마에 있다."""
    code = _admin_code("imports.js")
    for name, schema in (("record", HoldingImportRead), ("row", HoldingImportRow)):
        used = set(re.findall(rf"\b{name}\.(\w+)", code))
        assert used, name
        assert used <= set(schema.model_fields), (name, used - set(schema.model_fields))
    assert "donor" not in set(re.findall(r"\brow\.(\w+)", code))


def test_import_screen_labels_match_server():
    """[web-ui] 열과 표기의 이름: 열 키·이름이 서버와 같고 표기 넷이 모두 있다."""
    code = _admin_code("imports.js")
    assert _js_table(code, "FIELD_LABELS") == LABELS
    flags = {getattr(import_rows, name) for name in dir(import_rows) if name.startswith("FLAG_")}
    assert len(flags) == 4
    assert set(_js_table(code, "FLAG_LABELS")) == flags


def test_import_apply_confirms_before_each_request():
    """[web-ui] 적용 취소·대량 제적 확인: 확인 뒤에만 요청한다."""
    code = _admin_code("imports.js")
    assert code.index("confirm(APPLY_CONFIRM)") < code.index("api.importApply(id)")
    ask = code.index("confirm(MASS_WITHDRAW_CONFIRM)")
    assert code.index("if (!massWithdraw) throw error;") < ask
    assert ask < code.index("api.importApplyConfirmed(id)")
    assert code.count("api.importApplyConfirmed(") == 1
    entries = _api_entries()
    assert "confirm_withdraw" not in entries["importApply"].split("importApplyConfirmed")[0]
    assert "confirm_withdraw=true" in entries["importApplyConfirmed"]


def test_import_apply_button_only_on_latest_preview():
    """[web-ui] 오래된 미리 보기: [적용]은 가장 최근 기록이 미리 보기일 때만 만든다."""
    code = _admin_code("imports.js")
    assert 'record.status === "preview" && record.id === latestId' in code
    assert code.count('button("적용"') == 1
    assert "latestId = page.items.length ? page.items[0].id : null;" in code


def test_import_delete_button_only_on_preview():
    """[web-ui] 삭제 버튼의 자리: 미리 보기에만 만들고 확인 뒤에만 삭제를 요청한다."""
    code = _admin_code("imports.js")
    assert code.count('button("삭제"') == 1
    start = code.index('if (record.status === "preview") {')
    block = code[start:].split("box.append(actions);")[0]
    assert 'button("삭제"' in block
    assert code.index("confirm(DELETE_CONFIRM)") < code.index("api.importDelete(id)")
    assert code.count("api.importDelete(") == 1
