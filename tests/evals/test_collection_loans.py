"""[platform/experiment-collection] 실험 장서의 정보나루 대출 신호 받기. 가짜 정보나루로 돈다."""

import contextlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.central.external.data4library.client import popular_loans, usage_analysis
from app.central.external.data4library.parsing import PopularLoans, UsageAnalysis
from app.central.external.http import SourceStopped, StopReason
from evals.collection import loans as loans_module
from evals.collection.loans import (
    CONDITIONS,
    EXIT_OK,
    EXIT_PRECONDITION,
    Holding,
    dry_run,
    fetch,
    loan_targets,
    overlap_lines,
    pending,
    seed_lines,
)
from tests.helpers import make_isbn
from tests.source_helpers import (
    d4l_list_book,
    d4l_not_found,
    d4l_popular,
    d4l_popular_doc,
    d4l_usage,
    make_d4l_client,
)

ISBNS = [make_isbn(n) for n in range(700, 705)]
TODAY = date(2026, 11, 18)


class FakeLoans:
    """이용 분석·인기 호출을 기록하고, 정해 둔 ISBN에서 찾지 못함이나 중단을 낸다."""

    def __init__(self) -> None:
        self.usage_calls: list[str] = []
        self.popular_calls: list[tuple[str, date, date]] = []
        self.missing: set[str] = set()
        self.stop: dict[str, StopReason] = {}

    async def usage(self, isbn: str) -> UsageAnalysis | None:
        if isbn in self.stop:
            raise SourceStopped("data4library", self.stop[isbn])
        self.usage_calls.append(isbn)
        if isbn in self.missing:
            return None
        return UsageAnalysis((ISBNS[0], ISBNS[1]), (ISBNS[2],), (), 12)

    async def popular(self, group, start: date, end: date) -> PopularLoans:  # noqa: ANN001
        self.popular_calls.append((group.key, start, end))
        return PopularLoans((ISBNS[3], ISBNS[4]), (90, 80))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sources(*rows: tuple[str, str | None]) -> dict:
    return {
        "books": [{"isbn": isbn, "data4library": {"status": s} if s else None} for isbn, s in rows]
    }


def test_targets() -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 / 대상 ISBN"""
    sources = _sources(
        (ISBNS[0], "found"), (ISBNS[1], "found"), (ISBNS[2], "not_found"), (ISBNS[3], "found")
    )
    held = {ISBNS[0], ISBNS[1], ISBNS[2]}  # ISBNS[3]은 ISBN 없이 넣은 책(공식 서지로 소장 안 함)
    assert loan_targets(sources, held) == [ISBNS[0], ISBNS[1]]


async def test_fetch_records(tmp_path: Path) -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 / 기록 내용"""
    path = tmp_path / "loans.json"
    fake = FakeLoans()
    fake.missing.add(ISBNS[1])
    result = await fetch(fake.usage, fake.popular, ISBNS[:2], path, today=TODAY)
    document = _read(path)
    assert document["fetched_on"] == "2026-11-18"
    assert document["usage"][ISBNS[0]] == {
        "status": "found",
        "co_loans": [ISBNS[0], ISBNS[1]],
        "mania": [ISBNS[2]],
        "reader": [],
        "loan_count": 12,
    }
    assert document["usage"][ISBNS[1]] == {"status": "not_found"}
    assert sorted(document["popular"]) == sorted(c.key for c in CONDITIONS)
    assert len(CONDITIONS) == 8
    children = document["popular"]["children-365"]
    assert (children["start"], children["end"]) == ("2025-11-18", "2026-11-17")
    assert children["isbns"] == [ISBNS[3], ISBNS[4]]
    assert result.called == {"usageAnalysisList": 2, "loanItemSrch": 8}
    assert result.stopped is None


async def test_values_not_kept(tmp_path: Path) -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 / 남기지 않는 값"""

    def handler(request):  # noqa: ANN001, ANN202
        if request.url.path.endswith("/usageAnalysisList"):
            if request.url.params["isbn13"] == ISBNS[1]:
                return d4l_not_found()
            return d4l_usage([d4l_list_book(ISBNS[2])], mania=[d4l_list_book(ISBNS[3])])
        return d4l_popular(d4l_popular_doc(ISBNS[4], 1))

    client = make_d4l_client(handler)
    path = tmp_path / "loans.json"
    await fetch(
        lambda isbn: usage_analysis(client, isbn),
        lambda group, start, end: popular_loans(client, group, start, end, 1000),
        ISBNS[:2],
        path,
        today=TODAY,
    )
    text = path.read_text(encoding="utf-8")
    for value in ("image.example", "bookImageURL", "함께 빌린 책", "기준 책", "우정", "인기 책"):
        assert value not in text
    assert _read(path)["usage"][ISBNS[0]]["co_loans"] == [ISBNS[2]]


async def test_other_sources_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 / 다른 출처를 부르지 않음"""
    from evals.collection import sources as sources_module

    def no_other(*args, **kwargs):
        raise AssertionError("카카오·YES24는 부르지 않는다")

    monkeypatch.setattr(sources_module, "raw_documents_by_isbn", no_other)
    sources_file = tmp_path / "sources.json"
    sources_file.write_text("{}", encoding="utf-8")
    before = sources_file.read_bytes()
    fake = FakeLoans()
    await fetch(fake.usage, fake.popular, ISBNS[:1], tmp_path / "loans.json", today=TODAY)
    assert sources_file.read_bytes() == before
    assert fake.usage_calls == ISBNS[:1]


