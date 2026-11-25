"""장서 가져오기 화면 확인용 견본 파일: uv run python scripts/make_import_samples.py [폴더]

고정된 가상 값만 쓰고 DB를 읽지 않는다.
폴더를 주지 않으면 저장소의 `import-samples/`에 쓴다(git 제외).
`normal.csv`를 외부 대출 기관에 적용하면 가져온 사본 38권이 생기고, 그 뒤 `half.csv`를 적용하면
빠진 사본이 절반을 넘어 대량 제적 확인이 뜬다(그 기관에 가져온 사본이 이것뿐일 때).
주의: 가져온 사본이 이미 있는 기관에 적용하면 그 사본들이 제적된다. 확인용 DB에서만 적용한다.
"""

import argparse
import csv
from pathlib import Path

HEADER = ["등록번호", "서명", "저자", "출판사", "ISBN", "수입구분", "가격", "대출 상태", "자료실"]
ROWS = 40
HALF_ROWS = 10
DEFAULT_FOLDER = Path(__file__).resolve().parents[1] / "import-samples"
OLD_XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(504)  # 예전 .xls의 머리 바이트
DONOR = "견본기증자"


def sample_row(number: int) -> list[str]:
    """견본 한 행. 번호에 따라 확인할 행(표기·건너뜀)이 섞인다."""
    title = f"견본 도서 {number:02d}"
    isbn, acquisition, price, status = "", "구입", "", "대출가능"
    if number <= 25:
        pass  # 매입인데 ISBN과 가격이 없다(20줄이 넘어 [더 보기]가 생긴다)
    elif number <= 28:
        isbn, price = "12345", "12000"  # ISBN 형식 오류
    elif number <= 30:
        status = "수리중"  # 모르는 대출 상태
        acquisition = "기증"
    elif number <= 32:
        title = ""  # 서명이 없어 건너뛴다
        acquisition = "기증"
    else:
        acquisition = "기증"
    return [
        f"IMP-{number:04d}",
        title,
        "견본 저자",
        "견본출판",
        isbn,
        acquisition,
        price,
        status,
        "종합자료실",
    ]


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def make(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    rows = [sample_row(number) for number in range(1, ROWS + 1)]

    write_csv(folder / "normal.csv", HEADER, rows)
    write_csv(folder / "half.csv", HEADER, rows[:HALF_ROWS])
    renamed = ["책임표시" if name == "저자" else name for name in HEADER]
    write_csv(folder / "renamed.csv", renamed, rows[:5])
    donated = [
        [f"IMP-D{number:03d}", f"견본 기증 도서 {number}", "견본 저자", "기증", DONOR]
        for number in range(1, 4)
    ]
    write_csv(folder / "donor.csv", ["등록번호", "서명", "저자", "수입구분", "기증처"], donated)
    (folder / "old.xls").write_bytes(OLD_XLS)
    (folder / "empty.csv").write_bytes(b"")

    names = ["normal.csv", "half.csv", "renamed.csv", "donor.csv", "old.xls", "empty.csv"]
    return [folder / name for name in names]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, nargs="?", default=DEFAULT_FOLDER)
    for path in make(parser.parse_args().folder):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
