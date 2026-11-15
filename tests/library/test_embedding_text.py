"""[catalog/book-embeddings] 임베딩 텍스트 구성. DB 없이 모델 객체만으로 확인한다."""

from app.central.embedding_text import official_embedding_text
from app.central.models import Book
from app.library.models.catalog import LibraryBook
from app.library.recommendation.embedding_text import library_embedding_text


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
    _own(book=official, title="기관 서명", description="기관 소개")
    text = official_embedding_text(official)
    assert text == "공식 서명: 부제\n국내도서>어린이>과학 문학\n공룡을 좋아하는 아이의 이야기"
    assert "기관" not in text


def test_official_without_description_stays_official() -> None:
    """[catalog/book-embeddings] 공식 서지 벡터에 기관 값 없음 / 공식 서지에 없는 소개"""
    official = Book(title="공식 서명", author="공식 저자", description=None)
    _own(book=official, description="기관 소개")
    assert official_embedding_text(official) == "공식 서명"


def test_blank_fields_are_skipped() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 빈 값 건너뛰기"""
    assert library_embedding_text(_own(description="  ", kdc=None)) == "기관 서명"
    assert official_embedding_text(Book(title="공식 서명", author="공식 저자")) == "공식 서명"


def test_author_is_left_out() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 저자 미포함"""
    official = Book(
        title="별을 세는 밤",
        author="칼 멜링 글/브라이트 스타 그림",
        external_category="국내도서>유아",
        description="밤하늘 이야기",
    )
    own = _own(isbn=None, author="칼 멜링 글/브라이트 스타 그림", description="밤하늘 이야기")
    for text in (official_embedding_text(official), library_embedding_text(own)):
        assert "멜링" not in text
        assert "브라이트" not in text
        assert "그림" not in text


def test_book_without_isbn_uses_own_values() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / ISBN 없는 책"""
    text = library_embedding_text(_own(isbn=None, kdc="490", description="동물 도감"))
    assert text == "기관 서명\n자연과학\n동물 도감"


def test_library_text_ignores_linked_official_values() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성

    기관 도서 텍스트는 기관 값만 쓴다(`shown`을 쓰지 않는다).
    """
    official = Book(title="공식 서명", author="공식 저자", description="공식 소개")
    assert library_embedding_text(_own(book=official, description=None)) == "기관 서명"


def test_same_values_same_text() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 같은 값 같은 텍스트"""
    assert library_embedding_text(_own(description="소개")) == library_embedding_text(
        _own(description="소개")
    )


def test_both_layers_use_the_same_rule() -> None:
    """[catalog/book-embeddings] 임베딩 텍스트 구성 / 두 층의 같은 조립 규칙"""
    official = Book(title="같은 서명", author="같은 저자", kdc="911", description="같은 소개")
    own = _own(isbn=None, title="같은 서명", author="같은 저자", kdc="911", description="같은 소개")
    assert official_embedding_text(official) == library_embedding_text(own)
    assert official_embedding_text(official) == "같은 서명\n역사\n같은 소개"
