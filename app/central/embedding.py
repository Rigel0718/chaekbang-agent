"""임베딩 인코더 접점과 두 층이 함께 쓰는 배치 적재 흐름.

모델을 실행하는 코드는 어댑터(`external/tei.py`) 하나에 둔다. 문서(도서)와 질의는 규칙이 다르다.
질의 접두어 같은 모델별 규칙은 구현 안에 두고, 부르는 쪽은 두 함수만 안다. 벡터는 길이 1로
정규화돼 있다.

배치 흐름(`run_layer`)은 공식 서지 벡터와 기관 도서 벡터가 같이 쓴다. 층은 대상 읽기, 저장된 해시
읽기, 저장만 넘긴다(`EmbeddingLayer`). 인코딩 호출 동안 트랜잭션을 잡지 않고 배치마다 저장을
끝낸다. 중간에 멈춰도 끝난 배치는 남고 증분 적재로 이어 한다.

서비스 중 질의 인코딩은 `GuardedEmbedder`로 감싼다. 시간 제한, 실패 뒤 쉬기, 처음 한 번 모델 확인을
더하고, 실패하면 `EmbeddingError`를 낸다. 실패를 어떻게 다룰지(키워드 순위로 내려가기)는 부르는
쪽이 정한다.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings


class EmbeddingFailure(StrEnum):
    UNREACHABLE = "unreachable"  # 서버에 닿지 않는다
    SERVER_ERROR = "server_error"  # 서버가 오류를 돌려줬다
    BAD_RESPONSE = "bad_response"  # 벡터 수나 차원이 요청과 다르다
    MODEL_MISMATCH = "model_mismatch"  # 서버가 다른 모델을 제공한다
    TIMEOUT = "timeout"  # 시간 제한 안에 답하지 않았다
    PAUSED = "paused"  # 앞의 실패 뒤 쉬는 중이라 부르지 않았다


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


class GuardedEmbedder:
    """서비스 중 질의 인코딩. 안쪽 인코더에 시간 제한, 실패 뒤 쉬기, 처음 한 번 모델 확인을 더한다.

    - 시간 제한을 넘으면 `TIMEOUT`이다. 처음 쓸 때의 모델 확인도 같은 시간 제한 안에 든다.
    - 실패하면 `pause`초 동안 안쪽 인코더를 부르지 않고 바로 `PAUSED`를 낸다(상세에 앞 실패 종류).
    - 모델 확인은 성공하면 다시 하지 않는다. 실패(다른 모델 포함)는 쉬기 뒤 다시 확인한다.
    - 문서는 인코딩하지 않는다. 제품은 저장된 벡터만 쓰고 적재는 운영자 실행이 한다.
    - 잠금을 두지 않는다. 동시에 확인이 두 번 불려도 결과는 같다.
    """

    def __init__(self, inner: Embedder, *, timeout: float, pause: float) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self.timeout = timeout
        self.pause = timedelta(seconds=pause)
        self.checked = False
        self.paused_until: datetime | None = None
        self.last_failure: EmbeddingFailure | None = None
        self.failures = 0  # 실패한 질의 인코딩 수(쉬는 중 포함). 평가가 출력한다

    async def check(self) -> None:
        await self.inner.check()
        self.checked = True

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError(
            EmbeddingFailure.BAD_RESPONSE, "질의 인코더는 문서를 인코딩하지 않는다"
        )

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        if self.paused_until is not None and clock.now() < self.paused_until:
            detail = self.last_failure.value if self.last_failure else ""
            self.failures += 1
            raise EmbeddingError(EmbeddingFailure.PAUSED, detail)
        try:
            async with asyncio.timeout(self.timeout):
                if not self.checked:
                    await self.check()
                vectors = await self.inner.encode_queries(texts)
        except TimeoutError:
            error = EmbeddingError(EmbeddingFailure.TIMEOUT, f"{self.timeout}초")
        except EmbeddingError as exc:
            error = exc
        else:
            self.paused_until = None
            return vectors
        self.paused_until = clock.now() + self.pause
        self.last_failure = error.failure
        self.failures += 1
        raise error


@dataclass
class EmbeddingRun:
    targets: int = 0  # 대상 수
    encoded: int = 0
    skipped: int = 0  # 해시가 같아 건너뛴 수
    blank: int = 0  # 그 종류의 텍스트가 비어 벡터를 만들지 않은 수
    stopped: EmbeddingError | None = None

    @property
    def done(self) -> int:
        return self.encoded + self.skipped + self.blank


@dataclass(frozen=True)
class PendingText:
    """인코딩할 대상 하나. `key`는 저장 행의 대상 열 값이다."""

    target_id: int
    text: str
    hash: str
    key: dict[str, Any] = field(default_factory=dict)


class EmbeddingLayer(Protocol):
    """한 층(공식 서지 또는 기관 도서)의 적재 대상과 저장. 대상은 id 순서로 읽는다."""

    async def count(self, session: AsyncSession) -> int: ...

    async def read(self, session: AsyncSession, after_id: int, limit: int) -> list[PendingText]:
        """id가 after_id보다 큰 대상을 limit개까지, 텍스트와 해시를 만들어 돌려준다."""
        ...

    async def stored_hashes(self, session: AsyncSession, ids: list[int]) -> dict[int, str]:
        """현재 모델·텍스트 버전·종류로 저장된 해시."""
        ...

    async def save(
        self, session: AsyncSession, pending: list[PendingText], vectors: list[list[float]]
    ) -> None: ...


async def upsert_vectors(
    session: AsyncSession,
    model: Any,
    *,
    constraint: str,
    values: dict[str, Any],
    pending: list[PendingText],
    vectors: list[list[float]],
) -> None:
    """벡터 행을 넣고 같은 키면 벡터와 해시를 바꾼다.

    values는 모든 행에 같은 열(모델 이름, 텍스트 버전, 종류)이다.
    """
    statement = insert(model).values(
        [
            {**item.key, **values, "embedding": vector, "content_hash": item.hash}
            for item, vector in zip(pending, vectors, strict=True)
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint=constraint,
            set_={
                "embedding": statement.excluded.embedding,
                "content_hash": statement.excluded.content_hash,
                "updated_at": func.now(),
            },
        )
    )


async def run_layer(
    session: AsyncSession,
    embedder: Embedder,
    layer: EmbeddingLayer,
    *,
    full: bool,
    batch_size: int | None = None,
    on_progress: Callable[[EmbeddingRun], None] | None = None,
) -> EmbeddingRun:
    """대상을 배치로 인코딩해 저장한다.

    full이면 모두 다시 인코딩하고, 아니면 벡터가 없거나 텍스트 해시가 달라진 대상만 인코딩한다.
    텍스트가 빈 대상(소개 없는 책의 `description`)은 벡터를 만들지 않고 `blank`로 센다.
    배치 크기를 주지 않으면 설정 값(`EMBEDDING_BATCH_SIZE`)을 쓴다. 인코더가 실패하면 그 자리에서
    멈추고 `stopped`에 이유를 담는다. 끝난 배치는 저장돼 있다.
    """
    size = batch_size or get_settings().embedding_batch_size
    run = EmbeddingRun(targets=await layer.count(session))
    last_id = 0
    while True:
        items = await layer.read(session, last_id, size)
        if not items:
            break
        last_id = items[-1].target_id
        blank = sum(1 for item in items if not item.text)
        items = [item for item in items if item.text]  # 빈 텍스트는 인코딩하지 않는다
        run.blank += blank
        stored = {} if full else await layer.stored_hashes(session, [i.target_id for i in items])
        pending = [item for item in items if stored.get(item.target_id) != item.hash]
        await session.commit()  # 인코딩 호출 동안 트랜잭션을 잡지 않는다

        if pending:
            try:
                vectors = await embedder.encode_documents([item.text for item in pending])
                if len(vectors) != len(pending):
                    raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "벡터 수가 입력과 다릅니다")
            except EmbeddingError as exc:
                run.stopped = exc
                return run
            await layer.save(session, pending, vectors)
            await session.commit()
        run.encoded += len(pending)
        run.skipped += len(items) - len(pending)
        if on_progress is not None:
            on_progress(run)
    return run
