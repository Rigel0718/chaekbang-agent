"""검색 평가 질의 만들기. 표본 책마다 이용자가 칠 법한 질의를 코드로 만든다.

같은 책에서 늘 같은 질의가 나오게 서명을 씨앗으로 쓴다. 오타는 한 군데만 낸다.

| 종류 | 만드는 방법 |
| --- | --- |
| exact | 표시 서명 |
| spacing | 공백을 지우거나, 공백이 없으면 가운데에 넣는다 |
| prefix | 서명 앞 절반(공백 제외 2글자 이상) |
| word | 서명의 둘째 낱말(2글자 이상) |
| author | 저자 원문의 첫 이름(`저`, `/`, `,` 앞) |
| vowel | 음절 하나의 중성을 이웃 모음으로 |
| final | 받침 하나를 빼거나 `ㄴ`을 더한다 |
| key | 초성 하나를 두벌식 자판 옆 자음으로 |
| suggest | 입력 중인 글자: 1음절+다음 초성, 2음절+다음 초성, 3음절 |
| found | 서명을 넣은 문장 틀 |
| unrelated | 어느 서명도 담지 않은 주제·기분 문장 (찾은 책 오탐) |
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.text import CHOSEONG, JONGSEONG, JUNGSEONG, compact

SEARCH_KINDS = ("exact", "spacing", "prefix", "word", "author", "vowel", "final", "key")
TYPO_KINDS = ("vowel", "final", "key")
VOWEL_PAIRS = {
    "ㅏ": "ㅑ", "ㅑ": "ㅏ", "ㅓ": "ㅕ", "ㅕ": "ㅓ", "ㅐ": "ㅔ", "ㅔ": "ㅐ",
    "ㅗ": "ㅛ", "ㅛ": "ㅗ", "ㅜ": "ㅠ", "ㅠ": "ㅜ",
}  # fmt: skip
KEY_ROWS = ("ㅂㅈㄷㄱㅅ", "ㅁㄴㅇㄹㅎ", "ㅋㅌㅊㅍ")
FOUND_TEMPLATES = ("{title} 있어요?", "{title} 어디 있나요", "혹시 {title} 빌릴 수 있어요?")
UNRELATED_SENTENCES = (
    "공룡 책 추천해줘",
    "퇴근 후 30분 읽을 에세이 추천해 주세요",
    "아이랑 같이 읽을 그림책 있어요?",
    "마음이 지칠 때 읽을 책",
    "요즘 재밌는 소설 뭐 있어요?",
    "초등학생이 볼 과학책 있나요?",
    "집에서 간단히 해 먹을 요리책",
    "역사 쉽게 읽을 책 추천해 주세요",
    "여행 가기 전에 읽을 만한 책",
    "선물하기 좋은 책 있을까요",
    "두껍지 않은 책으로 골라 주세요",
    "비 오는 주말에 읽을 소설",
    "자기 전에 아이한테 읽어 줄 책",
    "일본어 공부 시작하려는데 책 있어요?",
    "운동 시작하려고 하는데 도움 되는 책",
    "아이 훈육 방법 책 추천해 주세요",
    "양자 컴퓨터 회로 설계 전문서 있나요?",
    "주식 투자 입문서 있어요?",
    "고양이 키우는 법 알려 주는 책",
    "등산 지도 있나요",
    "클래식 음악 듣는 법 책",
    "그림 그리기 배우고 싶어요",
    "웃긴 만화책 있어요?",
    "명상하는 법 알려 주는 책",
    "다이어트 식단 책",
    "컴퓨터 처음 배우는 사람용 책",
    "영어 회화 책 있어요?",
    "시험 공부하는 고등학생 참고서",
    "잠이 안 올 때 읽기 좋은 책",
    "아무 책이나 추천해 주세요",
)
_SYLLABLE_BASE = 0xAC00
_NEIGHBORS = {
    key: [row[j] for j in (i - 1, i + 1) if 0 <= j < len(row)]
    for row in KEY_ROWS
    for i, key in enumerate(row)
}


@dataclass(frozen=True)
class Book:
    library_book_id: int
    title: str
    author: str


@dataclass(frozen=True)
class Query:
    kind: str
    text: str
    target: int | None  # 찾아야 할 기관 도서. 오탐 문장은 None


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16)


def _split(char: str) -> tuple[int, int, int] | None:
    code = ord(char) - _SYLLABLE_BASE
    if 0 <= code < 11172:
        return code // 588, code % 588 // 28, code % 28
    return None


def _join(cho: int, jung: int, jong: int) -> str:
    return chr(_SYLLABLE_BASE + (cho * 21 + jung) * 28 + jong)


def clean_title(title: str) -> str:
    """판본·묶음 표기(`(완전판)`, `[예스리커버]`)를 뺀 서명. 이용자는 이 표기를 치지 않는다."""
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)).strip() or title


def query_base(title: str) -> str:
    """오타를 낼 질의: 짧은 서명(공백 제외 6글자 이하)은 전체, 긴 서명은 첫 낱말."""
    title = clean_title(title)
    if len(compact(title)) <= 6:
        return title
    words = [w for w in re.split(r"[\s:,·]+", title) if len(w) >= 2]
    return words[0] if words else title


def typo(text: str, kind: str, key: str) -> str | None:
    """한 군데에 오타를 낸다. 낼 수 없으면 None."""
    chars = list(text)
    positions = [i for i, ch in enumerate(chars) if _split(ch)]
    if not positions:
        return None
    start = _seed(key + kind) % len(positions)
    for i in positions[start:] + positions[:start]:
        parts = _split(chars[i])
        assert parts is not None
        cho, jung, jong = parts
        if kind == "vowel" and JUNGSEONG[jung] in VOWEL_PAIRS:
            chars[i] = _join(cho, JUNGSEONG.index(VOWEL_PAIRS[JUNGSEONG[jung]]), jong)
        elif kind == "final":
            chars[i] = _join(cho, jung, 0 if jong else JONGSEONG.index("ㄴ"))
        elif kind == "key" and _NEIGHBORS.get(CHOSEONG[cho]):
            options = _NEIGHBORS[CHOSEONG[cho]]
            chars[i] = _join(CHOSEONG.index(options[_seed(key) % len(options)]), jung, jong)
        else:
            continue
        return "".join(chars)
    return None


def author_name(author: str) -> str | None:
    """저자 원문의 첫 이름. `앤디 위어 저/박아람 역` → `앤디 위어`."""
    first = re.split(r"\s+(?:저|글|지음|편|엮음)\b|/|,", author, maxsplit=1)[0].strip()
    return first if len(compact(first)) >= 2 else None


def suggest_inputs(title: str) -> list[str]:
    """입력 중인 글자. 한글 서명만 만든다."""
    letters = [ch for ch in clean_title(title) if not ch.isspace()]
    if len(letters) < 2 or not all(_split(ch) for ch in letters[:3] if ch):
        return []
    inputs = []
    for done in (1, 2):
        if done < len(letters) and _split(letters[done]):
            cho = _split(letters[done])
            assert cho is not None
            inputs.append("".join(letters[:done]) + CHOSEONG[cho[0]])
    if len(letters) >= 3:
        inputs.append("".join(letters[:3]))
    return inputs


def make_queries(books: Sequence[Book]) -> list[Query]:
    queries: list[Query] = []
    for book in books:
        title = clean_title(book.title)
        queries.append(Query("exact", book.title, book.library_book_id))
        spaced = (
            title.replace(" ", "")
            if " " in title
            else title[: len(title) // 2] + " " + title[len(title) // 2 :]
        )
        if len(compact(title)) >= 2:
            queries.append(Query("spacing", spaced, book.library_book_id))
        half = compact(title)[: max(2, len(compact(title)) // 2)]
        if 2 <= len(half) < len(compact(title)):
            queries.append(Query("prefix", half, book.library_book_id))
        words = [w for w in title.split(" ") if len(w) >= 2]
        if len(words) >= 2:
            queries.append(Query("word", words[1], book.library_book_id))
        if name := author_name(book.author):
            queries.append(Query("author", name, book.library_book_id))
        base = query_base(book.title)
        for kind in TYPO_KINDS:
            wrong = typo(base, kind, book.title)
            if wrong and compact(wrong) != compact(base):
                queries.append(Query(kind, wrong, book.library_book_id))
        for text in suggest_inputs(book.title):
            queries.append(Query("suggest", text, book.library_book_id))
        if len(compact(title)) >= 2:
            for template in FOUND_TEMPLATES:
                queries.append(Query("found", template.format(title=title), book.library_book_id))
    queries.extend(Query("unrelated", sentence, None) for sentence in UNRELATED_SENTENCES)
    return queries
