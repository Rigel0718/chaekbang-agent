"""[platform/recommendation-experiments] 평가 세트, 책 키, 기준 책 고르기.

실험 장서 파일 없이 돈다.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from evals.recommendation.keys import DATA_DIR, book_key, fields_of, library_keys
from evals.recommendation.pick import BookInfo, pick
from evals.recommendation.sets import SetError, parse_seeds, parse_topic
from tests.conftest import Tenant
from tests.helpers import add_held_book, make_isbn
from tests.yes24_helpers import item

REPO = Path(__file__).resolve().parents[2]


def _query(**changes) -> dict:
    base = {
        "id": "t01",
        "text": "일곱 살 아이가 공룡을 좋아해요",
        "keywords": ["공룡"],
        "children": True,
        "style": "topic",
        "fields": ["children"],
        "split": "tune",
    }
    return {**base, **changes}


FIELDS = {
    "isbn:9791100000011": "children",
    "isbn:9791100000028": "fiction",
    "acc:EX00003": "essay",
    "isbn:9791100000035": "religion",
}


def test_missing_field_names_the_query() -> None:
    """[platform/recommendation-experiments] 평가 세트 형식 / 빠진 칸"""
    with pytest.raises(SetError) as caught:
        parse_topic({"queries": [_query(keywords=[])]})
    assert caught.value.item_id == "t01"
    assert "keywords" in str(caught.value)
    for changes in ({"split": "dev"}, {"style": "long"}, {"fields": ["cooking"]}):
        with pytest.raises(SetError):
            parse_topic({"queries": [_query(**changes)]})
    with pytest.raises(SetError, match="겹친 id"):
        parse_topic({"queries": [_query(), _query()]})


def test_three_sets_are_read() -> None:
    """[platform/recommendation-experiments] 평가 세트 형식 / 세 종류 읽기"""
    queries = parse_topic(
        {"queries": [_query(), _query(id="t02", children=False, style="mood", split="check")]}
    )
    assert [(q.id, q.children, q.style, q.split) for q in queries] == [
        ("t01", True, "topic", "tune"),
        ("t02", False, "mood", "check"),
    ]
    assert queries[0].keywords == ("공룡",) and queries[0].fields == ("children",)
    seeds, histories = parse_seeds(
        {
            "similar": [
                {"id": "s01", "book": "isbn:9791100000011", "split": "tune"},
                {"id": "s02", "book": "acc:EX00003", "split": "check"},
            ],
            "history": [
                {"id": "h01", "books": ["isbn:9791100000011", "acc:EX00003"], "split": "tune"},
                {"id": "h02", "books": ["isbn:9791100000028"], "split": "tune"},
            ],
        },
        FIELDS,
    )
    assert [s.book for s in seeds] == ["isbn:9791100000011", "acc:EX00003"]
    assert [h.books for h in histories] == [
        ("isbn:9791100000011", "acc:EX00003"),
        ("isbn:9791100000028",),
    ]


def test_holdout_field_query_is_rejected() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 제외 / 남겨 둔 분야의 질의"""
    with pytest.raises(SetError) as caught:
        parse_topic({"queries": [_query(id="t09", fields=["essay", "art"])]})
    assert caught.value.item_id == "t09"
    assert "남겨 둔 분야" in str(caught.value)


