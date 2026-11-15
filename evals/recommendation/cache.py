"""질의 벡터 캐시. 같은 질의는 다시 인코딩하지 않아 같은 명령이 같은 수치를 낸다.

캐시가 다 차 있으면 임베딩 서버 없이 돈다. 키는 모델 이름과 질의 문자열의 해시다. 질의 인코딩은
문서의 텍스트 종류와 상관없어 모든 변형이 같은 벡터를 쓴다.
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from app.central.embedding import Embedder, EmbeddingError, EmbeddingFailure
from evals.recommendation.keys import DATA_DIR

CACHE_FILE = DATA_DIR / "query_vectors.json"


def _read(path: Path) -> dict[str, list[float]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, vectors: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vectors), encoding="utf-8")


class CachedEmbedder:
    """`Embedder`를 감싼다. 질의 벡터를 파일에 두고, 없는 질의만 안쪽 인코더로 인코딩한다."""

    def __init__(self, inner: Embedder, path: Path = CACHE_FILE) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self.path = path
        self.vectors = _read(path)
        self.encoded = 0  # 이번 실행에서 새로 인코딩한 질의 수

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.name}\n{text}".encode()).hexdigest()

    async def check(self) -> None:
        await self.inner.check()

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "실험은 문서를 인코딩하지 않는다")

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [text for text in dict.fromkeys(texts) if self._key(text) not in self.vectors]
        if missing:
            for text, vector in zip(missing, await self.inner.encode_queries(missing), strict=True):
                self.vectors[self._key(text)] = vector
            self.encoded += len(missing)
            _write(self.path, self.vectors)
        return [self.vectors[self._key(text)] for text in texts]
