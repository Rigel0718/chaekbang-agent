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
from tests.source_helpers import TEST_D4L_KEY, TEST_KAKAO_KEY, FakeSources, d4l_error


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


@pytest.mark.parametrize(
    ("keys", "missing"),
    [
        ((None, "k", "y"), ["LIBRARY_BIGDATA_KEY"]),
        (("d", "", "y"), ["KAKAO_REST_API_KEY"]),
        (("d", "k", None), ["YES24_API_KEY"]),
        (("", None, ""), ["LIBRARY_BIGDATA_KEY", "KAKAO_REST_API_KEY", "YES24_API_KEY"]),
    ],
)
async def test_missing_key(
    keys: tuple,
    missing: list[str],
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """[catalog/book-enrichment] API 키 보호 / 키 미설정"""
    await _pending(session, library_a.id)
    names = ("library_bigdata_key", "kakao_rest_api_key", "yes24_api_key")
    for name, key in zip(names, keys, strict=True):
        monkeypatch.setattr(get_settings(), name, SecretStr(key) if key is not None else None)

    def no_network(*args, **kwargs):
        raise AssertionError("키가 없으면 외부를 부르지 않는다")

    monkeypatch.setattr(httpx.AsyncClient, "get", no_network)
    assert await run(argparse.Namespace(limit=1, retry_failed=False)) == EXIT_PRECONDITION
    err = capsys.readouterr().err
    for name in ("LIBRARY_BIGDATA_KEY", "KAKAO_REST_API_KEY", "YES24_API_KEY"):
        assert (name in err) == (name in missing)
    assert await session.scalar(text("SELECT enrichment_status FROM library_books")) == "pending"


async def test_exit_ok_and_summary(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-enrichment] 나눠서 처리 / limit만큼 처리 (결과 출력)"""
    await _pending(session, library_a.id)
    code = await execute(session, FakeSources().lookup(), limit=1, retry_failed=False)
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
    sources = FakeSources()
    sources.data4library.responses[VALID_ISBN] = d4l_error("인증정보가 일치하지 않습니다.")
    with caplog.at_level(logging.DEBUG):
        code = await execute(session, sources.lookup(), limit=1, retry_failed=False)
    captured = capsys.readouterr()
    assert code == EXIT_STOPPED
    assert "data4library auth_failed" in captured.err
    output = captured.out + captured.err + caplog.text
    assert TEST_D4L_KEY not in output
    assert TEST_KAKAO_KEY not in output


async def test_exit_stopped_on_network_error(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 네트워크 오류 (종료 코드)"""
    await _pending(session, library_a.id)
    sources = FakeSources()
    sources.kakao.responses[VALID_ISBN] = httpx.ConnectError("연결 실패")
    code = await execute(session, sources.lookup(), limit=1, retry_failed=False)
    assert code == EXIT_STOPPED
    assert "kakao upstream_unavailable" in capsys.readouterr().err
