"""[platform/web-ui] 화면 문구 규칙: 화면에 나오는 서버 문구와 화면 글자의 검사.

서버 검사는 `app/core`, `app/library`에서 오류(`NotFoundError` 등)와 `HTTPException`에 넘기는 글자와
그 상수를 읽는다(design 결정 5). tool 결과로만 LLM에 가는 모듈은 뺀다(design 결정 4).
"""

import ast
import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.api.purchase_requests import get_list_prices
from app.main import app
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    add_held_book,
    add_holding,
    add_library_book,
    add_member,
    login_member,
)
from tests.purchase_helpers import FakeListPrices, item_body, request_body

ROOT = Path(__file__).resolve().parents[2]
ERROR_CALLS = {
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "InvalidRequestError",
    "LimitExceededError",
    "UnavailableError",
    "HTTPException",
    "ImportFileError",
}
# tool 결과로만 LLM에 가는 모듈(design 결정 4)
TOOL_ONLY = (
    "app/library/tools.py",
    "app/library/analytics/",
    "app/library/services/analytics.py",
    "app/library/recommendation/",
)
# 화면에 나오지 않아 그대로 둔 문구: (파일, 문구 일부, 이유)
KEPT = [
    (
        "app/library/services/holding_imports.py",
        "confirm_withdraw",
        "대량 제적 409. 화면은 이 낱말로 알아보고 자기 확인창을 보인다(design 결정 8)",
    ),
    (
        "app/library/services/curations.py",
        "이 도서관에 없는 책",
        "큐레이션 초안은 tool로만 만든다. 책 id를 LLM에 돌려준다",
    ),
    (
        "app/library/services/curations.py",
        "담을 수 없는 책",
        "큐레이션 초안은 tool로만 만든다. 책 id를 LLM에 돌려준다",
    ),
]
DUAL_PARTICLES = ("을(를)", "이(가)", "은(는)", "과(와)", "으로(로)")


