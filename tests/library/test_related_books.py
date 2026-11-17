"""[catalog/related-recommendation] 관련 책의 제품 경로: 최소 유사도, 근거 문구, 범위 훅, service.

가짜 인코더로 적재하고 저장된 벡터로 조회한다(질의 인코딩 없음).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.tei import TeiEmbedder
from app.central.official_embeddings import run_official_embedding
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.library import hooks
from app.library.models.catalog import LibraryBook
from app.library.recommendation.basis import basis_codes, basis_texts
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.related import (
    AUTHOR,
    KDC,
    POPULAR,
    SERIES,
    VECTOR,
    HistorySettings,
    SimilarSettings,
    find_from_history,
    find_similar,
)
from app.library.services.related import related_for_session, similar_for_book
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.library.test_related_recommendation import MODEL, linked, load, unlinked

WRITER = "한작가 저"


async def _ids(session: AsyncSession, library_id: int, base: int, **options) -> list[int]:
    found = await find_similar(
        session, MODEL, library_id=library_id, library_book_id=base, **options
    )
    return [item.library_book_id for item in found]


# --- 벡터 근거만 있는 책의 최소 유사도 ---


async def _weak_neighbors(session: AsyncSession, library_id: int) -> dict[str, int]:
    ids = {
        "base": await linked(session, library_id, "기준", author=WRITER),
        "near": await unlinked(session, library_id, "가까운책"),
        "weak": await unlinked(session, library_id, "먼책"),
        "writer": await linked(session, library_id, "작가책", author=WRITER),
    }
    await load(session, library_id, {"가까운책": 0.9, "먼책": 0.4, "작가책": 0.4})
    return ids


async def test_weak_vector_only_book_is_dropped(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 벡터 근거만 있는 책의 최소 유사도

    문턱 아래의 벡터 근거만 있는 책
    """
    ids = await _weak_neighbors(session, library_a.id)
    found = await _ids(
        session,
        library_a.id,
        ids["base"],
        settings=SimilarSettings(min_vector_similarity=0.5),
    )
    assert ids["weak"] not in found
    assert ids["near"] in found


async def test_rule_evidence_keeps_weak_vector(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 벡터 근거만 있는 책의 최소 유사도 / 규칙 근거가 있는 책"""
    ids = await _weak_neighbors(session, library_a.id)
    found = await _ids(
        session,
        library_a.id,
        ids["base"],
        settings=SimilarSettings(min_vector_similarity=0.5),
    )
    assert ids["writer"] in found


async def test_no_threshold_by_default(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 벡터 근거만 있는 책의 최소 유사도 / 기본값"""
    ids = await _weak_neighbors(session, library_a.id)
    assert SimilarSettings().min_vector_similarity is None
    default = await _ids(session, library_a.id, ids["base"])
    assert ids["weak"] in default
    assert default == await _ids(
        session, library_a.id, ids["base"], settings=SimilarSettings(min_vector_similarity=None)
    )


# --- 근거 문구 ---


def test_series_and_vector_basis() -> None:
    """[catalog/related-recommendation] 근거 문구 / 같은 시리즈와 벡터 이웃"""
    ranks = {VECTOR: 3, SERIES: 1}
    assert basis_codes(ranks) == [SERIES, VECTOR]
    assert basis_texts(ranks) == ["같은 시리즈", "내용이 비슷한 책"]


def test_kdc_basis_shows_section() -> None:
    """[catalog/related-recommendation] 근거 문구 / 분류 문구"""
    assert basis_texts({KDC: 2}, kdc="813.72") == ["같은 분류 813.7"]


def test_two_texts_at_most() -> None:
    """[catalog/related-recommendation] 근거 문구 / 문구 두 개 상한"""
    ranks = {VECTOR: 1, KDC: 4, AUTHOR: 2, SERIES: 1}
    assert basis_codes(ranks) == [SERIES, AUTHOR, KDC, VECTOR]
    assert basis_texts(ranks, kdc="813.7") == ["같은 시리즈", "같은 지은이"]


def test_popular_basis() -> None:
    """[catalog/related-recommendation] 근거 문구 / 인기로 채운 책"""
    assert basis_codes({POPULAR: 1}) == [POPULAR]
    assert basis_texts({POPULAR: 1}, history=True) == ["우리 도서관에서 많이 빌린 책"]


def test_history_basis_wording() -> None:
    """[catalog/related-recommendation] 근거 문구 / 최근 기록 문구(보조)"""
    assert basis_texts({VECTOR: 1}, history=True) == ["최근 본 책과 내용이 비슷한 책"]
    assert basis_codes({"co_loan": 1, VECTOR: 2}) == [VECTOR, "co_loan"]


# --- 제품 service ---


@pytest.fixture
def no_scopes(monkeypatch: pytest.MonkeyPatch) -> list:
    """등록된 범위 제공자를 비운다. 테스트가 넣은 제공자는 끝나면 사라진다."""
    scopes: list = []
    monkeypatch.setattr(hooks, "_related_scopes", scopes)
    return scopes


async def load_product(session: AsyncSession, library_id: int, cosines: dict[str, float]) -> None:
    """제품 경로가 쓰는 모델 이름(설정의 임베딩 모델)으로 두 층을 적재한다."""
    embedder = FakeEmbedder(
        get_settings().embedding_model,
        vectors={"기준": unit(1), **{word: toward(c) for word, c in cosines.items()}},
    )
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)


async def _product_books(session: AsyncSession, library_id: int) -> dict[str, int]:
    ids = {
        "base": await linked(session, library_id, "기준", author=WRITER, series_keys=["묶음"]),
        "series": await linked(session, library_id, "시리즈책", series_keys=["묶음"]),
        "writer": await linked(session, library_id, "작가책", author=WRITER),
        "near": await unlinked(session, library_id, "가까운책"),
        "far": await unlinked(session, library_id, "먼책"),
    }
    await load_product(
        session, library_id, {"시리즈책": 0.2, "작가책": 0.3, "가까운책": 0.9, "먼책": 0.1}
    )
    return ids


