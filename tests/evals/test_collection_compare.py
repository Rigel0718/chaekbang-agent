"""[platform/experiment-collection] 출처끼리 같은 ISBN 값 비교(건수만). design 결정 8의 3."""

import json
from pathlib import Path

from evals.collection.compare import load_books, summarize
from tests.helpers import make_isbn
from tests.source_helpers import d4l_book, kakao_document
from tests.yes24_helpers import item

A, B, C = (make_isbn(n) for n in (700, 701, 702))


def _files(tmp_path: Path) -> tuple[Path, Path]:
    yes24 = {
        "fetched_on": "2026-11-15",
        "books": [
            {"field": "toddler", "rank": 1, "item": item(A, title="강아지똥 (개정판)")},
            {
                "field": "essay",
                "rank": 1,
                "item": item(
                    B,
                    title="다른 책",
                    author="J.K. 롤링 저/김혜원 역",
                    goodsSortNm="국내도서-에세이",
                    contentDetail={"bookIntroduction": "긴 소개"},
                ),
            },
            {"field": "essay", "rank": 2, "item": item(C, title="셋째 책")},
        ],
    }
    sources = {
        "fetched_on": "2026-11-16",
        "sources": ["data4library", "kakao"],
        "books": [
            {
                "isbn": A,
                "field": "toddler",
                "data4library": {"status": "found", "books": [d4l_book(A)]},
                "kakao": {"status": "found", "documents": [kakao_document(A)]},
            },
            {
                "isbn": B,
                "field": "essay",
                "data4library": {
                    "status": "found",
                    "books": [
                        d4l_book(
                            B,
                            bookname="다른 책",
                            authors="조앤 K. 롤링 지음 ;김혜원 옮김",
                            addition_symbol="03840",
                        )
                    ],
                },
                "kakao": {"status": "not_found", "documents": []},
            },
            {"isbn": C, "field": "essay", "data4library": None, "kakao": None},
        ],
    }
    yes24_path, sources_path = tmp_path / "yes24.json", tmp_path / "sources.json"
    yes24_path.write_text(json.dumps(yes24, ensure_ascii=False), encoding="utf-8")
    sources_path.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    return yes24_path, sources_path


def test_counts(tmp_path: Path) -> None:
    """[platform/experiment-collection] 비교 수치 (찾은 출처, 서명 일치, 지은이, 어린이)"""
    summary = summarize(load_books(*_files(tmp_path)))
    assert summary["책"] == 3
    assert summary["찾은 출처"] == {"셋 다": 1, "카카오 없음": 1, "아직 받지 않음": 1}
    # 판본 표기를 지우면 `강아지똥 (개정판)`과 `강아지똥`이 같다
    assert summary["서명 일치"]["정보나루-YES24"] == (2, 2)
    assert summary["서명 일치"]["YES24-카카오"] == (1, 1)
    # `J.K. 롤링`과 `조앤 K. 롤링`은 지은이 수가 같고 키가 다르다(다른 음역 의심)
    assert summary["지은이"]["정보나루"] == {"같음": 1, "다른 음역 의심": 1, "비교": 2}
    assert summary["KDC 있음"] == 2 and summary["부가기호 있음"] == 2
    assert summary["어린이"] == {
        "YES24 분류": 2,  # A와 C는 `국내도서-유아`(고정본 기본값)
        "부가기호": 1,
        "둘 중 하나": 2,
        "둘 다": 1,
        "분류만": 1,
        "부가기호만": 0,
    }
    assert summary["소개"]["YES24"]["있음"] == 3


def test_no_values_in_output(tmp_path: Path) -> None:
    """[platform/experiment-collection] 비교 수치 (건수만 내고 서명·소개를 내지 않는다)"""
    text = json.dumps(summarize(load_books(*_files(tmp_path))), ensure_ascii=False)
    for value in ("강아지똥", "롤링", "긴 소개", "다른 책"):
        assert value not in text
