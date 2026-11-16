"""[platform/experiment-collection] 실험 장서의 정보나루·카카오 값 받기. 가짜 출처로 돈다."""

import json
from pathlib import Path

import pytest

from app.central.external.http import SourceStopped, StopReason
from evals.collection import sources as sources_module
from evals.collection.sources import (
    EXIT_OK,
    EXIT_PRECONDITION,
    FOUND,
    NOT_FOUND,
    Target,
    dry_run,
    fetch,
    load_document,
    pending,
    targets,
)
from tests.helpers import make_isbn
from tests.source_helpers import d4l_book, kakao_document
from tests.yes24_helpers import item

ISBNS = [make_isbn(n) for n in range(600, 605)]


def _books(n: int = 5) -> list[Target]:
    return [Target(isbn, "toddler" if i % 2 else "essay") for i, isbn in enumerate(ISBNS[:n])]


class FakeFetchers:
    """출처마다 호출을 기록하고, 정해 둔 ISBN에서 결과 없음이나 중단을 낸다."""

    def __init__(self) -> None:
        self.calls: dict[str, list[str]] = {"data4library": [], "kakao": []}
        self.empty: dict[str, set[str]] = {"data4library": set(), "kakao": set()}
        self.stop: dict[str, dict[str, StopReason]] = {"data4library": {}, "kakao": {}}

    def __getitem__(self, source: str):
        async def call(isbn: str) -> list[dict]:
            if isbn in self.stop[source]:
                raise SourceStopped(source, self.stop[source][isbn])
            self.calls[source].append(isbn)
            if isbn in self.empty[source]:
                return []
            if source == "data4library":
                return [d4l_book(isbn)]
            return [kakao_document(isbn, sale_price=12345, status="품절임박")]

        return call


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def test_records(tmp_path: Path) -> None:
    """[platform/experiment-collection] 새 출처 더 받기 / 기록 내용"""
    path = tmp_path / "sources.json"
    books = _books(3)
    result = await fetch(FakeFetchers(), books, path)
    document = _read(path)
    assert document["fetched_on"]
    assert document["sources"] == ["data4library", "kakao"]
    assert [row["isbn"] for row in document["books"]] == [b.isbn for b in books]
    for row, book in zip(document["books"], books, strict=True):
        assert row["field"] == book.field
        assert row["data4library"]["status"] == FOUND
        assert row["data4library"]["books"][0]["isbn13"] == book.isbn
        assert row["kakao"]["status"] == FOUND
    assert result.pending == {"data4library": 0, "kakao": 0}


async def test_found_in_one_source(tmp_path: Path) -> None:
    """[platform/experiment-collection] 새 출처 더 받기 / 한 출처에만 있는 책"""
    path = tmp_path / "sources.json"
    fake = FakeFetchers()
    fake.empty["data4library"].add(ISBNS[1])
    await fetch(fake, _books(3), path)
    row = _read(path)["books"][1]
    assert row["data4library"] == {"status": NOT_FOUND, "books": []}
    assert row["kakao"]["status"] == FOUND
    assert row["kakao"]["documents"]


async def test_volatile_values_not_stored(tmp_path: Path) -> None:
    """[platform/experiment-collection] 새 출처 더 받기 / 변동 정보 미저장"""
    path = tmp_path / "sources.json"
    await fetch(FakeFetchers(), _books(2), path)
    text = path.read_text(encoding="utf-8")
    assert "sale_price" not in text and "12345" not in text
    assert '"status": "품절임박"' not in text and "품절임박" not in text


async def test_yes24_is_not_called(tmp_path: Path) -> None:
    """[platform/experiment-collection] 새 출처 더 받기 / YES24 원본 유지"""
    yes24_file = tmp_path / "yes24.json"
    original = {
        "fetched_on": "2026-11-15",
        "books": [{"field": "toddler", "rank": 1, "item": item(isbn)} for isbn in ISBNS[:2]],
    }
    yes24_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    before = yes24_file.read_bytes()
    books = targets(yes24_file)
    fake = FakeFetchers()
    await fetch(fake, books, tmp_path / "sources.json")
    assert yes24_file.read_bytes() == before
    assert set(fake.calls) == {"data4library", "kakao"}  # YES24 호출 자리가 없다
    assert [b.isbn for b in books] == sorted(ISBNS[:2])


