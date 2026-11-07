"""[catalog/book-enrichment] 운영자 스크립트: 인자, 키, 종료 코드."""

import argparse
import logging

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from scripts.enrich_books import EXIT_OK, EXIT_PRECONDITION, EXIT_STOPPED, execute, parse_args, run
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, add_holding, add_library_book
from tests.yes24_helpers import TEST_API_KEY, FakeYes24, error


async def _pending(session: AsyncSession, library_id: int) -> None:
    book = await add_library_book(session, library_id)
    await add_holding(
        session, library_id, book["id"], "A-1", acquisition_type="donated", purchase_price=None
    )


@pytest.mark.parametrize("argv", [["--limit", "0"], ["--limit", "-1"], ["--limit", "많이"]])
def test_invalid_limit(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """[catalog/book-enrichment] 나눠서 처리 / 잘못된 limit"""
    with pytest.raises(SystemExit) as caught:
        parse_args(argv)
    assert caught.value.code == EXIT_PRECONDITION
    assert capsys.readouterr().err


def test_default_args() -> None:
    """[catalog/book-enrichment] 나눠서 처리 (기본 limit 100)"""
    args = parse_args([])
    assert (args.limit, args.retry_failed) == (100, False)
    assert parse_args(["--retry-failed", "--limit", "5"]).retry_failed


@pytest.mark.parametrize("key", [None, SecretStr("")])
async def test_missing_key(
    key,
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """[catalog/book-enrichment] API 키 보호 / 키 미설정"""
    await _pending(session, library_a.id)
    monkeypatch.setattr(get_settings(), "yes24_api_key", key)
    assert await run(argparse.Namespace(limit=1, retry_failed=False)) == EXIT_PRECONDITION
    assert "YES24_API_KEY" in capsys.readouterr().err
    assert await session.scalar(text("SELECT enrichment_status FROM library_books")) == "pending"


async def test_exit_ok_and_summary(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-enrichment] 나눠서 처리 / limit만큼 처리 (결과 출력)"""
    await _pending(session, library_a.id)
    code = await execute(session, FakeYes24().client(), limit=1, retry_failed=False)
    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "처리 1건" in out and "남은 처리 대기 0건" in out


async def test_exit_stopped_without_key(
    session: AsyncSession,
    library_a: Tenant,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """[catalog/book-enrichment] API 키 보호 / 오류에 키 없음"""
    await _pending(session, library_a.id)
    yes24 = FakeYes24()
    yes24.responses[VALID_ISBN] = error(401, "AUTH_002")
    with caplog.at_level(logging.DEBUG):
        code = await execute(session, yes24.client(), limit=1, retry_failed=False)
    captured = capsys.readouterr()
    assert code == EXIT_STOPPED
    assert "auth_failed" in captured.err
    assert TEST_API_KEY not in captured.out + captured.err + caplog.text


async def test_exit_stopped_on_network_error(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 네트워크 오류 (종료 코드)"""
    await _pending(session, library_a.id)
    yes24 = FakeYes24()
    yes24.responses[VALID_ISBN] = httpx.ConnectError("연결 실패")
    code = await execute(session, yes24.client(), limit=1, retry_failed=False)
    assert code == EXIT_STOPPED
    assert "upstream_unavailable" in capsys.readouterr().err
