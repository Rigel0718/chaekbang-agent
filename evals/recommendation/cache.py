"""질의 벡터(선택으로 문서 벡터) 캐시. 같은 텍스트를 다시 인코딩하지 않아 수치가 같다.

캐시가 다 차 있으면 임베딩 서버 없이 돈다. 키는 모델 이름과 텍스트의 해시이고, 문서는 질의와 다른
키(`doc` 줄)로 다른 파일에 둔다. 질의 인코딩은 문서의 텍스트 종류와 상관없어 모든 변형이 같은 벡터를
쓴다. 문서 캐시는 AI 사서 평가 표본 적재가 쓴다(`doc_path`). 없으면 문서 인코딩을 막는다(실험은 개발
DB에 이미 적재된 벡터만 쓴다). 캐시에 없는 텍스트가 있으면 처음 한 번 안쪽 인코더를 `check()`한다.
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

    def __init__(
        self, inner: Embedder, path: Path = CACHE_FILE, doc_path: Path | None = None
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self.path = path
        self.vectors = _read(path)
        self.doc_path = doc_path
        self.doc_vectors = _read(doc_path) if doc_path is not None else {}
        self.encoded = 0  # 이번 실행에서 새로 인코딩한 질의 수
        self.encoded_documents = 0
        self.cached_documents = 0  # 캐시에서 꺼낸 문서 수
        self.checked = False

    def _key(self, text: str, kind: str = "") -> str:
        prefix = f"{self.name}\n{kind}\n" if kind else f"{self.name}\n"
        return hashlib.sha256(f"{prefix}{text}".encode()).hexdigest()

    async def check(self) -> None:
        await self.inner.check()
        self.checked = True

    async def _fill(self, texts, vectors, key, encode, path) -> int:
        missing = [text for text in dict.fromkeys(texts) if key(text) not in vectors]
        if missing:
            if not self.checked:
                await self.check()
            for text, vector in zip(missing, await encode(missing), strict=True):
                vectors[key(text)] = vector
            _write(path, vectors)
        return len(missing)

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.doc_path is None:
            raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "실험은 문서를 인코딩하지 않는다")

        def key(text: str) -> str:
            return self._key(text, "doc")

        new = await self._fill(
            texts, self.doc_vectors, key, self.inner.encode_documents, self.doc_path
        )
        self.encoded_documents += new
        self.cached_documents += len(texts) - new
        return [self.doc_vectors[key(text)] for text in texts]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.encoded += await self._fill(
            texts, self.vectors, self._key, self.inner.encode_queries, self.path
        )
        return [self.vectors[self._key(text)] for text in texts]
