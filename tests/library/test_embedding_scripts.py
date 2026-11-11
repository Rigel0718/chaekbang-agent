"""[catalog/book-embeddings] 운영자 스크립트: 인자, 출력, 종료 코드, 확인용 조회."""

import argparse

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import EmbeddingFailure
from app.core.config import get_settings
from evals.librarian.catalog import Sample
from scripts import embedding_search
from scripts.embed_books import EXIT_OK, EXIT_PRECONDITION, EXIT_STOPPED, execute, parse_args
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.external.test_tei_embedder import FakeTei
from tests.helpers import add_held_book, make_isbn


async def _count(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM book_embeddings"))


async def _run(session: AsyncSession, embedder, *, full: bool = False, **options) -> int:
    options.setdefault("library_id", None)
    options.setdefault("batch_size", 32)
    return await execute(session, embedder, full=full, **options)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--full", "--incremental"],
        ["--full", "--batch-size", "0"],
        ["--full", "--library-id", "가"],
    ],
)
def test_invalid_arguments(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 잘못된 인자"""
    with pytest.raises(SystemExit) as caught:
        parse_args(argv)
    assert caught.value.code == EXIT_PRECONDITION
    assert "usage" in capsys.readouterr().err


def test_arguments() -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 (인자)"""
    args = parse_args(["--incremental", "--library-id", "3", "--batch-size", "8"])
    assert (args.full, args.incremental, args.library_id, args.batch_size) == (False, True, 3, 8)
    assert parse_args(["--full"]).batch_size is None


async def test_summary_and_exit_ok(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 완료 출력"""
    for i in range(3):
        await add_held_book(session, library_a.id, title=f"먼저{i}")
    assert await _run(session, FakeEmbedder(), full=True) == EXIT_OK
    for i in range(2):
        await add_held_book(session, library_a.id, title=f"나중{i}")
    capsys.readouterr()

    assert await _run(session, FakeEmbedder(), batch_size=2) == EXIT_OK
    out = capsys.readouterr().out
    assert "대상 5권: 인코딩 2건, 건너뜀 3건" in out
    assert "모델 fake-model, 텍스트 버전 1" in out
    assert "[2/5]" in out and "[5/5] 인코딩 2, 건너뜀 3" in out


async def test_unreachable_server_stops_with_hint(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 임베딩 서버가 꺼져 있음"""
    await add_held_book(session, library_a.id)
    tei = FakeTei()
    tei.error = httpx.ConnectError("connection refused")
    assert await _run(session, tei.embedder(), full=True) == EXIT_STOPPED
    err = capsys.readouterr().err
    assert (
        "연결할 수 없습니다" in err and "docker compose --profile embedding up -d embedder" in err
    )
    assert await _count(session) == 0


async def test_server_error_mid_run_exits_stopped(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 중간 실패 뒤 이어 하기 (종료 코드)"""
    for i in range(5):
        await add_held_book(session, library_a.id, title=f"책{i}")
    code = await _run(session, FakeEmbedder(fail_on=2), full=True, batch_size=2)
    captured = capsys.readouterr()
    assert code == EXIT_STOPPED
    assert "인코딩 2건" in captured.out and "server_error" in captured.err
    assert await _count(session) == 2

    assert await _run(session, FakeEmbedder(), batch_size=2) == EXIT_OK
    assert "인코딩 3건, 건너뜀 2건" in capsys.readouterr().out


async def test_other_model_is_a_precondition_error(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 다른 모델이 떠 있음"""
    await add_held_book(session, library_a.id)
    tei = FakeTei(info={"served_model_name": "BAAI/bge-m3", "max_input_length": 512})
    assert await _run(session, tei.embedder(), full=True) == EXIT_PRECONDITION
    assert "BAAI/bge-m3" in capsys.readouterr().err
    assert tei.bodies == [] and await _count(session) == 0


async def test_unknown_library(session: AsyncSession, capsys: pytest.CaptureFixture[str]) -> None:
    """[catalog/book-embeddings] 적재 대상 / 기관을 지정한 실행 (없는 기관)"""
    assert await _run(session, FakeEmbedder(), full=True, library_id=999_999) == EXIT_PRECONDITION
    assert "999999" in capsys.readouterr().err


async def test_search_prints_top_five(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 유사도 순서 (확인 스크립트 출력)"""
    cosines = {"가": 0.2, "나": 0.9, "다": 0.5, "라": 0.7, "마": 0.1, "바": 0.3}
    for title in cosines:
        await add_held_book(session, library_a.id, title=title, author=f"{title} 저자")
    await add_held_book(session, library_b.id, title="남의 책")
    embedder = FakeEmbedder(
        vectors={"질의": unit(1), "남의": unit(1), **{t: toward(c) for t, c in cosines.items()}}
    )
    await _run(session, embedder, full=True)
    capsys.readouterr()

    code = await embedding_search.execute(session, embedder, library_a.id, "질의")
    lines = capsys.readouterr().out.splitlines()
    assert code == EXIT_OK
    assert lines[1:] == [
        "1. 0.900  나 / 나 저자",
        "2. 0.700  라 / 라 저자",
        "3. 0.500  다 / 다 저자",
        "4. 0.300  바 / 바 저자",
        "5. 0.200  가 / 가 저자",
    ]


async def test_search_without_embeddings(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 적재 전 조회 (확인 스크립트 안내)"""
    assert await embedding_search.execute(session, FakeEmbedder(), library_a.id, "질의") == EXIT_OK
    assert "embed_books.py" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv", [["질의"], ["질의", "--sample", "--library-id", "1"], ["--sample"], [" ", "--sample"]]
)
def test_search_invalid_arguments(argv: list[str]) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 (확인 스크립트 인자)"""
    with pytest.raises(SystemExit) as caught:
        embedding_search.parse_args(argv)
    assert caught.value.code == EXIT_PRECONDITION


def _sample(count: int) -> Sample:
    return Sample(
        "2026-11-11",
        [
            {
                "isbn13": make_isbn(700 + i),
                "title": f"표본 책 {i}",
                "author": "표본 저자",
                "description": f"표본 소개 {i}",
            }
            for i in range(count)
        ],
    )


async def test_sample_run_loads_then_reruns_with_zero(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 증분 재실행은 0건 (표본 확인 방식)"""
    embedder = FakeEmbedder()
    code = await embedding_search.execute_sample(
        session, embedder, _sample(12), "표본 책 3", batch_size=5
    )
    out = capsys.readouterr().out
    assert code == EXIT_OK
    targets = sum(len(call) for call in embedder.document_calls)
    assert f"전체 적재: 대상 {targets}권, 인코딩 {targets}건" in out
    assert f"증분 적재: 인코딩 0건, 건너뜀 {targets}건" in out
    assert out.count("표본 저자") == 5


async def test_sample_run_stops_when_server_fails(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 임베딩 서버가 꺼져 있음 (표본)"""
    embedder = FakeEmbedder(fail_on=1, failure=EmbeddingFailure.UNREACHABLE)
    code = await embedding_search.execute_sample(
        session, embedder, _sample(3), "질의", batch_size=5
    )
    assert code == EXIT_STOPPED
    assert "연결할 수 없습니다" in capsys.readouterr().err


async def test_sample_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 (표본 파일이 없을 때의 안내)"""
    monkeypatch.setattr(embedding_search, "DATA_FILE", tmp_path / "없음.json")
    args = argparse.Namespace(query="질의", sample=True, library_id=None)
    assert await embedding_search.run(args) == EXIT_PRECONDITION
    assert "표본이 없습니다" in capsys.readouterr().err
    assert get_settings().test_database_url