def _book_ids(items) -> list[int]:
    return [item.candidate.library_book.id for item in items]


async def test_scope_condition_applies(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 관련 책의 기관 개별 범위 / 등록된 조건"""
    ids = await _product_books(session, library_a.id)
    seen: list = []

    async def only_writer(session, library_id, base_ids):
        seen.append((library_id, list(base_ids)))
        return select(LibraryBook.id).where(LibraryBook.id == ids["writer"])

    no_scopes.append(only_writer)
    found = await similar_for_book(session, library_a.id, ids["base"])
    assert _book_ids(found) == [ids["writer"]]
    assert seen == [(library_a.id, [ids["base"]])]


async def test_no_scope_registered(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 관련 책의 기관 개별 범위 / 등록된 조건 없음"""
    ids = await _product_books(session, library_a.id)
    found = await similar_for_book(session, library_a.id, ids["base"])
    plain = await find_similar(
        session,
        get_settings().embedding_model,
        library_id=library_a.id,
        library_book_id=ids["base"],
    )
    assert _book_ids(found) == [item.library_book_id for item in plain]


async def test_product_path_matches_default(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 기본 설정과 같은 결과(service), 근거"""
    ids = await _product_books(session, library_a.id)
    found = await similar_for_book(session, library_a.id, ids["base"])
    plain = await find_similar(
        session,
        get_settings().embedding_model,
        library_id=library_a.id,
        library_book_id=ids["base"],
        settings=SimilarSettings(),
    )
    assert _book_ids(found) == [item.library_book_id for item in plain]
    by_id = {item.candidate.library_book.id: item for item in found}
    assert by_id[ids["series"]].basis[0] == SERIES
    assert by_id[ids["series"]].basis_text[0] == "같은 시리즈"
    assert by_id[ids["near"]].basis == (VECTOR,)


async def test_product_path_has_no_co_loan(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 제품 경로의 설정 / 함께 대출 없음"""
    ids = await _product_books(session, library_a.id)
    found = await similar_for_book(session, library_a.id, ids["base"])
    assert found
    assert all("co_loan" not in item.basis for item in found)


async def test_empty_history_without_loans_is_empty(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 제품 경로의 설정 / 정보나루 인기로 채우지 않음"""
    await _product_books(session, library_a.id)
    assert HistorySettings().popular_fill
    assert await related_for_session(session, library_a.id, []) == []


async def test_works_without_embedding_server(
    session: AsyncSession, library_a: Tenant, no_scopes: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/related-recommendation] 제품 경로의 설정 / 임베딩 서버 없이 동작"""
    ids = await _product_books(session, library_a.id)

    def no_server(*args, **kwargs):
        raise AssertionError("제품 경로가 임베딩 서버를 불렀다")

    monkeypatch.setattr(TeiEmbedder, "__init__", no_server)
    found = await similar_for_book(session, library_a.id, ids["base"])
    assert ids["near"] in _book_ids(found)
    assert any(VECTOR in item.basis for item in found)


async def test_base_of_other_library_is_not_found(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 다른 기관의 기준 책(service)"""
    other = await unlinked(session, library_b.id, "남의 책")
    with pytest.raises(NotFoundError):
        await similar_for_book(session, library_a.id, other)


async def test_unrecommendable_base_is_not_found(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 추천할 수 없는 기준 책(service)"""
    gone = await unlinked(session, library_a.id, "제적된 책", "withdrawn")
    with pytest.raises(NotFoundError):
        await similar_for_book(session, library_a.id, gone)


async def test_results_stay_in_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, no_scopes: list
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 결과의 기관 범위(service)"""
    ids = await _product_books(session, library_a.id)
    theirs = {
        await unlinked(session, library_b.id, "가까운책 둘"),
        await linked(session, library_b.id, "작가책 둘", author=WRITER),
    }
    await load_product(session, library_b.id, {"가까운책": 0.95, "작가책": 0.9})
    found = set(_book_ids(await similar_for_book(session, library_a.id, ids["base"])))
    assert found and not found & theirs


async def test_session_history_uses_mean(
    session: AsyncSession, library_a: Tenant, no_scopes: list
) -> None:
    """[agent/librarian] 관련 책 tool / 비워서 부름(service): 세션의 책으로 최근 기록"""
    ids = await _product_books(session, library_a.id)
    found = await related_for_session(session, library_a.id, [ids["near"]])
    plain = await find_from_history(
        session,
        get_settings().embedding_model,
        library_id=library_a.id,
        library_book_ids=[ids["near"]],
    )
    assert _book_ids(found) == [item.library_book_id for item in plain]
    assert ids["near"] not in _book_ids(found)
    assert all(text.startswith("최근 본 책과") for item in found for text in item.basis_text)


async def test_session_history_skips_unusable_books(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, no_scopes: list
) -> None:
    """[agent/librarian] 대화 세션의 책 / 추천할 수 없는 책과 다른 기관의 책은 건너뜀, 3권까지"""
    ids = await _product_books(session, library_a.id)
    gone = await unlinked(session, library_a.id, "제적된 책", "withdrawn")
    other = await unlinked(session, library_b.id, "남의 책")
    seen: list = []

    async def record(session, library_id, base_ids):
        seen.append(list(base_ids))
        return None

    no_scopes.append(record)
    history = [gone, other, ids["near"], ids["far"], ids["writer"], ids["series"]]
    await related_for_session(session, library_a.id, history)
    assert seen == [[ids["near"], ids["far"], ids["writer"]]]
