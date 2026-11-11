"""[catalog/book-embeddings] 임베딩 텍스트 구성. DB 없이 모델 객체만으로 확인한다."""

import hashlib

from app.central.models import Book
from app.library.models.catalog import LibraryBook
from app.library.recommendation.embedding_text import (
    TEXT_VERSION,
    build_embedding_text,
    content_hash,
)


def _own(**values) -> LibraryBook:
    return LibraryBook(**{"title": "기관 서명", "author": "기관 저자", **values})


def test_official_values_first() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 공식 값 먼저"""
    official = Book(
        title="공식 서명",
        author="공식 저자",
        subtitle="부제",
        external_category="국내도서>어린이>과학",
        kdc="813.7",
        description="공룡을  좋아하는\n아이의 이야기",
    )
    text = build_embedding_text(_own(book=official, description="기관 소개"))
    assert text == (
        "공식 서명: 부제\n공식 저자\n국내도서>어린이>과학 문학\n공룡을 좋아하는 아이의 이야기"
    )
    assert "기관 서명" not in text


def test_official_blank_falls_back_to_own() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 공식 값 먼저 (공식 값이 비면 기관 값)"""
    official = Book(title="공식 서명", author="공식 저자", description=None)
    text = build_embedding_text(_own(book=official, description="기관 소개"))
    assert text.splitlines() == ["공식 서명", "공식 저자", "기관 소개"]


def test_blank_fields_are_skipped() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 빈 값 건너뛰기"""
    text = build_embedding_text(_own(description="  ", kdc=None))
    assert text == "기관 서명\n기관 저자"


def test_book_without_isbn_uses_own_values() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / ISBN 없는 책"""
    text = build_embedding_text(_own(isbn=None, kdc="490", description="동물 도감"))
    assert text == "기관 서명\n기관 저자\n자연과학\n동물 도감"


def test_description_comes_last() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 (design 6: 잘릴 때 서명·저자·분류가 남는다)"""
    text = build_embedding_text(_own(kdc="911", description="긴 소개"))
    assert text.splitlines()[-1] == "긴 소개"


def test_same_values_same_text_and_hash() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 같은 값 같은 텍스트"""
    first = build_embedding_text(_own(description="소개"))
    second = build_embedding_text(_own(description="소개"))
    assert first == second
    assert content_hash(first) == content_hash(second)
    assert content_hash(first) == hashlib.sha256(first.encode()).hexdigest()
    assert len(content_hash(first)) == 64
    assert content_hash(first) != content_hash(build_embedding_text(_own(description="다른 소개")))


def test_text_version_is_a_positive_integer() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 (규칙에 버전 번호가 있다)"""
    assert isinstance(TEXT_VERSION, int) and TEXT_VERSION >= 1
