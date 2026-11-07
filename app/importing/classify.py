"""어린이 도서 분류 근거. 판단은 표 기반 코드로 하고, 불확실하면 근거 없음으로 둔다."""

CHILDREN_MARKS = {"아", "아동", "어린이", "유", "유아", "j"}
CHILDREN_SHELF_WORDS = ("어린이", "아동", "유아")
CHILDREN_ADDITION_DIGITS = ("6", "7")  # 독자대상기호: 초등 학습참고서, 아동


def has_children_label(
    separate_mark: str | None, shelf_location: str | None, addition_code: str | None
) -> bool:
    """별치기호(완전 일치), 자료실 이름, 부가기호 첫 자리 중 하나라도 아동이면 True."""
    if separate_mark and separate_mark.replace(" ", "").casefold() in CHILDREN_MARKS:
        return True
    if shelf_location and any(word in shelf_location for word in CHILDREN_SHELF_WORDS):
        return True
    code = (addition_code or "").strip()
    return len(code) == 5 and code.isdigit() and code[0] in CHILDREN_ADDITION_DIGITS
