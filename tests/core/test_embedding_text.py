"""[catalog/book-embeddings] 임베딩 텍스트 구성: 두 층이 함께 쓰는 조립 규칙."""

import hashlib

from app.core.embedding_text import TEXT_VERSION, TextKind, compose, content_hash


def _compose(**values) -> str:
    base = {"title": "서명", "subtitle": None, "categories": [], "description": None}
    return compose(TextKind.FULL, **{**base, **values})


def test_blank_fields_are_skipped() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 빈 값 건너뛰기"""
    text = _compose(subtitle="  ", categories=[None, ""], description="   ")
    assert text == "서명"


def test_subtitle_joins_title() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 (부제는 서명 뒤에 붙인다)"""
    assert _compose(subtitle="부제").splitlines()[0] == "서명: 부제"


def test_description_comes_last() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 (잘릴 때 서명·분류가 남는다)"""
    text = _compose(categories=["국내도서>소설", "문학"], description="긴   소개\n둘째 줄")
    assert text.splitlines() == ["서명", "국내도서>소설 문학", "긴 소개 둘째 줄"]


def test_same_values_same_text_and_hash() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 같은 값 같은 텍스트"""
    first = _compose(description="소개")
    second = _compose(description="소개")
    assert first == second
    assert content_hash(first) == content_hash(second)
    assert content_hash(first) == hashlib.sha256(first.encode()).hexdigest()
    assert len(content_hash(first)) == 64
    assert content_hash(first) != content_hash(_compose(description="다른 소개"))


def test_text_version_is_two() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 (규칙이 바뀌면 번호가 오른다: 저자를 빼서 2)"""
    assert TEXT_VERSION == 2
    assert TextKind.FULL == "full"
