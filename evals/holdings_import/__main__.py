import sys

from evals.holdings_import.files import generate_files
from evals.holdings_import.metrics import FileScore, score_file

HEADER = (
    "| 파일 | 행 | 건너뜀 | ISBN 인식 | 틀린 ISBN 표기 | 어린이 정밀도 | 어린이 재현율 | 표기 행 |"
)


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:5.1f}%"


def _line(score: FileScore) -> str:
    return (
        f"| {score.name} | {score.rows} | {score.skipped} | {_pct(score.isbn_recognition)} "
        f"| {_pct(score.invalid_flagged)} | {_pct(score.children_precision)} "
        f"| {_pct(score.children_recall)} | {_pct(score.flagged_rate)} |"
    )


def main() -> int:
    scores = [score_file(file) for file in generate_files()]
    print(HEADER)
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for score in scores:
        print(_line(score))
    # 일반 도서를 어린이로 잘못 분류하면 어린이 추천에 일반 도서가 섞인다.
    wrong = [s.name for s in scores if s.children_precision not in (None, 1.0)]
    if wrong:
        print(f"어린이 정밀도가 1.0이 아닌 파일: {', '.join(wrong)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
