"""추천 실험이 쓰는 정보나루 대출 신호. 받아 둔 파일(`evals/collection/loans.py`)만 읽는다.

제품의 신호 함수(`app/library/recommendation/related.py`)는 ISBN 순위를 주는 쪽(`LoanSignals`)만
안다. 여기는 그 공급을 파일로 구현한다. 외부 API를 부르지 않는다.

- 받지 않은(`null`) ISBN의 신호는 빈 것으로 본다. 그 수는 요약에 적는다.
- 정보나루 인기는 연령 묶음마다 정한 기간(`POPULAR_DAYS`)의 목록을 쓴다. 기간은 소장 겹침으로
  정한다(`add-loan-signals` design 결정 7).
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.library.recommendation.related import CO_LOAN, MANIA, READER
from evals.collection.loans import LOANS_FILE, condition_key

POPULAR_DAYS = 365  # 정보나루 인기의 기간(소장 겹침으로 정한다. 같으면 1년)
_FILE_KEYS = {CO_LOAN: "co_loans", MANIA: "mania", READER: "reader"}
FETCH_COMMAND = "uv run python -m evals.collection.loans"


class LoanSignalsMissingError(FileNotFoundError):
    pass


class FileLoanSignals:
    """대출 신호 파일을 읽는 `LoanSignals` 구현."""

    def __init__(self, document: Mapping[str, Any], popular_days: int = POPULAR_DAYS) -> None:
        self.document = document
        self.popular_days = popular_days

    @classmethod
    def load(cls, path: Path = LOANS_FILE, popular_days: int = POPULAR_DAYS) -> "FileLoanSignals":
        if not path.exists():
            raise LoanSignalsMissingError(f"대출 신호 파일이 없습니다: {path}")
        return cls(json.loads(path.read_text(encoding="utf-8")), popular_days)

    async def co_loans(self, isbn: str, kind: str = CO_LOAN) -> Sequence[str]:
        entry = self.document.get("usage", {}).get(isbn) or {}
        return list(entry.get(_FILE_KEYS[kind], ()))

    async def popular(self, age_group: str) -> Sequence[str]:
        key = condition_key(age_group, self.popular_days)
        entry = self.document.get("popular", {}).get(key) or {}
        return list(entry.get("isbns", ()))

    def pending_isbns(self) -> int:
        """이용 분석을 아직 받지 않은 ISBN 수."""
        return sum(1 for entry in self.document.get("usage", {}).values() if entry is None)

    def popular_conditions(self) -> dict[str, list[str]]:
        """받은 인기 조건(`<연령 묶음>-<기간>`) → ISBN 순위."""
        return {
            key: list(entry["isbns"])
            for key, entry in self.document.get("popular", {}).items()
            if entry is not None
        }

    def fingerprint(self) -> str:
        usage = self.document.get("usage", {})
        return (
            f"받은 날 {self.document.get('fetched_on')}, 이용 분석 ISBN {len(usage)}개"
            f"(받지 않음 {self.pending_isbns()}), 정보나루 인기 기간 {self.popular_days}일"
        )
