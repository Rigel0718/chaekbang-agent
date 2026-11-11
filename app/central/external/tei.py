"""Text Embeddings Inference(TEI) 어댑터. TEI의 요청·응답 형식은 이 파일 밖으로 나가지 않는다.

- 문서는 그대로, 질의는 모델이 정한 접두어를 붙여 보낸다. TEI의 `prompt_name`을 쓰지 않고 앱이
  문자열을 붙인다(결과는 같다). 접두어 규칙을 이 구현 안에 두어야 모델을 바꿀 때 한 곳만 고친다.
- `normalize`와 `truncate`를 항상 켠다. 길이 한도는 서버가 정한다(`docker/embedder/start.sh`가
  모델 폴더의 한도를 EMBEDDING_MAX_TOKENS로 낮춘다). `check()`가 서버의 한도와 설정을 비교한다.
- 오류 메시지에 입력 텍스트를 넣지 않는다.
"""

from collections.abc import Sequence
from typing import Any

import httpx

from app.central.embedding import EmbeddingError, EmbeddingFailure
from app.core.config import Settings, get_settings

# 모델별 질의 접두어. 모델 저장소 `config_sentence_transformers.json`의 `prompts.query`와 같다.
# 없는 모델은 접두어 없이 인코딩한다.
QUERY_PREFIXES = {
    "dragonkue/snowflake-arctic-embed-l-v2.0-ko": "query: ",
    "Snowflake/snowflake-arctic-embed-l-v2.0": "query: ",
    "nlpai-lab/KURE-v1": "",
}

EMBED_PATH = "/embed"
INFO_PATH = "/info"


class TeiEmbedder:
    def __init__(self, http: httpx.AsyncClient, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._http = http
        self.name = settings.embedding_model
        self.dim = settings.embedding_dim
        self.max_tokens = settings.embedding_max_tokens
        self.query_prefix = QUERY_PREFIXES.get(self.name, "")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise EmbeddingError(EmbeddingFailure.SERVER_ERROR, "응답 시간 초과") from exc
        except httpx.TransportError as exc:
            raise EmbeddingError(EmbeddingFailure.UNREACHABLE, type(exc).__name__) from exc
        if response.status_code != httpx.codes.OK:
            raise EmbeddingError(EmbeddingFailure.SERVER_ERROR, _error_detail(response))
        try:
            return response.json()
        except ValueError as exc:
            raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "JSON이 아닙니다") from exc

    async def check(self) -> None:
        """서버가 설정한 모델과 길이 한도로 떠 있는지 확인한다."""
        info = await self._request("GET", INFO_PATH)
        if not isinstance(info, dict):
            raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "서버 정보 형식이 다릅니다")
        served = info.get("served_model_name") or info.get("model_id")
        if served != self.name:
            raise EmbeddingError(
                EmbeddingFailure.MODEL_MISMATCH, f"서버 모델 {served}, 설정 {self.name}"
            )
        limit = info.get("max_input_length")
        if limit != self.max_tokens:
            raise EmbeddingError(
                EmbeddingFailure.MODEL_MISMATCH,
                f"서버 입력 한도 {limit}토큰, 설정 {self.max_tokens}토큰",
            )

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = await self._request(
            "POST", EMBED_PATH, json={"inputs": list(texts), "normalize": True, "truncate": True}
        )
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "벡터 수가 입력과 다릅니다")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dim:
                size = len(vector) if isinstance(vector, list) else "?"
                raise EmbeddingError(
                    EmbeddingFailure.BAD_RESPONSE, f"벡터 차원 {size}, 설정 {self.dim}"
                )
        return vectors

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed([f"{self.query_prefix}{text}" for text in texts])


def _error_detail(response: httpx.Response) -> str:
    """상태 코드와 TEI의 오류 종류만 남긴다. 오류 문장에는 입력 일부가 들어갈 수 있다."""
    try:
        kind = response.json().get("error_type")
    except (ValueError, AttributeError):
        kind = None
    return f"HTTP {response.status_code}" + (f" {kind}" if kind else "")
