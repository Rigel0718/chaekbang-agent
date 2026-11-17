"""관련 책 결과의 근거 코드와 문구. LLM을 쓰지 않는 순수 함수다.

근거 코드는 결과가 오른 신호 이름이고, 문구는 코드가 데이터(신호, 표시 KDC 세목)로 만든다. 화면과
AI 사서 tool이 같은 문구를 쓴다. LLM은 이 문구와 소개를 근거로만 이유를 쓴다(설계 원칙 6).
"""

from collections.abc import Mapping

from app.library.recommendation.related import (
    AUTHOR,
    KDC,
    NATIONAL_POPULAR,
    POPULAR,
    SERIES,
    VECTOR,
    kdc_section,
)

BASIS_ORDER = (SERIES, AUTHOR, KDC, VECTOR, POPULAR, NATIONAL_POPULAR)
TEXT_LIMIT = 2

_SIMILAR = {
    SERIES: "같은 시리즈",
    AUTHOR: "같은 지은이",
    KDC: "같은 분류",
    VECTOR: "내용이 비슷한 책",
}
_HISTORY = {
    AUTHOR: "최근 본 책과 같은 지은이",
    KDC: "최근 본 책과 같은 분류",
    VECTOR: "최근 본 책과 내용이 비슷한 책",
}
_POPULAR = {
    POPULAR: "우리 도서관에서 많이 빌린 책",
    NATIONAL_POPULAR: "전국 도서관에서 많이 빌린 책",
}


def basis_codes(ranks: Mapping[str, int]) -> list[str]:
    """결과가 오른 신호 이름을 모두, 정한 순서로. 순서 표에 없는 신호는 뒤에 이름 순으로 둔다."""
    known = [code for code in BASIS_ORDER if code in ranks]
    return known + sorted(code for code in ranks if code not in BASIS_ORDER)


def _text(code: str, kdc: str | None, history: bool) -> str | None:
    if code in _POPULAR:
        return _POPULAR[code]
    if history:
        return _HISTORY.get(code)
    if code == KDC:
        section = kdc_section(kdc)
        return f"{_SIMILAR[KDC]} {section}" if section else _SIMILAR[KDC]
    return _SIMILAR.get(code)


def basis_texts(
    ranks: Mapping[str, int], *, kdc: str | None = None, history: bool = False
) -> list[str]:
    """근거 문구를 두 개까지. kdc는 그 결과 책의 표시 KDC, history는 최근 기록 결과인지다."""
    texts = [_text(code, kdc, history) for code in basis_codes(ranks)]
    return [text for text in texts if text][:TEXT_LIMIT]
