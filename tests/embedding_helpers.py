"""가짜 인코더. 임베딩 서버 없이 적재와 조회를 테스트한다."""

import hashlib
import math
import random
from collections.abc import Sequence

from app.central.embedding import EmbeddingError, EmbeddingFailure

FAKE_DIM = 1024


def unit(*head: float) -> list[float]:
    """앞 성분만 준 FAKE_DIM차원 벡터를 길이 1로 맞춘다."""
    norm = math.sqrt(sum(x * x for x in head))
    return [x / norm for x in head] + [0.0] * (FAKE_DIM - len(head))


def toward(cosine: float) -> list[float]:
    """`unit(1)`과의 코사인 유사도가 cosine인 벡터."""
    return unit(cosine, math.sqrt(1 - cosine * cosine))


def hashed_vector(text: str) -> list[float]:
    """텍스트로 정해지는 정규화 벡터."""
    rng = random.Random(hashlib.sha256(text.encode()).digest())
    values = [rng.gauss(0, 1) for _ in range(FAKE_DIM)]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


class FakeEmbedder:
    """호출을 기록한다. `vectors`의 낱말이 텍스트에 있으면 그 벡터를, 없으면 해시 벡터를 준다.

    `fail_on`번째 문서 인코딩 호출(1부터)에서 `failure`로 실패한다.
    """

    def __init__(
        self,
        name: str = "fake-model",
        *,
        vectors: dict[str, list[float]] | None = None,
        fail_on: int | None = None,
        failure: EmbeddingFailure = EmbeddingFailure.SERVER_ERROR,
    ) -> None:
        self.name = name
        self.dim = FAKE_DIM
        self.vectors = vectors or {}
        self.fail_on = fail_on
        self.failure = failure
        self.document_calls: list[list[str]] = []
        self.query_calls: list[list[str]] = []

    async def check(self) -> None:
        pass

    def _vector(self, text: str) -> list[float]:
        for word, vector in self.vectors.items():
            if word in text:
                return vector
        return hashed_vector(text)

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        if self.fail_on == len(self.document_calls):
            raise EmbeddingError(self.failure, "가짜 실패")
        return [self._vector(text) for text in texts]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.query_calls.append(list(texts))
        return [self._vector(text) for text in texts]
