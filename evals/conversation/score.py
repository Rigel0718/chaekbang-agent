"""카드 채점과 요약. DB와 LLM을 모르는 순수 함수다.

- 카드: 마지막 턴의 추천 카드를 카드 순서대로 책 키로 바꾼다(최대 5권).
- tool 결과 앞 5권: 마지막 턴에서 처음 부른 책 tool(검색 또는 관련 책)의 결과 앞 5권. 카드가 tool
  순서보다 나은지(LLM이 고른 효과) 본다.
- 지표: Hit@5, Recall@5(분모는 라벨 1 이상인 책 수와 5 중 작은 값), nDCG@5(이상적 순위는 그 항목의
  라벨 전체). 라벨 없는 책은 0으로 센다. 카드가 없으면 셋 다 0이다.
- 수치는 같은 라벨에서 버전끼리 비교할 때만 쓴다(라벨은 Claude 초안, 사람은 표본만 검수).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.config import LLM_PRICES
from evals.conversation.items import GROUP_NAMES, Group
from evals.recommendation.metrics import TOP, hit, mean, ndcg, recall

RESULTS_VARIANT = "chat"  # 보충 도구가 읽는 results-<세트>.json의 변형 이름
NOT_POOLED = "라벨 보충 전"


@dataclass(frozen=True)
class Score:
    hit: float
    recall: float
    ndcg: float
    count: int  # 책 수(카드면 카드 수)
    unlabeled: int  # 라벨 없는 책 수


@dataclass
class ItemRun:
    """항목 하나의 실행 결과(저장하고 다시 읽는 값만)."""

    set_name: str
    id: str
    group: Group
    cards: list[str]  # 카드 책 키, 카드 순서
    tool_top: list[str]  # 처음 부른 책 tool 결과 앞 5권의 책 키
    calls: list[dict[str, Any]] = field(default_factory=list)  # tool 이름, 입력, 결과 키, note
    violations: dict[str, list[str]] = field(default_factory=dict)
    children_judged: bool = False
    status: str = ""
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def score_keys(keys: Sequence[str], labels: Mapping[str, int]) -> Score:
    """keys는 순서대로의 책 키, labels는 그 항목의 책 키 → 라벨이다."""
    top = list(keys[:TOP])
    grades = [labels.get(k) for k in top]
    labeled = list(labels.values())
    return Score(
        hit=hit(grades),
        recall=recall(grades, labeled, k=TOP),
        ndcg=ndcg(grades, labeled),
        count=len(top),
        unlabeled=sum(1 for g in grades if g is None),
    )


def cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """캐시 없이 계산한 비용(USD). 가격표에 없는 모델이면 None."""
    price = LLM_PRICES.get(model)
    if price is None:
        return None
    million = Decimal(1_000_000)
    return (price.input * input_tokens + price.output * output_tokens) / million


@dataclass(frozen=True)
class GroupRow:
    name: str
    items: int
    cards: Score  # 평균(hit·recall·ndcg), 합(count·unlabeled)
    tool: Score
    empty: int  # 카드 없음


def _average(scores: Sequence[Score]) -> Score:
    return Score(
        hit=mean([s.hit for s in scores]),
        recall=mean([s.recall for s in scores]),
        ndcg=mean([s.ndcg for s in scores]),
        count=sum(s.count for s in scores),
        unlabeled=sum(s.unlabeled for s in scores),
    )


def group_rows(
    runs: Sequence[ItemRun], labels: Mapping[str, Mapping[str, Mapping[str, int]]]
) -> list[GroupRow]:
    """labels는 세트 → 항목 id → 책 키 → 라벨. 전체 줄이 먼저, 그다음 묶음 순서대로."""
    scored = [
        (
            run,
            score_keys(run.cards, labels[run.set_name].get(run.id, {})),
            score_keys(run.tool_top, labels[run.set_name].get(run.id, {})),
        )
        for run in runs
    ]

    def row(name: str, part: Sequence[tuple[ItemRun, Score, Score]]) -> GroupRow:
        return GroupRow(
            name,
            len(part),
            _average([c for _, c, _ in part]),
            _average([t for _, _, t in part]),
            sum(1 for r, _, _ in part if not r.cards),
        )

    rows = [row("전체", scored)]
    for group in Group:
        rows.append(row(GROUP_NAMES[group], [p for p in scored if p[0].group == group]))
    return rows


def _fmt(score: Score) -> str:
    return f"{score.hit:.3f} | {score.recall:.3f} | {score.ndcg:.3f}"


def table(rows: Sequence[GroupRow]) -> list[str]:
    lines = [
        "| 묶음 | 항목 | 카드 Hit@5 | 카드 Recall@5 | 카드 nDCG@5 | tool 앞 5권 Hit@5 | Recall@5 "
        "| nDCG@5 | 카드 없음 | 라벨 없는 카드 | 라벨 없는 tool 책 |",
        "|" + " --- |" * 11,
    ]
    for r in rows:
        lines.append(
            f"| {r.name} | {r.items} | {_fmt(r.cards)} | {_fmt(r.tool)} | {r.empty} "
            f"| {r.cards.unlabeled} | {r.tool.unlabeled} |"
        )
    return lines


def summary(
    runs: Sequence[ItemRun],
    labels: Mapping[str, Mapping[str, Mapping[str, int]]],
    head: Sequence[str],
    model: str,
) -> str:
    """요약 글. head는 머리 줄(모델, 프로필 버전, 세트 해시, 라벨 수, 장서)."""
    rows = group_rows(runs, labels)
    unlabeled = rows[0].cards.unlabeled
    violations = sum(len(v) for r in runs for v in r.violations.values())
    calls = [c for r in runs for c in r.calls]
    searches = [c for c in calls if "keywords" in c["input"]]
    tokens_in = sum(r.input_tokens for r in runs)
    tokens_out = sum(r.output_tokens for r in runs)
    usd = cost(model, tokens_in, tokens_out)
    lines = []
    if unlabeled:
        lines += [
            f"**{NOT_POOLED}**: 라벨 없는 카드 {unlabeled}권(0으로 셈). 보충 뒤 다시 읽는다.",
            "",
        ]
    lines += [*head, "", *table(rows), ""]
    lines += [
        f"규칙 위반 {violations}건",
        f"턴 {len(runs)}개(LLM 턴), LLM 호출 {sum(r.llm_calls for r in runs)}회, "
        f"입력 토큰 {tokens_in}, 출력 토큰 {tokens_out}, "
        + (f"비용 ${usd:.4f}(캐시 없이)" if usd is not None else "비용 -(가격표에 없는 모델)"),
        f"검색 tool 호출 {len(searches)}번, 키워드 순위가 빈 검색 "
        f"{sum(1 for c in searches if c['keyword_missing'])}번, 결과 note "
        f"{sum(1 for c in calls if c['note'])}번",
        "장서는 YES24 스테디셀러 실험 장서이고 기관·사본은 가상이다. 수치를 실제 서비스 성능으로 "
        "쓰지 않는다. 라벨은 Claude 초안·사람 표본 검수다.",
    ]
    for run in runs:
        for name, items in run.violations.items():
            lines.append(f"- {run.set_name}/{run.id} {name}: {items}")
    return "\n".join(lines) + "\n"


def exit_code(runs: Sequence[ItemRun]) -> int:
    """규칙 위반이 하나라도 있으면 1."""
    return 1 if any(r.violations for r in runs) else 0


def results(runs: Sequence[ItemRun]) -> dict[str, dict[str, dict[str, list[dict[str, str]]]]]:
    """세트 → {변형 `chat`: 항목 → 책 키 목록}. 카드 다음에 tool 결과 앞 5권(중복 없이)."""
    out: dict[str, dict[str, dict[str, list[dict[str, str]]]]] = {}
    for run in runs:
        keys = list(dict.fromkeys([*run.cards, *run.tool_top]))
        out.setdefault(run.set_name, {RESULTS_VARIANT: {}})[RESULTS_VARIANT][run.id] = [
            {"key": k} for k in keys
        ]
    return out
