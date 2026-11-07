"""기관 층의 어린이 구분 규칙. 어린이 도서는 영유아·초등학생 대상 도서다.

공식 서지와 외부 연동은 어린이를 모른다. 분류 원문을 어린이 근거로 볼지는 여기서만 정한다.
값이 카테고리 이름과 항상 같지는 않아서 정확히 일치하는 값만 본다.
"""

CHILDREN_CATEGORIES = frozenset({"국내도서-유아", "국내도서-어린이", "국내도서-초등학습서"})


def is_children_category(category: str | None) -> bool:
    return category in CHILDREN_CATEGORIES
