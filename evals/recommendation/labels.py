"""어울림 라벨 파일. 사람이 0·1·2로 단 값이고 다시 만들 수 없다(저장소 밖, 따로 백업한다).

형식: `{"<항목 id>": {"<책 키>": {"grade": 2, "stage": "before", "by": "user"}}}`.
단 쪽 `by`는 `claude`(초안)와 `user`(사람이 달았거나 검수에서 확인·고침)다. 없으면 `user`다.
단계는 `before`(어떤 변형도 돌리기 전, 분야로 좁힌 목록에서)와 `pool`(실행 뒤 상위 결과 중 라벨
없는 책 보충)이다.
"""

import json
from pathlib import Path

from evals.recommendation.keys import DATA_DIR

LABELS_DIR = DATA_DIR / "labels"
GRADES = (0, 1, 2)
BEFORE = "before"
POOL = "pool"
CLAUDE = "claude"
USER = "user"


def labels_file(set_name: str) -> Path:
    return LABELS_DIR / f"{set_name}.json"


class Labels:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: dict[str, dict[str, dict]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def grade(self, item_id: str, key: str) -> int | None:
        entry = self.items.get(item_id, {}).get(key)
        return entry["grade"] if entry else None

    def grades(self, item_id: str) -> dict[str, int]:
        return {key: entry["grade"] for key, entry in self.items.get(item_id, {}).items()}

    def labeler(self, item_id: str, key: str) -> str | None:
        entry = self.items.get(item_id, {}).get(key)
        return entry.get("by", USER) if entry else None

    def stage(self, item_id: str, key: str) -> str | None:
        entry = self.items.get(item_id, {}).get(key)
        return entry["stage"] if entry else None

    def put(self, item_id: str, key: str, grade: int, stage: str, by: str = USER) -> None:
        """라벨 하나를 적고 바로 파일에 쓴다."""
        self.put_many(item_id, {key: grade}, stage, by)

    def put_many(self, item_id: str, grades: dict[str, int], stage: str, by: str = USER) -> None:
        """한 항목의 라벨 여럿을 적고 파일에 한 번 쓴다."""
        for grade in grades.values():
            if grade not in GRADES:
                raise ValueError(f"라벨은 0·1·2다: {grade}")
        entries = self.items.setdefault(item_id, {})
        for key, grade in grades.items():
            entries[key] = {"grade": grade, "stage": stage, "by": by}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )

    def stage_counts(self) -> dict[str, int]:
        counts = {BEFORE: 0, POOL: 0}
        for entries in self.items.values():
            for entry in entries.values():
                counts[entry["stage"]] = counts.get(entry["stage"], 0) + 1
        return counts

    def by_counts(self) -> dict[str, int]:
        counts = {CLAUDE: 0, USER: 0}
        for entries in self.items.values():
            for entry in entries.values():
                by = entry.get("by", USER)
                counts[by] = counts.get(by, 0) + 1
        return counts

    def book_keys(self) -> set[str]:
        return {key for entries in self.items.values() for key in entries}
