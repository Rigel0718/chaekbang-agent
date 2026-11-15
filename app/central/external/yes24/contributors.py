"""YES24 저자 원문 해석. `칼 멜링 글/브라이트 스타 그림/김맑아,김경덕 역` 꼴이다.

`/`로 묶음을 나누고, 묶음마다 끝의 역할 표기를 읽고, 앞부분을 `,`로 나눠 이름으로 삼는다.
역할 표와 공통 조각은 `app/core/contributors.py`에 있다.
"""

from app.core.contributors import Contributor, parse_suffix_group

GROUP_SEPARATOR = "/"


def parse_yes24_author(author: str) -> list[Contributor]:
    """원문에 나온 순서대로. 같은 사람·같은 역할은 한 번만 둔다."""
    seen: set[tuple[str, str]] = set()
    people: list[Contributor] = []
    for group in author.split(GROUP_SEPARATOR):
        for person in parse_suffix_group(group):
            key = (person.name_key, person.role)
            if person.name_key and key not in seen:
                seen.add(key)
                people.append(person)
    return people