def test_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 / 호출 수 미리 보기"""
    assert dry_run(ISBNS[:3], tmp_path / "loans.json") == EXIT_OK
    out = capsys.readouterr().out
    assert "usageAnalysisList: 남은 호출 3회" in out
    assert "loanItemSrch: 남은 호출 8회" in out
    assert "합계 11회" in out
    assert not (tmp_path / "loans.json").exists()


async def test_rate_limited_then_resume(tmp_path: Path) -> None:
    """[platform/experiment-collection] 대출 신호 이어 받기 / 한도 초과, 이어 받기"""
    path = tmp_path / "loans.json"
    fake = FakeLoans()
    fake.stop[ISBNS[2]] = StopReason.RATE_LIMITED
    result = await fetch(fake.usage, fake.popular, ISBNS, path, today=TODAY)
    assert result.stopped == "rate_limited"
    assert result.pending == {"usageAnalysisList": 3, "loanItemSrch": 8}
    usage = _read(path)["usage"]
    assert [isbn for isbn in ISBNS if usage[isbn] is not None] == ISBNS[:2]
    fake.stop.clear()
    again = FakeLoans()
    result = await fetch(again.usage, again.popular, ISBNS, path, today=TODAY)
    assert again.usage_calls == ISBNS[2:]
    assert len(again.popular_calls) == 8
    assert result.pending == {"usageAnalysisList": 0, "loanItemSrch": 0}


async def test_already_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/experiment-collection] 대출 신호 이어 받기 / 이미 다 받음"""
    path = tmp_path / "loans.json"
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps(_sources((ISBNS[0], "found"))), encoding="utf-8")
    fake = FakeLoans()
    await fetch(fake.usage, fake.popular, ISBNS[:1], path, today=TODAY)
    before = path.read_bytes()

    @contextlib.asynccontextmanager
    async def no_session():
        yield None

    async def library_id(session):  # noqa: ANN001, ANN202
        return 1

    async def held(session, library_id):  # noqa: ANN001, ANN202
        return {ISBNS[0]}

    def no_network(*args, **kwargs):
        raise AssertionError("다 받았으면 외부를 부르지 않는다")

    monkeypatch.setattr(loans_module, "LOANS_FILE", path)
    monkeypatch.setattr(loans_module, "SOURCES_FILE", sources_file)
    monkeypatch.setattr(loans_module, "get_sessionmaker", lambda: no_session)
    monkeypatch.setattr(loans_module, "experiment_library_id", library_id)
    monkeypatch.setattr(loans_module, "held_official_isbns", held)
    monkeypatch.setattr(loans_module.httpx.AsyncClient, "get", no_network)
    assert await loans_module.run([]) == EXIT_PRECONDITION
    assert "이미 다 받았습니다" in capsys.readouterr().err
    assert path.read_bytes() == before


def test_mismatched_file_is_rejected(tmp_path: Path) -> None:
    """[platform/experiment-collection] 대출 신호 이어 받기 (대상과 다른 파일은 잇지 않는다)"""
    path = tmp_path / "loans.json"
    path.write_text(json.dumps({"fetched_on": None, "usage": {}, "popular": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="ISBN"):
        loans_module.load_document(path, ISBNS[:1])
    assert pending({"usage": {ISBNS[0]: None}, "popular": {"x": None}}) == {
        "usageAnalysisList": 1,
        "loanItemSrch": 1,
    }


def test_overlap_counts() -> None:
    """[platform/experiment-collection] 정보나루 대출 신호 받기 (소장 겹침 세기)"""
    document = {
        "usage": {
            ISBNS[0]: {
                "status": "found",
                "co_loans": [ISBNS[1], ISBNS[2], "x"],
                "mania": [],
                "reader": [],
            },
            ISBNS[1]: {"status": "found", "co_loans": ["y"], "mania": [], "reader": []},
            ISBNS[2]: {"status": "not_found"},
            ISBNS[3]: None,
        },
        "popular": {
            "children-365": {"start": "a", "end": "b", "isbns": [ISBNS[1], "z"], "loan_counts": []},
            "all-90": None,
        },
    }
    held = {
        ISBNS[0]: Holding(1, False, True),
        ISBNS[1]: Holding(2, True, True),
        ISBNS[2]: Holding(3, False, False),
    }
    lines = overlap_lines(document, held)
    assert lines[0] == "이용 분석: 받음 3/4, 찾음 2, 찾지 못함 1"
    assert lines[1].startswith("co_loans: 순위 길이 합 4, 가진 책 합 2, 기준 책별 0권 1 / 1~2권 1")
    assert "인기 children-365(a~b): 길이 2, 가진 책 1, 어린이 도서 1, 추천 가능 1" in lines
    assert "인기 all-90: 받지 않음" in lines
    assert seed_lines(document, held, [ISBNS[0], ISBNS[1]])[0] == (
        "기준 책 2권 중 co_loans 비지 않음: 1"
    )
