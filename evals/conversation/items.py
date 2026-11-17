"""추천 실험의 세 세트 항목을 대화로 바꾼다. 같은 세트 파일과 같은 항목 id를 쓴다.

| 세트 | 대화 | 묶음 |
| --- | --- | --- |
| `topic` | 이용자 문장 한 턴 | 어린이 / 일반은 결로 주제어·상황 |
| `similar` | 기준 책을 고른 턴(LLM 없음) → 정해 둔 문장 | 비슷한 책 |
| `history` | 기록의 책을 앞에서부터 고른 턴들(LLM 없음) → 정해 둔 문장 | 아무거나 |

기준 책이나 기록의 책이 모두 어린이 도서인 항목은 어린이 요청 문장을 쓴다. 실험이 그 항목에 어린이
조건을 걸었기 때문이다. 규칙 검사와 실행은 AI 사서 평가의 `Scenario`와 `run_scenario`를 그대로
쓴다(기대는 `ANY`: 규칙 검사만, 품질은 라벨로 본다).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from evals.librarian.scenarios import Expect, Scenario
from evals.recommendation.sets import History, Seed, TopicQuery

SIMILAR_TEXT = "이 책이랑 비슷한 책 있어요?"
SIMILAR_CHILDREN_TEXT = "아이랑 같이 볼 건데 이 책이랑 비슷한 책 있어요?"
ANYTHING_TEXT = "아무거나 추천해 줘"
ANYTHING_CHILDREN_TEXT = "아이가 읽을 거 아무거나 추천해 줘"
TRACE = "[platform/conversation-recommendation-evals] 세트 항목을 대화로"


class Group(StrEnum):
    KEYWORD = "keyword"  # 주제어 요청(일반)
    SITUATION = "situation"  # 상황·기분 요청(일반)
    CHILDREN = "children"  # 어린이 주제 요청
    SIMILAR = "similar"  # 비슷한 책
    ANYTHING = "anything"  # 아무거나(최근 기록)


GROUP_NAMES = {
    Group.KEYWORD: "주제어",
    Group.SITUATION: "상황",
    Group.CHILDREN: "어린이",
    Group.SIMILAR: "비슷한 책",
    Group.ANYTHING: "아무거나",
}


@dataclass(frozen=True)
class ChatItem:
    set_name: str  # topic | similar | history (라벨 파일 이름)
    id: str  # 세트의 항목 id(라벨의 항목 id)
    group: Group
    scenario: Scenario
    picks: tuple[str, ...] = ()  # 첫 턴 전에 차례로 고를 책 키


def _scenario(item_id: str, text: str, children: bool) -> Scenario:
    return Scenario(item_id, (text,), Expect.ANY, children=children, traces=(TRACE,))


def topic_item(query: TopicQuery) -> ChatItem:
    if query.children:
        group = Group.CHILDREN
    else:
        group = Group.KEYWORD if query.style == "topic" else Group.SITUATION
    return ChatItem("topic", query.id, group, _scenario(query.id, query.text, query.children))


def similar_item(seed: Seed, children: bool) -> ChatItem:
    text = SIMILAR_CHILDREN_TEXT if children else SIMILAR_TEXT
    return ChatItem(
        "similar", seed.id, Group.SIMILAR, _scenario(seed.id, text, children), (seed.book,)
    )


def history_item(history: History, children: bool) -> ChatItem:
    text = ANYTHING_CHILDREN_TEXT if children else ANYTHING_TEXT
    return ChatItem(
        "history", history.id, Group.ANYTHING, _scenario(history.id, text, children), history.books
    )


def build_items(
    topics: Sequence[TopicQuery],
    seeds: Sequence[Seed],
    histories: Sequence[History],
    keys: Mapping[str, int],
    children: set[int],
) -> list[ChatItem]:
    """keys는 책 키 → 기관 도서 id, children은 어린이 도서 id다(어린이 문장을 고른다)."""

    def all_children(books: Sequence[str]) -> bool:
        return all(keys[key] in children for key in books)

    return [
        *(topic_item(q) for q in topics),
        *(similar_item(s, all_children((s.book,))) for s in seeds),
        *(history_item(h, all_children(h.books)) for h in histories),
    ]
