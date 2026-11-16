"""[catalog/bibliographic-sources] 세 출처 결과를 필드별 기준 출처로 합치기."""

from datetime import date

from app.central.external.data4library.parsing import Data4LibraryRecord, parse_book
from app.central.external.kakao.parsing import KakaoRecord, parse_document
from app.central.external.yes24.parsing import Yes24Item, parse_item
from app.central.models import ExternalSource
from app.central.sources import LookupOutcome, OfficialValues, merge
from tests.helpers import VALID_ISBN, VALID_ISBN_2
from tests.source_helpers import d4l_book, kakao_document
from tests.yes24_helpers import item


def _d4l(isbn: str = VALID_ISBN, **overrides) -> Data4LibraryRecord:
    return parse_book(d4l_book(isbn, **overrides))


def _kakao(isbn: str = VALID_ISBN, **overrides) -> KakaoRecord:
    return parse_document(kakao_document(isbn, **overrides))


def _yes24(isbn: str = VALID_ISBN, **overrides) -> Yes24Item:
    return parse_item(item(isbn, **overrides))


def _merged(d4l: list, kakao: list, yes24: list | None = None) -> OfficialValues:
    values = merge(VALID_ISBN, d4l, kakao, yes24 or [])
    assert isinstance(values, OfficialValues)
    return values


def test_both_sources() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 두 출처가 모두 있음"""
    d4l = _d4l(bookname="아몬드 :손원평 장편소설", class_no="813.7", addition_symbol="03810")
    values = _merged([d4l], [_kakao(title="아몬드(양장본)", price=14000)])
    assert (values.title, values.subtitle) == ("아몬드", "손원평 장편소설")
    assert values.author == "지은이: 권정생 ;그림: 정승각"
    assert (values.kdc, values.addition_symbol) == ("813.7", "03810")
    assert values.kdc_name == "문학 > 한국문학 > 동화"
    assert values.category is None  # 분류 원문은 YES24에서만
    assert values.list_price == 14000
    assert values.cover_url == "https://search1.kakaocdn.net/thumb/cover"
    assert values.url.startswith("https://search.daum.net/")
    assert values.published_date == date(1996, 4, 1)  # 카카오 먼저
    assert values.series_name is None and values.series_names == ()
    assert values.table_of_contents is None


def test_only_kakao() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 정보나루와 YES24에 없는 책"""
    values = _merged([], [_kakao()])
    assert values.source is ExternalSource.KAKAO
    assert (values.title, values.author, values.publisher) == ("강아지똥", "권정생", "길벗어린이")
    assert values.description == "강아지똥이 민들레 꽃을 피워 내는"
    assert values.kdc is None and values.addition_symbol is None and values.kdc_name is None
    assert values.subtitle is None


def test_only_data4library() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 (카카오에 없는 책: 정가·표지·링크가 빈다)"""
    values = _merged([_d4l()], [])
    assert values.source is ExternalSource.DATA4LIBRARY
    assert values.list_price is None and values.cover_url is None and values.url is None
    assert values.published_date is None  # 정보나루 출간일이 해뿐이다


def test_title_and_author_come_from_one_source() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 서명과 저자를 섞지 않음"""
    values = _merged([_d4l(authors="")], [_kakao(title="카카오 서명", authors=["카카오 저자"])])
    assert values.source is ExternalSource.KAKAO
    assert (values.title, values.author) == ("카카오 서명", "카카오 저자")
    assert values.subtitle is None  # 정보나루 서명에서 나눈 부제도 쓰지 않는다
    assert values.kdc == "813.8"  # 서명·저자 밖의 정보나루 값은 쓴다


def test_description_falls_back_to_kakao() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 정보나루 소개가 비어 있음"""
    values = _merged([_d4l(description="")], [_kakao(contents="카카오 소개")])
    assert values.description == "카카오 소개"
    assert values.field_sources["description"] == "kakao"


def test_year_only_date_is_empty() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 해만 있는 출간일"""
    values = _merged([_d4l(publication_date="2017")], [_kakao(datetime="")])
    assert values.published_date is None
    assert "published_date" not in values.field_sources
    full = _merged([_d4l(publication_date="2017-03-31")], [_kakao(datetime="")])
    assert full.published_date == date(2017, 3, 31)
    assert full.field_sources["published_date"] == "data4library"


def test_no_title_or_author_anywhere() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 세 출처 모두 서명·저자 없음"""
    assert merge(VALID_ISBN, [_d4l(authors="")], [_kakao(authors=[])]) is LookupOutcome.NOT_FOUND
    no_author = [_d4l(authors="")], [_kakao(authors=[])], [_yes24(author="")]
    assert merge(VALID_ISBN, *no_author) is LookupOutcome.NOT_FOUND
    assert merge(VALID_ISBN, [], []) is LookupOutcome.NOT_FOUND


def test_field_sources() -> None:
    """[catalog/bibliographic-sources] 필드별 출처 기록 / 출처 기록"""
    values = _merged([_d4l()], [_kakao()])
    assert values.source is ExternalSource.DATA4LIBRARY
    assert values.field_sources == {
        "addition_symbol": "data4library",
        "cover_url": "kakao",
        "description": "data4library",
        "external_url": "kakao",
        "kdc": "data4library",
        "kdc_name": "data4library",
        "list_price": "kakao",
        "published_date": "kakao",
        "publisher": "data4library",
        "subtitle": "data4library",
    }


def test_empty_field_has_no_source() -> None:
    """[catalog/bibliographic-sources] 필드별 출처 기록 / 빈 필드"""
    values = _merged([_d4l()], [_kakao(price=0)])
    assert values.list_price is None
    assert "list_price" not in values.field_sources
    assert "volume" not in values.field_sources


def test_other_isbn_only_is_mismatch() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 / 다른 ISBN 문서만 있음"""
    assert merge(VALID_ISBN, [], [_kakao(VALID_ISBN_2)]) is LookupOutcome.MISMATCH


