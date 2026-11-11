"""[catalog/book-embeddings] TEI 어댑터: 문서·질의 구분, 요청 형식, 오류 구분. 서버 없이 돈다."""

import json

import httpx
import pytest

from app.central.embedding import EmbeddingError, EmbeddingFailure
from app.central.external.tei import TeiEmbedder
from app.core.config import get_settings

MODEL = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"


class FakeTei:
    def __init__(self, *, dim: int = 1024, info: dict | None = None, status: int = 200) -> None:
        self.dim = dim
        self.status = status
        self.info = info or {"served_model_name": MODEL, "max_input_length": 512}
        self.bodies: list[dict] = []
        self.error: Exception | None = None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.error is not None:
            raise self.error
        if request.url.path == "/info":
            return httpx.Response(200, json=self.info)
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status != 200:
            return httpx.Response(
                self.status, json={"error": "비밀 입력 문장", "error_type": "Backend"}
            )
        return httpx.Response(200, json=[[0.0] * self.dim for _ in body["inputs"]])

    def embedder(self) -> TeiEmbedder:
        http = httpx.AsyncClient(
            base_url="http://tei.test", transport=httpx.MockTransport(self._handle)
        )
        return TeiEmbedder(http, get_settings())


def test_name_and_dim_come_from_settings() -> None:
    """[catalog/book-embeddings] 인코더 교체 (모델 이름과 차원)"""
    embedder = FakeTei().embedder()
    assert (embedder.name, embedder.dim) == (MODEL, 1024)


async def test_query_gets_prefix() -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 / 질의 접두어"""
    fake = FakeTei()
    vectors = await fake.embedder().encode_queries(["공룡 책"])
    assert fake.bodies[0]["inputs"] == ["query: 공룡 책"]
    assert "prompt_name" not in fake.bodies[0]
    assert len(vectors) == 1 and len(vectors[0]) == 1024


async def test_document_has_no_prefix() -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 / 문서에는 접두어 없음"""
    fake = FakeTei()
    await fake.embedder().encode_documents(["공룡 대탐험\n소개", "둘째 책"])
    assert fake.bodies[0]["inputs"] == ["공룡 대탐험\n소개", "둘째 책"]


async def test_requests_normalize_and_truncate() -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 / 정규화 요청"""
    fake = FakeTei()
    embedder = fake.embedder()
    await embedder.encode_documents(["문서"])
    await embedder.encode_queries(["질의"])
    assert [(b["normalize"], b["truncate"]) for b in fake.bodies] == [(True, True)] * 2


async def test_dimension_mismatch_is_an_error() -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 / 차원 불일치"""
    with pytest.raises(EmbeddingError) as caught:
        await FakeTei(dim=768).embedder().encode_documents(["문서"])
    assert caught.value.failure is EmbeddingFailure.BAD_RESPONSE
    assert "768" in str(caught.value)


async def test_empty_input_does_not_call_server() -> None:
    """[catalog/book-embeddings] 문서와 질의 인코딩 구분 (빈 입력)"""
    fake = FakeTei()
    assert await fake.embedder().encode_documents([]) == []
    assert fake.bodies == []


async def test_unreachable() -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 임베딩 서버가 꺼져 있음 (오류 구분)"""
    fake = FakeTei()
    fake.error = httpx.ConnectError("connection refused")
    with pytest.raises(EmbeddingError) as caught:
        await fake.embedder().encode_documents(["문서"])
    assert caught.value.failure is EmbeddingFailure.UNREACHABLE


async def test_timeout_is_a_server_error() -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 (응답 시간 초과)"""
    fake = FakeTei()
    fake.error = httpx.ReadTimeout("timeout")
    with pytest.raises(EmbeddingError) as caught:
        await fake.embedder().encode_documents(["문서"])
    assert caught.value.failure is EmbeddingFailure.SERVER_ERROR


async def test_server_error_hides_input() -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 (서버 오류에 입력을 남기지 않는다)"""
    with pytest.raises(EmbeddingError) as caught:
        await FakeTei(status=500).embedder().encode_documents(["비밀 입력 문장"])
    assert caught.value.failure is EmbeddingFailure.SERVER_ERROR
    assert "500" in str(caught.value) and "Backend" in str(caught.value)
    assert "비밀" not in str(caught.value)


async def test_check_passes_for_configured_model() -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 다른 모델이 떠 있음 (같은 모델)"""
    await FakeTei().embedder().check()


@pytest.mark.parametrize(
    "info",
    [
        {"served_model_name": "BAAI/bge-m3", "max_input_length": 512},
        {"model_id": "BAAI/bge-m3", "max_input_length": 512},
        {"served_model_name": MODEL, "max_input_length": 8192},
    ],
)
async def test_check_rejects_other_model_or_limit(info: dict) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 다른 모델이 떠 있음"""
    with pytest.raises(EmbeddingError) as caught:
        await FakeTei(info=info).embedder().check()
    assert caught.value.failure is EmbeddingFailure.MODEL_MISMATCH
