"""[agent/librarian] 질의 인코더 실행 값: 앱이 인코더를 하나 두고 서버가 끝날 때 닫는다."""

import asyncio
from types import SimpleNamespace

import pytest

from app.central.embedding import GuardedEmbedder
from app.core.config import get_settings
from app.library.api import librarian


def _request() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def test_encoder_is_made_once() -> None:
    """[agent/librarian] 질의 인코더 실행 값 / 인코더를 넘김 (앱의 인코더 하나)"""
    request = _request()
    first = librarian.get_query_encoder(request)
    assert isinstance(first, GuardedEmbedder)
    assert first.timeout == get_settings().embedding_query_timeout_seconds
    assert librarian.get_query_encoder(request) is first

    async def close() -> None:
        await librarian.close_query_encoder(request.app)

    http = request.app.state.query_http
    asyncio.run(close())
    assert http.is_closed and request.app.state.query_encoder is None


def test_encoder_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """[agent/librarian] 질의 인코더 실행 값 / 인코더 없음 (끈 설정)"""
    off = get_settings().model_copy(update={"embedding_query_enabled": False})
    monkeypatch.setattr(librarian, "get_settings", lambda: off)
    assert librarian.get_query_encoder(_request()) is None


def test_lifespan_closes_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """[agent/librarian] 질의 인코더 실행 값 (서버가 끝날 때 닫음)"""
    import app.main as main

    closed: list[bool] = []

    async def fake_purge(open_session, interval: float = 60) -> None:
        await asyncio.sleep(3600)

    async def fake_close(app) -> None:
        closed.append(True)

    class NoEngine:
        async def dispose(self) -> None:
            return None

    async def check() -> None:
        async with main.lifespan(main.app):
            pass

    monkeypatch.setattr(main, "purge_forever", fake_purge)
    monkeypatch.setattr(main, "close_query_encoder", fake_close)
    monkeypatch.setattr(main, "get_engine", lambda: NoEngine())
    asyncio.run(check())
    assert closed == [True]