def _in_scope(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel.endswith("_tools.py") or any(rel.startswith(p) for p in TOOL_ONLY):
        return False
    return rel.startswith(("app/core/", "app/library/"))


def _text(node: ast.AST) -> str | None:
    """글자 상수와 f-string의 고정 부분(자리는 `{}`)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else "{}" for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        return None if left is None or right is None else left + right
    return None


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def server_messages() -> Iterator[tuple[str, str]]:
    """(파일, 문구): 오류 호출에 넘기는 글자와, 그 호출이 이름으로 넘기는 모듈 상수."""
    for path in sorted((ROOT / "app").rglob("*.py")):
        if not _in_scope(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {
            target.id: text
            for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            for target in stmt.targets
            if isinstance(target, ast.Name) and (text := _text(stmt.value)) is not None
        }
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in ERROR_CALLS:
                continue
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                text = _text(arg)
                if text is None and isinstance(arg, ast.Name):
                    text = constants.get(arg.id)
                if text and re.search("[가-힣]", text):
                    yield rel, text


def _kept(rel: str, text: str) -> bool:
    return any(rel == f and part in text for f, part, _ in KEPT)


def test_server_messages_found() -> None:
    """검사가 뜻이 있으려면 문구를 충분히 찾아야 한다."""
    found = list(server_messages())
    assert len(found) > 40
    assert any("휴관일" in text or "찾을 수 없어요." in text for _, text in found)


def test_server_message_style() -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 서버 문구의 말투

    "니다"로 끝나는 문장이 없고, "세요"는 "주세요"로만 나온다.
    """
    bad = [
        (rel, text)
        for rel, text in server_messages()
        if not _kept(rel, text)
        and (re.search(r"니다(?=[.\s:]|$)", text) or re.search(r"(?<!주)세요", text))
    ]
    assert not bad, bad


def test_no_dual_particles() -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 겸용 조사 없음"""
    bad = [
        (rel, text)
        for rel, text in server_messages()
        if any(particle in text for particle in DUAL_PARTICLES)
    ]
    assert not bad, bad


# --- API 시나리오 ---


async def test_not_found_without_id(admin_client: AsyncClient, admin_client_b: AsyncClient) -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 없는 대상"""
    theirs = (
        await admin_client_b.post("/library/closures", json={"closed_on": "2026-11-20"})
    ).json()
    res = await admin_client.delete(f"/library/closures/{theirs['id']}")
    assert res.status_code == 404
    assert res.json()["detail"] == "휴관일을 찾을 수 없어요."
    assert str(theirs["id"]) not in res.json()["detail"]


async def test_cannot_borrow_without_status_value(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 빌릴 수 없는 책"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "LOST-1", status="lost")
    await add_member(session, library_a.id, "M0001", phone="01011112222")
    await login_member(kiosk_client, "01011112222")
    res = await kiosk_client.post("/loans", json={"accession_number": "LOST-1"})
    assert res.status_code == 409
    assert res.json()["detail"] == "지금 빌릴 수 없는 책이에요."
    assert "lost" not in res.json()["detail"]


async def test_approval_conflict_particles(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 승인 흐름 문구의 조사"""
    ids = [(await add_held_book(session, library_a.id, title=f"책 {i}"))["id"] for i in range(3)]
    curation = await admin_client.post(
        "/curations",
        json={
            "title": "공룡 특집",
            "intro": "소개",
            "items": [{"library_book_id": i, "reason": "이유"} for i in ids],
        },
    )
    assert curation.status_code == 201, curation.text
    res = await admin_client.post(
        f"/curations/{curation.json()['id']}/reject", json={"reason": "x"}
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "큐레이션이 초안 상태라 반려할 수 없어요."

    created = await admin_client.post(
        "/purchase-requests", json=request_body([item_body(VALID_ISBN)])
    )
    assert created.status_code == 201, created.text
    url = f"/purchase-requests/{created.json()['id']}/reject"
    res = await admin_client.post(url, json={"reason": "x"})
    assert res.status_code == 409
    assert res.json()["detail"] == "구매 요청서가 초안 상태라 반려할 수 없어요."
    assert "(가)" not in res.json()["detail"]


async def test_duplicate_accession_keeps_value(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[platform/web-ui] 화면에 나오는 서버 문구 / 사람이 넣은 값"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "EM0001")
    res = await admin_client.post(
        "/holdings",
        json={
            "library_book_id": book["id"],
            "accession_number": "EM0001",
            "acquisition_type": "donated",
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "이미 쓰는 등록번호예요: EM0001"


async def test_no_overdue_template_message(admin_client: AsyncClient) -> None:
    """[platform/web-ui] 실패 안내 / 연체 안내 양식이 없음 (서버는 없다는 말까지만)"""
    res = await admin_client.get("/overdue-notices/today")
    assert res.status_code == 409
    assert res.json()["detail"] == "승인한 연체 안내 양식이 없어요."


@pytest.fixture
async def down_prices(_app: None) -> AsyncIterator[FakeListPrices]:
    fake = FakeListPrices({VALID_ISBN: 15000})
    fake.unavailable = True
    app.dependency_overrides[get_list_prices] = lambda: fake
    yield fake


async def test_price_lookup_down_message(
    admin_client: AsyncClient, down_prices: FakeListPrices
) -> None:
    """[platform/web-ui] 실패 안내 / 정가 조회 장애 (서버 문구)"""
    created = await admin_client.post(
        "/purchase-requests", json=request_body([item_body(VALID_ISBN)])
    )
    request_id = created.json()["id"]
    assert (await admin_client.post(f"/purchase-requests/{request_id}/submit")).status_code == 200
    res = await admin_client.post(f"/purchase-requests/{request_id}/approve")
    assert res.status_code == 503
    assert res.json()["detail"] == "지금 정가를 조회할 수 없어요. 잠시 뒤 다시 해 주세요."


async def test_member_required_message(kiosk_client: AsyncClient) -> None:
    """[circulation/member-login] 회원 세션 / 회원 토큰이 없음 (문구)"""
    res = await kiosk_client.get("/basket")
    assert res.status_code == 403
    assert res.json()["detail"] == "회원 로그인을 해 주세요."


# --- 화면 글자 검사 ---

PUBLIC = ROOT / "app" / "web" / "public"
# "서명"은 "도서명" 안에서만 나올 수 있다
BANNED_WORDS = (
    "사본",
    "장서",
    "소장",
    "운영 대화",
    "운영 에이전트",
    "안내문 틀",
    "책방",
    "책 이름",
    "이용 가능",
    "지울까요",
)
OLD_FAILURES = ("시도해 주세요", "다시 눌러 주세요", "다시 열어 보세요")


def _strip_comments(source: str) -> str:
    source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(^|\s)//.*$", r"\1", source, flags=re.M)


def _screen_files() -> dict[str, str]:
    """화면의 HTML·JS에서 주석을 뺀 글자. 키는 `public/` 아래 경로."""
    return {
        path.relative_to(PUBLIC).as_posix(): _strip_comments(path.read_text(encoding="utf-8"))
        for path in sorted(PUBLIC.rglob("*"))
        if path.suffix in {".html", ".js"}
    }


def _hits(words: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(name, w) for name, text in _screen_files().items() for w in words if w in text]


def _buttons() -> set[str]:
    """HTML의 버튼 글자와 스크립트의 `button("…"` 글자."""
    found: set[str] = set()
    for name, text in _screen_files().items():
        if name.endswith(".html"):
            found |= {m.strip() for m in re.findall(r"<button[^>]*>\s*([^<]+?)\s*<", text)}
        else:
            found |= set(re.findall(r'button\("([^"]+)"', text))
            found |= set(re.findall(r'_BUTTON = "([^"]+)"', text))
    return found


def test_banned_words() -> None:
    """[platform/web-ui] 화면 용어 / 쓰지 않는 말"""
    assert not _hits(BANNED_WORDS)
    files = _screen_files()
    assert not [n for n, t in files.items() if "서명" in t.replace("도서명", "")]
    assert not [n for n, t in files.items() if "사서" in t.replace("AI 사서", "")]


def test_tabs_and_login_title() -> None:
    """[platform/web-ui] 화면 용어 / 탭과 로그인 화면 이름"""
    admin = _screen_files()["admin/index.html"]
    tabs = [m.strip() for m in re.findall(r'data-tab="[a-z]+"[^>]*>([^<]*)<', admin)]
    assert tabs == [
        "AI 도우미",
        "승인 목록",
        "희망도서",
        "오늘의 연체",
        "책 가져오기",
        "책 목록",
        "회원",
        "휴관일",
    ]
    login = _screen_files()["login/index.html"]
    assert "<title>직원 로그인</title>" in login and "<h1>직원 로그인</h1>" in login


def test_changed_buttons() -> None:
    """[platform/web-ui] 화면 버튼 / 바뀐 버튼"""
    buttons = _buttons()
    assert not buttons & {"더하기", "반려하기", "고치기", "사서에게 물어보기"}
    assert {"등록", "보내기", "수정", "처리 완료", "AI 사서에게 묻기"} <= buttons


def test_librarian_buttons_kept() -> None:
    """[platform/web-ui] 화면 버튼 / AI 사서가 안내하는 버튼"""
    html = _screen_files()["librarian/index.html"]
    assert ">대출·반납</button>" in html and ">희망도서 신청</button>" in html


def test_screen_text_style() -> None:
    """[platform/web-ui] 화면 문장의 말투와 마침표 / 화면 문구의 말투: "니다"로 끝나는 문장 없음"""
    bad = [
        (name, line.strip())
        for name, text in _screen_files().items()
        for line in text.splitlines()
        if re.search(r"니다(?=[.\s\"'`<(]|$)", line)
    ]
    assert not bad, bad


def test_search_empty_text() -> None:
    """[platform/web-ui] 화면 문장의 말투와 마침표 / 이용자 검색 결과 없음"""
    chat = _screen_files()["librarian/chat.js"]
    assert '"찾은 책이 없어요."' in chat
    assert "물어보세요" not in chat


def test_single_failure_text() -> None:
    """[platform/web-ui] 실패 안내 / 실패 문구 하나"""
    assert not _hits(OLD_FAILURES)
    files = _screen_files()
    defined = [n for n, t in files.items() if re.search(r"const GENERIC_ERROR =", t)]
    assert defined == ["shared/api.js"]
    assert 'export const GENERIC_ERROR = "잠시 뒤 다시 해 주세요.";' in files["shared/api.js"]


def test_no_status_number_in_error() -> None:
    """[platform/web-ui] 실패 안내 / 상태 번호 없음"""
    api = _screen_files()["shared/api.js"]
    body = api[api.index("export class ApiError") : api.index("this.status = status")]
    assert "GENERIC_ERROR" in body
    assert "${status}" not in api and "요청에 실패" not in api


def test_approval_error_not_appended() -> None:
    """[platform/web-ui] 실패 안내 / 정가 조회 장애 (503 갈래가 서버 문구에 덧붙이지 않음)"""
    approvals = _screen_files()["admin/approvals.js"]
    assert "errorLine.textContent = error.detail || GENERIC_ERROR;" in approvals
    assert "error.status === 503" not in approvals


def _confirm_texts() -> list[str]:
    """확인창 문구: `confirm("…")`의 글자와, `confirm`에 넘기는 상수·표의 글자."""
    texts: list[str] = []
    for name, source in _screen_files().items():
        if not name.startswith("admin/"):
            continue
        texts += re.findall(r'confirm\("([^"]+)"\)', source)
        texts += re.findall(r'const \w+_CONFIRM =\s*"([^"]+)"', source)
        table = re.search(r"const APPROVE_CONFIRM = \{(.*?)\};", source, re.S)
        if table:
            texts += re.findall(r'"([^"]+)"', table.group(1))
    return texts


def test_confirm_question_first() -> None:
    """[platform/web-ui] 확인창 / 질문 먼저"""
    texts = _confirm_texts()
    assert len(texts) >= 12, texts
    bad = [t for t in texts if not re.match(r"[^.?]*까요\?", t) or "확인을 눌러" in t]
    assert not bad, bad


def test_delete_confirms_use_delete() -> None:
    """[platform/web-ui] 확인창 / 버튼과 같은 동사"""
    files = _screen_files()
    for name in ("admin/closures.js", "admin/members.js", "admin/imports.js"):
        text = re.search(r'const DELETE_CONFIRM =\s*"([^"]+)"', files[name])
        assert text and "삭제할까요?" in text.group(1), name
