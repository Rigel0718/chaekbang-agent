"""[catalog/book-embeddings] 실제 임베딩 서버로 확인하는 인코딩 규칙."""

import math

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.tei import TeiEmbedder
from app.library.recommendation.embeddings import run_embedding, similar_books
from evals.librarian.catalog import DATA_FILE, Sample, load_catalog, load_sample

QUERY = "공룡을 좋아하는 아이에게 읽어 줄 책"


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def _embed(http: httpx.AsyncClient, **body) -> list[float]:
    response = await http.post("/embed", json={"normalize": True, "truncate": True, **body})
    response.raise_for_status()
    return response.json()[0]


async def test_server_matches_settings(embedder: TeiEmbedder) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 다른 모델이 떠 있음 (실제 서버 확인)"""
    await embedder.check()


async def test_vectors_are_normalized_with_model_dim(embedder: TeiEmbedder) -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 (길이 1, 1024차원)"""
    document = (await embedder.encode_documents(["공룡 대탐험\n공룡 화석을 찾는 이야기"]))[0]
    query = (await embedder.encode_queries([QUERY]))[0]
    for vector in (document, query):
        assert len(vector) == embedder.dim == 1024
        assert math.sqrt(_cosine(vector, vector)) == pytest.approx(1.0, abs=1e-4)


async def test_app_prefix_equals_prompt_name(
    embedder: TeiEmbedder, http: httpx.AsyncClient
) -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 / 질의 접두어

    앱이 붙인 접두어가 모델 설정의 `prompts.query`(sentence-transformers의 prompt_name="query")와
    같은 벡터를 낸다. 접두어 없는 인코딩과는 다르다.
    """
    ours = (await embedder.encode_queries([QUERY]))[0]
    theirs = await _embed(http, inputs=[QUERY], prompt_name="query")
    plain = (await embedder.encode_documents([QUERY]))[0]
    assert _cosine(ours, theirs) > 0.999
    assert _cosine(ours, plain) < 0.99


async def test_long_text_is_cut_at_token_limit(
    embedder: TeiEmbedder, http: httpx.AsyncClient
) -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 (길이 한도를 넘으면 앞부분만 인코딩)

    한도는 문장 시작·끝 토큰 2개를 포함한다. 한도까지의 앞부분만 넣은 벡터와 같아야 한다.
    """
    long_text = "".join(f"{i}번째 공룡 화석을 찾아 떠나는 모험 이야기. " for i in range(400))
    tokens = (await http.post("/tokenize", json={"inputs": long_text})).json()[0]
    normal = [t for t in tokens if not t["special"]]
    assert len(tokens) > embedder.max_tokens * 2
    # TEI의 토큰 위치는 UTF-8 바이트 기준이다
    raw = long_text.encode()
    head = raw[: normal[embedder.max_tokens - 3]["stop"]].decode()
    shorter = raw[: normal[embedder.max_tokens // 2]["stop"]].decode()

    whole = (await embedder.encode_documents([long_text]))[0]
    assert _cosine(whole, (await embedder.encode_documents([head]))[0]) > 0.9999
    assert _cosine(whole, (await embedder.encode_documents([shorter]))[0]) < 0.9999

    refused = await http.post("/embed", json={"inputs": [long_text], "truncate": False})
    assert refused.status_code == 422  # 잘라내기를 끄면 서버가 거부한다. 한도가 서버에 걸려 있다


@pytest.mark.sample
async def test_sample_subset_full_then_incremental(
    session: AsyncSession, embedder: TeiEmbedder
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 증분 재실행은 0건 (실제 서버, 표본 일부)"""
    if not DATA_FILE.exists():
        pytest.skip(f"표본이 없습니다: {DATA_FILE}")
    sample = load_sample(DATA_FILE)
    subset = Sample(sample.fetched_on, sorted(sample.books, key=lambda r: r["isbn13"])[:6])
    catalog = await load_catalog(session, subset)

    full = await run_embedding(
        session, embedder, full=True, library_id=catalog.library_id, batch_size=4
    )
    assert full.stopped is None and full.encoded == full.targets > 0
    again = await run_embedding(
        session, embedder, full=False, library_id=catalog.library_id, batch_size=4
    )
    assert (again.encoded, again.skipped) == (0, full.targets)

    title = next(iter(catalog.titles.values()))
    found = await similar_books(session, embedder, library_id=catalog.library_id, query=title)
    assert found and found[0].similarity > found[-1].similarity - 1e-9
    assert {f.library_book.library_id for f in found} == {catalog.library_id}
