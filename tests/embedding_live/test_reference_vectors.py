"""[catalog/book-embeddings] 실행 방식을 바꿔도 같은 벡터가 나온다.

기준 벡터(`data/reference_vectors.json`)는 원본 가중치(Candle 실행기)로 만들었다. 지금 떠 있는 서버
(ONNX 변환본 등)가 같은 모델 이름을 쓰려면 문서와 질의 모두 코사인 0.999 이상이어야 한다.
미달이면 같은 모델이 아니므로 `EMBEDDING_MODEL`을 따로 두고 다시 적재해야 한다.
"""

import json

import pytest

from app.central.external.tei import TeiEmbedder
from tests.embedding_live.reference import DOCUMENTS, QUERIES, REFERENCE_FILE, encode

SAME_MODEL_COSINE = 0.999


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@pytest.fixture(scope="module")
def reference() -> dict:
    return json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))


def test_reference_file_matches_texts(reference: dict) -> None:
    """[catalog/book-embeddings] 인코더 교체 (기준 벡터 파일이 기준 문장과 맞다)"""
    assert len(reference["documents"]) == len(DOCUMENTS)
    assert len(reference["queries"]) == len(QUERIES)
    assert {len(v) for v in reference["documents"] + reference["queries"]} == {1024}


async def test_same_vectors_as_reference(embedder: TeiEmbedder, reference: dict) -> None:
    """[catalog/book-embeddings] 인코더 교체 / 모델 이름 기록 (같은 이름이면 같은 벡터)

    문서 5개(입력 한도를 넘는 것 하나 포함)와 질의 2개(접두어 경로)를 기준 벡터와 비교한다.
    """
    assert embedder.name == reference["model_name"]
    current = await encode(embedder)
    for kind in ("documents", "queries"):
        cosines = [
            _cosine(now, then) for now, then in zip(current[kind], reference[kind], strict=True)
        ]
        assert min(cosines) >= SAME_MODEL_COSINE, (kind, [round(c, 6) for c in cosines])
