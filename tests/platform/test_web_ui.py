"""[platform/web-ui] 화면 서빙과 화면 코드의 계약. 화면 동작은 design의 브라우저 확인이 본다."""

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.core.config import get_settings
from app.library.schemas.catalog import BookSummary, RelatedBook
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
    "/catalog/suggest": {"GET"},
    "/catalog/search": {"GET"},
    "/catalog/books/{id}/similar": {"GET"},
    "/librarian/messages": {"POST"},
    "/librarian/sessions/{id}": {"DELETE"},
    "/library": {"GET"},
    "/library/guide": {"GET"},
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


# 회원번호의 행선지


def test_member_number_only_in_loan_and_request_bodies():
    """[web-ui] 회원번호를 보내는 곳: `member_number`는 대출·희망도서 본문에만 있다."""
    readers = {PUBLIC / "admin" / "requests.js", PUBLIC / "admin" / "overdue.js"}
    for path in _js_files():
        text = _code(path)
        if path != API_JS and path not in readers:
            assert "member_number" not in text, path
    entries = _api_entries()
    assert {name for name, src in entries.items() if "member_number" in src} == {
        "borrow",
        "requestBook",
    }
    assert "member_number" not in API_JS.read_text(encoding="utf-8").split("export const api")[0]


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
    for path in [*(PUBLIC / "librarian").glob("*.js"), INDEX]:
        text = _code(path) if path.suffix == ".js" else path.read_text(encoding="utf-8")
        assert "logout" not in text.lower(), path
        assert "로그아웃" not in text, path


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


def test_cap_clock_does_not_pause_or_extend():
    """[web-ui] 이용 상한: 답 받는 중에 멈추지 않고 입력해도 늘지 않는다(시작은 첫 입력 한 번)."""
    code = _code(IDLE_JS)
    pause = code[code.index("pause() {") : code.index("resume() {")]
    assert "stopCap" not in pause and "armCap" not in pause
    # 상한을 거는 곳은 비운 뒤 첫 입력(started가 거짓일 때) 한 곳뿐이다
    assert len(re.findall(r"armCap\(\)", code)) == 2  # 정의와 호출
    assert re.search(r"if \(!started\) \{\s*started = true;\s*armCap\(\);", code)


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


def test_admin_overdue_hidden_until_internal():
    """[web-ui] 처음 그린 화면·보이는 조건(관리자): 연체 탭·틀 묶음은 internal 한 곳에서 푼다."""
    html = ADMIN_INDEX.read_text(encoding="utf-8")
    for element_id in ("tab-overdue", "group-templates"):
        tag = re.search(rf"<\w+\b[^>]*\bid=\"{element_id}\"[^>]*>", html)
        assert tag and re.search(r"\bhidden\b", tag.group(0)), element_id
    code = _admin_code("main.js")
    assert len(re.findall(r"loan_mode", code)) == 1
    assert 'library.loan_mode === "internal"' in code
    block = code[code.index('library.loan_mode === "internal"') :].split("}")[0]
    assert block.count('$("tab-overdue").hidden = false;') == 1
    assert block.count('$("group-templates").hidden = false;') == 1
    assert code.count('$("tab-overdue").hidden = false;') == 1
    assert code.count('$("group-templates").hidden = false;') == 1


def test_admin_chat_request_body_keys():
    """[web-ui] 대화 요청의 본문(운영 에이전트): 키는 session_id, message뿐이다."""
    code = _admin_code("chat.js")
    keys = set(re.findall(r"adminOpenMessages\(\s*sessionId \? \{ (\w+):", code))
    keys |= set(re.findall(r"\{ session_id: sessionId, (\w+):", code))
    keys |= set(re.findall(r": \{ (\w+): text \}", code))
    assert keys == {"session_id", "message"}
    assert "member_number" not in code


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
    assert 'method: "PUT"' not in api_text  # 고치기 없음
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
    assert code.count("toStart: true") == 1
    assert "onClear: () => resetAll({ toStart: true })" in code
    assert "onSessionLost() {\n    resetAll();" in code
    assert '$("new-chat").addEventListener("click", () => resetAll());' in code
    # 비우는 길(resetAll, showStart)에는 토큰·로그인·로그아웃이 없다
    start = code.index("function showStart()")
    end = code.index('$("composer")')
    clearing = code[start:end]
    assert not re.search(r"goLogin|clearToken|logout|location\.", clearing, re.IGNORECASE)
    assert "if (toStart) showStart();" in clearing
