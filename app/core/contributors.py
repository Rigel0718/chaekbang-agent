"""저자 원문 해석: 역할 표기와 이름 나누기. 문자열만 다루는 순수 함수다.

출처마다 꼴이 달라 해석기를 따로 둔다. 여기에는 역할 표, 공통 조각, 꼴이 정해지지 않은 기관 파일·
입력 값의 해석기(`parse_author_text`)와 기관 도서 저자 키(`author_keys`)를 둔다. YES24 해석기는
`app/central/external/yes24/contributors.py`에 있다.

- 역할은 일곱이다. 표에 없는 표기가 끝 낱말 자리에 오면 이름의 일부로 둔다(여러 낱말 이름이 많다).
  이름표(`낭독자: 김소리`)처럼 역할 자리가 분명한 꼴에서만 표에 없는 표기를 `other`로 읽는다.
- `공`·`등`은 역할 앞에 붙는 말(`공저`, `공역`, `등저`), `외`·`등`은 이름 뒤에 붙는 말이라 뺀다.
- 한 사람이 두 역할이면(`글그림`, `글,그림`, `글·그림`) 같은 이름을 역할마다 하나씩 낸다.
- 원문은 바꾸지 않는다. 표시와 서명·저자 찾기는 원문을 쓴다.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.core.text import clean_spaces, match_key


class ContributorRole(StrEnum):
    AUTHOR = "author"  # 글, 지은이
    ILLUSTRATOR = "illustrator"  # 그림
    TRANSLATOR = "translator"  # 옮김
    EDITOR = "editor"  # 엮음
    SUPERVISOR = "supervisor"  # 감수
    ORIGINAL = "original"  # 원저, 원작
    OTHER = "other"  # 기획, 사진 등 그 밖의 역할


# 지은이로 보는 역할. 기관 도서 저자 키와 "같은 저자"가 쓴다.
WRITER_ROLES = (ContributorRole.AUTHOR, ContributorRole.ORIGINAL)

# 역할 표기 → 역할. 키는 `match_key`로 맞춘 값이다. 표에 더하면 다시 만들기 스크립트를 돌린다.
ROLE_WORDS: dict[str, ContributorRole] = {
    **dict.fromkeys(
        ("저", "지음", "글", "지은이", "저자", "작가", "글쓴이", "저작", "편저"),
        ContributorRole.AUTHOR,
    ),
    **dict.fromkeys(
        ("그림", "그린이", "일러스트", "삽화", "만화", "그림작가"), ContributorRole.ILLUSTRATOR
    ),
    **dict.fromkeys(("역", "옮김", "옮긴이", "번역", "역자", "편역"), ContributorRole.TRANSLATOR),
    **dict.fromkeys(("편", "엮음", "엮은이", "편집", "편자"), ContributorRole.EDITOR),
    **dict.fromkeys(("감수", "감수자"), ContributorRole.SUPERVISOR),
    **dict.fromkeys(("원저", "원작", "원안"), ContributorRole.ORIGINAL),
    **dict.fromkeys(
        ("기획", "사진", "해설", "해제", "구성", "각색", "기획편집", "자문"),
        ContributorRole.OTHER,
    ),
}
_ROLE_PREFIXES = ("공", "등")  # 공저, 공역, 등저
_ROLE_WORDS_LONGEST = sorted(ROLE_WORDS, key=len, reverse=True)


@dataclass(frozen=True)
class Contributor:
    name: str  # 저장용(`clean_spaces`)
    role: ContributorRole
    role_text: str | None = None  # 역할 원문(`글`, `공역`, `기획`). 역할 표기가 없었으면 None

    @property
    def name_key(self) -> str:
        return match_key(self.name)


def _segment(word: str) -> list[str] | None:
    """역할 낱말 하나(`공역`, `글그림`)를 역할 표기 목록으로 나눈다. 다 나뉘지 않으면 None."""
    out: list[str] = []
    rest = word
    while rest:
        for prefix in ("", *_ROLE_PREFIXES):
            if not rest.startswith(prefix):
                continue
            body = rest[len(prefix) :]
            found = next((w for w in _ROLE_WORDS_LONGEST if body.startswith(w)), None)
            if found is not None:
                out.append(prefix + found)
                rest = body[len(found) :]
                break
        else:
            return None
    return out


def read_roles(text: str) -> list[tuple[ContributorRole, str]] | None:
    """역할 표기(`글`, `글,그림`, `글·그림`, `등저`)를 (역할, 원문) 목록으로. 역할이 아니면 None."""
    parts = [p for p in re.split(r"[,·ㆍ\s]+", clean_spaces(text)) if p]
    if not parts:
        return None
    roles: list[tuple[ContributorRole, str]] = []
    for part in parts:
        segments = _segment(match_key(part))
        if segments is None:
            return None
        for segment in segments:
            word = (
                segment[1:]
                if segment[0] in _ROLE_PREFIXES and segment not in ROLE_WORDS
                else segment
            )
            roles.append((ROLE_WORDS[word], segment))
    return roles


# 이름 뒤의 `외`, `외 3명`, `등`. 사람이 아니다.
_TRAILING_OTHERS = re.compile(r"(?:\s+|^)(?:외|등)(?:\s*\d+\s*(?:명|인))?$")
_NAME_SPLIT = re.compile(r"\s*[,，]\s*")


def split_names(text: str) -> list[str]:
    """`,`로 사람을 나누고 이름 뒤의 `외`·`등`을 뗀다. 빈 이름과 기호뿐인 이름은 버린다."""
    names: list[str] = []
    for part in _NAME_SPLIT.split(clean_spaces(text)):
        name = clean_spaces(_TRAILING_OTHERS.sub("", part))
        if match_key(name):
            names.append(name)
    return names


def _people(names: list[str], roles: list[tuple[ContributorRole, str]]) -> list[Contributor]:
    return [Contributor(name, role, role_text) for name in names for role, role_text in roles]


def parse_suffix_group(group: str) -> list[Contributor]:
    """`이름, 이름 역할` 꼴의 묶음 하나. 끝 낱말이 역할이 아니면 모두 `author`(역할 표기 없음)."""
    tokens = clean_spaces(group).split(" ")
    # 역할 표기가 띄어 쓰여 있을 수 있어(`글, 그림`) 가장 긴 역할 꼬리를 찾는다.
    # 이름은 한 낱말 이상 남긴다.
    for start in range(1, len(tokens)):
        roles = read_roles(" ".join(tokens[start:]))
        if roles is not None:
            return _people(split_names(" ".join(tokens[:start])), roles)
    return [Contributor(name, ContributorRole.AUTHOR) for name in split_names(group)]


_LABEL = re.compile(r"^([^:：,()]{1,10}?)\s*[:：]\s*(.+)$")
_PAREN = re.compile(r"^(.*?)\s*[(（]\s*([^()（）]+?)\s*[)）]$")


def _parse_label(group: str) -> list[Contributor] | None:
    """`지은이: 한강` 꼴. 이름표가 표에 없으면 `other`이고 이름표를 역할 원문으로 둔다."""
    match = _LABEL.match(group)
    if match is None:
        return None
    label, names = clean_spaces(match.group(1)), split_names(match.group(2))
    roles = read_roles(label) or [(ContributorRole.OTHER, label)]
    return _people(names, roles)


def _parse_parens(group: str) -> list[Contributor] | None:
    """`백희나 (지은이), 김소연 (옮긴이)` 꼴. 괄호 안이 역할인 조각이 하나도 없으면 None.

    괄호 안이 역할이 아니면(`에반(하상희)`) 이름의 일부로 둔다.
    """
    pieces = _NAME_SPLIT.split(group)
    parsed: list[list[Contributor]] = []
    matched = False
    for piece in pieces:
        match = _PAREN.match(piece)
        roles = read_roles(match.group(2)) if match else None
        if match is not None and roles is not None:
            matched = True
            parsed.append(_people(split_names(match.group(1)), roles))
        else:
            parsed.append(parse_suffix_group(piece))
    if not matched:
        return None
    return [person for people in parsed for person in people]


_GROUP_SPLIT = re.compile(r"\s*[/;|]\s*")


def _dedupe(people: list[Contributor]) -> list[Contributor]:
    seen: set[tuple[str, ContributorRole]] = set()
    out: list[Contributor] = []
    for person in people:
        key = (person.name_key, person.role)
        if person.name_key and key not in seen:
            seen.add(key)
            out.append(person)
    return out


def parse_author_text(author: str) -> list[Contributor]:
    """기관 파일·입력 값의 저자 원문. 꼴이 정해져 있지 않아 관대하게 읽는다.

    묶음은 `/`, `;`, `|`로 나누고, 역할은 이름표(`지은이: 한강`) → 괄호(`한강 (지은이)`) →
    끝 낱말(`한강 지음`) 순으로 찾는다. 아무것도 읽지 못하면 원문 전체를 `author` 한 명으로 둔다.
    """
    people: list[Contributor] = []
    for group in _GROUP_SPLIT.split(clean_spaces(author)):
        if not group:
            continue
        people.extend(_parse_label(group) or _parse_parens(group) or parse_suffix_group(group))
    people = _dedupe(people)
    if not people and match_key(author):
        return [Contributor(clean_spaces(author), ContributorRole.AUTHOR)]
    return people


def writer_keys(people: list[Contributor]) -> list[str]:
    """지은이(`author`, `original`)의 이름 맞춤 키. 순서대로, 중복 없이."""
    keys: list[str] = []
    for person in people:
        if person.role in WRITER_ROLES and person.name_key not in keys:
            keys.append(person.name_key)
    return keys


def author_keys(author: str | None) -> list[str]:
    """기관 도서 저자 키: 기관의 저자 원문에서 지은이의 이름 맞춤 키. 역자·그린이·감수자는 뺀다."""
    return writer_keys(parse_author_text(author)) if author else []