def test_holdout_seed_book_is_rejected() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 제외 / 남겨 둔 분야의 기준 책"""
    with pytest.raises(SetError) as caught:
        parse_seeds(
            {"similar": [{"id": "s07", "book": "isbn:9791100000035", "split": "tune"}]}, FIELDS
        )
    assert caught.value.item_id == "s07"
    assert "남겨 둔 분야" in str(caught.value)
    with pytest.raises(SetError, match="남겨 둔 분야"):
        parse_seeds(
            {
                "history": [
                    {"id": "h03", "books": ["acc:EX00003", "isbn:9791100000035"], "split": "tune"}
                ]
            },
            FIELDS,
        )


def test_isbn_in_query_file_fails() -> None:
    """[platform/recommendation-experiments] 저장소에 넣는 것과 빼는 것 / 질의 파일의 ISBN"""
    with pytest.raises(SetError) as caught:
        parse_topic({"queries": [_query(id="t05", text="9788901234567 같은 책")]})
    assert caught.value.item_id == "t05"
    with pytest.raises(SetError):
        parse_topic({"queries": [_query(keywords=["EX00012"])]})


def test_data_folder_is_ignored() -> None:
    """[platform/recommendation-experiments] 저장소에 넣는 것과 빼는 것 / 데이터 폴더"""
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"{DATA_DIR.relative_to(REPO)}/" in ignored


def test_repo_topic_set_is_valid() -> None:
    """[platform/recommendation-experiments] 평가 세트 형식

    저장소의 주제 질의 파일이 검사를 통과한다.
    """
    path = REPO / "evals" / "recommendation" / "sets" / "topic.json"
    if not path.exists():
        pytest.skip("주제 질의 파일을 아직 쓰지 않았다")
    queries = parse_topic(json.loads(path.read_text(encoding="utf-8")))
    assert queries


async def test_two_kinds_of_keys(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/recommendation-experiments] 책 키 / 두 갈래 키"""
    isbn = make_isbn(801)
    linked = await add_held_book(session, library_a.id, isbn=isbn, official={"title": "공식"})
    own = await add_held_book(session, library_a.id, "available", "on_loan", title="기관 책")
    keys = await library_keys(session, library_a.id)
    by_id = {book_id: key for key, book_id in keys.items()}
    assert by_id[linked["id"]] == f"isbn:{isbn}"
    assert by_id[own["id"]].startswith("acc:AC")
    assert book_key(None, "EX00004") == "acc:EX00004"
    # 사본이 둘이면 가장 앞선 등록번호다
    assert sum(1 for key in keys if key.startswith("acc:")) == 1


def test_fields_follow_the_seeding_order() -> None:
    """[platform/recommendation-experiments] 책 키 (분야는 적재와 같은 순서 번호로 맞춘다)"""
    books = [
        {"field": "essay" if n % 2 else "fiction", "item": item(make_isbn(n), title=f"책{n}")}
        for n in range(10, 0, -1)
    ]
    fields = fields_of(books)
    isbns = sorted(make_isbn(n) for n in range(1, 11))
    # 순서 번호 3(네 번째 책)은 ISBN 없이 들어가 등록번호로 가리킨다
    assert "acc:EX00004" in fields and f"isbn:{isbns[3]}" not in fields
    assert fields[f"isbn:{isbns[0]}"] in ("essay", "fiction")
    assert len(fields) == 10


def _infos() -> list[BookInfo]:
    infos = []
    for n in range(240):
        field = ("toddler", "children", "fiction", "essay", "science", "history", "art")[n % 7]
        infos.append(
            BookInfo(
                key=f"acc:EX{n:05d}" if n % 10 == 3 else f"isbn:{make_isbn(n)}",
                field=field,
                children=field in ("toddler", "children"),
                related=n % 3 == 0,
            )
        )
    return infos


def test_pick_is_deterministic_and_skips_holdout() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 제외 (기준 책 고르기)

    두 번 고르면 같고, 남겨 둔 분야의 책이 없다.
    """
    infos = _infos()
    first = pick(infos)
    assert first == pick(list(reversed(infos)))
    by_key = {info.key: info for info in infos}
    seeds = [by_key[row["book"]] for row in first["similar"]]
    assert len(seeds) == 20 and len({s.key for s in seeds}) == 20
    assert sum(s.children for s in seeds) == 8
    assert sum(s.related for s in seeds) == 10
    assert sum(s.key.startswith("acc:") for s in seeds) >= 2
    assert len(first["history"]) == 10
    assert all(2 <= len(row["books"]) <= 3 for row in first["history"])
    picked = [row["book"] for row in first["similar"]]
    picked += [key for row in first["history"] for key in row["books"]]
    assert all(by_key[key].field != "art" for key in picked)
    assert {row["split"] for row in first["similar"]} == {"tune", "check"}
    parse_seeds(first, {info.key: info.field for info in infos})
