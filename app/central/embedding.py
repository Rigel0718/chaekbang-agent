"""임베딩 인코더 접점. 모델을 실행하는 코드는 어댑터(`external/tei.py`) 하나에 둔다.

문서(도서)와 질의는 규칙이 다르다. 질의 접두어 같은 모델별 규칙은 구현 안에 두고,
부르는 쪽은 두 함수만 안다. 벡터는 길이 1로 정규화돼 있다.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol


class EmbeddingFailure(StrEnum):
    UNREACHABLE = "unreachable"  # 서버에 닿지 않는다
    SERVER_ERROR = "server_error"  # 서버가 오류를 돌려줬다
    BAD_RESPONSE = "bad_response"  # 벡터 수나 차원이 요청과 다르다
    MODEL_MISMATCH = "model_mismatch"  # 서버가 다른 모델을 제공한다


class EmbeddingError(Exception):
    """입력 텍스트는 메시지에 넣지 않는다."""

    def __init__(self, failure: EmbeddingFailure, detail: str = "") -> None:
        super().__init__(f"{failure.value}: {detail}" if detail else failure.value)
        self.failure = failure
        self.detail = detail


class Embedder(Protocol):
    name: str  # 벡터와 함께 저장하는 모델 이름
    dim: int

    async def check(self) -> None:
        """실행 전에 한 번 부른다. 서버가 설정과 다르면 `EmbeddingError`다."""
        ...

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """도서 텍스트를 인코딩한다."""
        ...

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        """검색 질의를 인코딩한다."""
        ...