async def test_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """[platform/experiment-collection] 새 출처 더 받기 / 호출 수 미리 보기"""
    path = tmp_path / "sources.json"
    assert dry_run(_books(5), path) == EXIT_OK
    out = capsys.readouterr().out
    assert "data4library: 남은 호출 5회" in out and "kakao: 남은 호출 5회" in out
    assert not path.exists()


async def test_data4library_limit_continues_kakao(tmp_path: Path) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 / 정보나루 한도 초과"""
    path = tmp_path / "sources.json"
    fake = FakeFetchers()
    fake.stop["data4library"][ISBNS[2]] = StopReason.RATE_LIMITED
    result = await fetch(fake, _books(5), path)
    assert fake.calls["kakao"] == ISBNS[:5]
    assert fake.calls["data4library"] == ISBNS[:2]
    assert result.stopped == {"data4library": "rate_limited"}
    assert result.pending == {"data4library": 3, "kakao": 0}
    assert pending(_read(path)) == {"data4library": 3, "kakao": 0}


async def test_resume_data4library_only(tmp_path: Path) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 / 정보나루만 이어 받기"""
    path = tmp_path / "sources.json"
    first = FakeFetchers()
    first.stop["data4library"][ISBNS[2]] = StopReason.AUTH_FAILED
    await fetch(first, _books(5), path)
    second = FakeFetchers()
    result = await fetch(second, _books(5), path)
    assert second.calls["kakao"] == []
    assert second.calls["data4library"] == ISBNS[2:5]
    assert result.pending == {"data4library": 0, "kakao": 0}


async def test_kakao_failure_stops(tmp_path: Path) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 / 카카오 장애"""
    path = tmp_path / "sources.json"
    fake = FakeFetchers()
    fake.stop["kakao"][ISBNS[2]] = StopReason.UPSTREAM_UNAVAILABLE
    with pytest.raises(SourceStopped):
        await fetch(fake, _books(5), path)
    document = _read(path)
    done = [row["isbn"] for row in document["books"] if row["kakao"] is not None]
    assert done == ISBNS[:2]


async def test_already_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 / 이미 다 받음"""
    path = tmp_path / "sources.json"
    yes24_file = tmp_path / "yes24.json"
    original = {
        "fetched_on": "2026-11-15",
        "books": [{"field": "toddler", "rank": 1, "item": item(isbn)} for isbn in ISBNS[:2]],
    }
    yes24_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    await fetch(FakeFetchers(), targets(yes24_file), path)
    before = path.read_bytes()
    monkeypatch.setattr(sources_module, "YES24_FILE", yes24_file)
    monkeypatch.setattr(sources_module, "SOURCES_FILE", path)
    monkeypatch.setattr(sources_module, "targets", lambda: targets(yes24_file))

    def no_network(*args, **kwargs):
        raise AssertionError("다 받았으면 외부를 부르지 않는다")

    monkeypatch.setattr(sources_module.httpx.AsyncClient, "get", no_network)
    assert await sources_module.run([]) == EXIT_PRECONDITION
    assert "이미 다 받았습니다" in capsys.readouterr().err
    assert path.read_bytes() == before


def test_mismatched_file_is_rejected(tmp_path: Path) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 (입력과 다른 파일은 잇지 않는다)"""
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"fetched_on": None, "books": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="ISBN"):
        load_document(path, _books(2))


async def test_missing_yes24_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 출처마다 이어 받기 (YES24 원본 파일 없음은 전제 조건)"""
    missing = tmp_path / "none.json"
    monkeypatch.setattr(sources_module, "targets", lambda: targets(missing))
    assert await sources_module.run([]) == EXIT_PRECONDITION
    assert "YES24 원본" in capsys.readouterr().err