def test_one_source_matches() -> None:
    """[catalog/book-enrichment] ISBN 일치 확인 / 한 출처만 일치"""
    values = _merged([_d4l()], [_kakao(VALID_ISBN_2, price=99000)])
    assert values.source is ExternalSource.DATA4LIBRARY
    assert values.list_price is None  # 다른 ISBN의 카카오 값은 쓰지 않는다
    assert set(values.field_sources.values()) == {"data4library"}


def test_picks_matching_document_among_many() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 (여러 문서 중 같은 ISBN의 문서)"""
    values = _merged([], [_kakao(VALID_ISBN_2, title="다른 책"), _kakao(title="맞는 책")])
    assert values.title == "맞는 책"


# --- YES24가 함께 있을 때 ---


def test_three_sources() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 세 출처가 모두 있음"""
    yes24 = _yes24(
        title="강아지똥 (개정판)",
        author="권정생 글/정승각 그림",
        series=[{"seriesName": "민들레그림책"}, {"seriesName": "우리 그림책"}],
        contentDetail={"bookIntroduction": "YES24의 긴 소개", "tableOfContents": "1장"},
    )
    values = _merged([_d4l()], [_kakao()], [yes24])
    assert (values.title, values.source) == ("강아지똥 (개정판)", ExternalSource.YES24)
    assert values.author == "권정생 글/정승각 그림"
    assert values.description == "YES24의 긴 소개"
    assert values.table_of_contents == "1장"
    assert values.series_name == "민들레그림책, 우리 그림책"
    assert values.series_names == ("민들레그림책", "우리 그림책")
    assert values.category == "국내도서-유아"
    assert values.kdc == "813.8"
    assert values.list_price == 14000  # 카카오 먼저
    assert values.published_date == date(1996, 4, 1)
    assert values.cover_url == "https://image.yes24.com/goods/15320/L"
    assert values.url == "https://www.yes24.com/product/goods/15320"
    sources = values.field_sources
    assert (sources["description"], sources["series_name"], sources["cover_url"]) == (
        "yes24",
        "yes24",
        "yes24",
    )
    assert (sources["external_url"], sources["list_price"]) == ("yes24", "kakao")


def test_yes24_head_when_data4library_missing() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 정보나루에 없는 책"""
    values = _merged([], [_kakao(title="카카오 서명")], [_yes24(subTitle="부제")])
    assert values.source is ExternalSource.YES24
    assert (values.title, values.subtitle) == ("강아지똥", "부제")
    assert values.author == "권정생 글/정승각 그림"


def test_description_order() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 소개 순서 (YES24, 정보나루, 카카오)"""
    no_intro = {"bookIntroduction": None, "bookSummary": None}
    values = _merged([_d4l()], [_kakao()], [_yes24(contentDetail=no_intro)])
    assert values.description == "강아지똥이 민들레 꽃을 피워 내는 이야기"
    assert values.field_sources["description"] == "data4library"
    values = _merged([_d4l(description="")], [_kakao()], [_yes24(contentDetail=no_intro)])
    assert values.field_sources["description"] == "kakao"


def test_cover_and_link_from_one_source() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 표지와 링크는 한 출처"""
    values = _merged([_d4l()], [_kakao()], [_yes24(cover="")])
    assert values.cover_url is None  # YES24 링크가 있어 YES24 쌍을 고른다
    assert values.url == "https://www.yes24.com/product/goods/15320"
    values = _merged([_d4l()], [_kakao()], [_yes24(cover="", link="")])
    assert values.cover_url == "https://search1.kakaocdn.net/thumb/cover"
    assert values.field_sources["external_url"] == "kakao"


def test_price_falls_back_to_yes24() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 정가 (카카오, 없으면 YES24)"""
    values = _merged([_d4l()], [_kakao(price=0)], [_yes24(shopPrice=13000)])
    assert values.list_price == 13000
    assert values.field_sources["list_price"] == "yes24"


def test_yes24_other_isbn_is_ignored() -> None:
    """[catalog/book-enrichment] ISBN 일치 확인 / 한 출처만 일치 (YES24 다른 ISBN)"""
    values = _merged([_d4l()], [], [_yes24(VALID_ISBN_2, shopPrice=99000)])
    assert values.list_price is None
    assert "yes24" not in values.field_sources.values()


def test_data4library_head_when_yes24_missing() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / YES24에 없는 책"""
    values = _merged([_d4l()], [_kakao(title="카카오 서명")], [])
    assert values.source is ExternalSource.DATA4LIBRARY
    assert (values.title, values.subtitle) == ("강아지똥", "권정생 그림책")


def test_yes24_without_author_falls_to_data4library() -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 서명과 저자를 섞지 않음 (YES24)"""
    values = _merged([_d4l()], [_kakao()], [_yes24(author="")])
    assert values.source is ExternalSource.DATA4LIBRARY
    assert (values.title, values.author) == ("강아지똥", "지은이: 권정생 ;그림: 정승각")


def test_field_sources_three() -> None:
    """[catalog/bibliographic-sources] 필드별 출처 기록 / 출처 기록 (세 출처)"""
    values = _merged([_d4l()], [_kakao()], [_yes24()])
    assert values.source is ExternalSource.YES24
    sources = values.field_sources
    assert (sources["list_price"], sources["description"], sources["cover_url"]) == (
        "kakao",
        "yes24",
        "yes24",
    )
    assert sources["kdc"] == "data4library"
