"""평가 세트 읽기와 검사.

- 주제 질의(`sets/topic.json`): 사람이 쓴 문장이라 저장소에 둔다. ISBN·등록번호가 들어가면 안 된다.
- 기준 책과 최근 기록(`data/seeds.json`): 책 키가 실험 장서를 가리켜 저장소 밖에 둔다.

남겨 둔 분야(holdout)는 질의의 관련 분야, 기준 책, 최근 기록에 쓸 수 없다.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.recommendation.keys import DATA_DIR, FIELD_KEYS, HOLDOUT_FIELDS

TOPIC_FILE = Path(__file__).parent / "sets" / "topic.json"
SEEDS_FILE = DATA_DIR / "seeds.json"
STYLES = ("topic", "mood")  # 주제어 요청 / 상황·기분 요청
SPLITS = ("tune", "check")  # 조정 / 확인
_BOOK_VALUE = re.compile(r"97[89]\d{10}|EX\d{5}|isbn:|acc:")


class SetError(ValueError):
    def __init__(self, item_id: str, message: str) -> None:
        super().__init__(f"{item_id}: {message}")
        self.item_id = item_id


@dataclass(frozen=True)
class TopicQuery:
    id: str
    text: str  # 이용자 문장
    keywords: tuple[str, ...]  # 사서(LLM)가 tool에 넘길 낱말
    children: bool  # 어린이 요청인지(사람이 정한다. 요청 판단은 이 실험의 범위가 아니다)
    style: str
    fields: tuple[str, ...]  # 관련 분야. 실행 전 라벨 후보를 좁힌다
    split: str


@dataclass(frozen=True)
class Seed:
    id: str
    book: str  # 책 키
    split: str


@dataclass(frozen=True)
class History:
    id: str
    books: tuple[str, ...]  # 최근 기록의 책 키 목록
    split: str


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else "없음"


def _need(row: Mapping[str, Any], item_id: str, *names: str) -> None:
    for name in names:
        value = row.get(name)
        if value is None or value == "" or value == []:
            raise SetError(item_id, f"빠진 칸 `{name}`")


def _unique(item_id: str, seen: set[str]) -> None:
    if item_id in seen:
        raise SetError(item_id, "겹친 id")
    seen.add(item_id)


def _split(row: Mapping[str, Any], item_id: str) -> str:
    if row["split"] not in SPLITS:
        raise SetError(item_id, f"정의되지 않은 구분 `{row['split']}` ({', '.join(SPLITS)})")
    return row["split"]


def parse_topic(document: Mapping[str, Any]) -> list[TopicQuery]:
    queries, seen = [], set()
    for row in document.get("queries", []):
        item_id = str(row.get("id") or "(id 없음)")
        _need(row, item_id, "id", "text", "keywords", "style", "fields", "split")
        if "children" not in row or not isinstance(row["children"], bool):
            raise SetError(item_id, "빠진 칸 `children`")
        _unique(item_id, seen)
        if row["style"] not in STYLES:
            raise SetError(item_id, f"정의되지 않은 결 `{row['style']}` ({', '.join(STYLES)})")
        for field in row["fields"]:
            if field not in FIELD_KEYS:
                raise SetError(item_id, f"없는 분야 `{field}`")
            if field in HOLDOUT_FIELDS:
                raise SetError(item_id, f"남겨 둔 분야 `{field}`는 질의에 쓰지 않는다")
        for value in (row["text"], *row["keywords"]):
            if _BOOK_VALUE.search(str(value)):
                raise SetError(item_id, "ISBN이나 등록번호 모양의 값이 있다(저장소에 넣지 않는다)")
        queries.append(
            TopicQuery(
                id=item_id,
                text=row["text"],
                keywords=tuple(row["keywords"]),
                children=row["children"],
                style=row["style"],
                fields=tuple(row["fields"]),
                split=_split(row, item_id),
            )
        )
    return queries


def load_topic(path: Path = TOPIC_FILE) -> list[TopicQuery]:
    return parse_topic(json.loads(path.read_text(encoding="utf-8")))


def _check_book(item_id: str, key: str, fields: Mapping[str, str]) -> None:
    field = fields.get(key)
    if field is None:
        raise SetError(item_id, f"실험 장서에 없는 책 `{key}`")
    if field in HOLDOUT_FIELDS:
        raise SetError(item_id, f"남겨 둔 분야 `{field}`의 책 `{key}`는 쓰지 않는다")


def parse_seeds(
    document: Mapping[str, Any], fields: Mapping[str, str]
) -> tuple[list[Seed], list[History]]:
    """fields는 책 키별 분야(`keys.load_fields`)다. 남겨 둔 분야의 책을 거부한다."""
    seeds, histories, seen = [], [], set()
    for row in document.get("similar", []):
        item_id = str(row.get("id") or "(id 없음)")
        _need(row, item_id, "id", "book", "split")
        _unique(item_id, seen)
        _check_book(item_id, row["book"], fields)
        seeds.append(Seed(item_id, row["book"], _split(row, item_id)))
    for row in document.get("history", []):
        item_id = str(row.get("id") or "(id 없음)")
        _need(row, item_id, "id", "books", "split")
        _unique(item_id, seen)
        for key in row["books"]:
            _check_book(item_id, key, fields)
        histories.append(History(item_id, tuple(row["books"]), _split(row, item_id)))
    return seeds, histories


def load_seeds(
    fields: Mapping[str, str], path: Path = SEEDS_FILE
) -> tuple[list[Seed], list[History]]:
    return parse_seeds(json.loads(path.read_text(encoding="utf-8")), fields)
