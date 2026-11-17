"""[catalog/topic-recommendation] 서비스 중 질의 인코더: 시간 제한, 쉬기, 모델 확인 한 번.

임베딩 서버 없이 가짜 인코더로 돈다. 키워드 순위로 내려가기는 `tests/library/test_topic_search.py`.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from app.central.embedding import EmbeddingError, EmbeddingFailure, GuardedEmbedder
from app.core import clock


class Inner:
    """호출 수를 센다. `failure`가 있으면 그 종류로, `delay`가 있으면 그만큼 기다린다."""

    name = "fake-model"
    dim = 3

    def __init__(self) -> None:
        self.checks = 0
        self.queries = 0
        self.failure: EmbeddingFailure | None = None
        self.check_failure: EmbeddingFailure | None = None
        self.delay = 0.0

    async def check(self) -> None:
        self.checks += 1
        if self.check_failure is not None:
            raise EmbeddingError(self.check_failure, "서버 모델 다른-모델")

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("문서를 인코딩하면 안 된다")

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.queries += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure is not None:
            raise EmbeddingError(self.failure, "연결 거부")
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch):
    current = [datetime(2026, 11, 17, 10, 0, tzinfo=UTC)]
    monkeypatch.setattr(clock, "now", lambda: current[0])

    def advance(seconds: float) -> None:
        current[0] += timedelta(seconds=seconds)

    return advance


def _guarded(inner: Inner, timeout: float = 2.0) -> GuardedEmbedder:
    return GuardedEmbedder(inner, timeout=timeout, pause=30)


async def test_paused_after_failure(now) -> None:
    """[catalog/topic-recommendation] 질의 인코딩 쉬기 / 쉬는 동안"""
    inner = Inner()
    inner.failure = EmbeddingFailure.UNREACHABLE
    guarded = _guarded(inner)
    with pytest.raises(EmbeddingError) as first:
        await guarded.encode_queries(["공룡"])
    assert first.value.failure is EmbeddingFailure.UNREACHABLE
    now(10)
    with pytest.raises(EmbeddingError) as second:
        await guarded.encode_queries(["공룡"])
    assert second.value.failure is EmbeddingFailure.PAUSED
    assert second.value.detail == "unreachable"
    assert inner.queries == 1 and guarded.failures == 2


async def test_pause_ends(now) -> None:
    """[catalog/topic-recommendation] 질의 인코딩 쉬기 / 쉬기가 끝남"""
    inner = Inner()
    inner.failure = EmbeddingFailure.UNREACHABLE
    guarded = _guarded(inner)
    with pytest.raises(EmbeddingError):
        await guarded.encode_queries(["공룡"])
    now(30)
    inner.failure = None
    assert await guarded.encode_queries(["공룡"]) == [[1.0, 0.0, 0.0]]
    assert inner.queries == 2


async def test_model_checked_once(now) -> None:
    """[catalog/topic-recommendation] 질의 인코딩 쉬기 / 모델 확인 한 번"""
    inner = Inner()
    guarded = _guarded(inner)
    for _ in range(3):
        await guarded.encode_queries(["공룡"])
    assert inner.checks == 1 and inner.queries == 3


async def test_other_model_pauses(now) -> None:
    """[catalog/topic-recommendation] 키워드 순위로 내려가기 / 다른 모델 (인코더 쪽)"""
    inner = Inner()
    inner.check_failure = EmbeddingFailure.MODEL_MISMATCH
    guarded = _guarded(inner)
    with pytest.raises(EmbeddingError) as caught:
        await guarded.encode_queries(["공룡"])
    assert caught.value.failure is EmbeddingFailure.MODEL_MISMATCH
    assert inner.queries == 0
    now(31)
    inner.check_failure = None
    await guarded.encode_queries(["공룡"])
    assert inner.checks == 2 and inner.queries == 1


async def test_timeout(now) -> None:
    """[catalog/topic-recommendation] 키워드 순위로 내려가기 / 시간 제한 (인코더 쪽)"""
    inner = Inner()
    inner.delay = 0.2
    guarded = _guarded(inner, timeout=0.05)
    with pytest.raises(EmbeddingError) as caught:
        await guarded.encode_queries(["비밀 낱말"])
    assert caught.value.failure is EmbeddingFailure.TIMEOUT
    assert "비밀" not in str(caught.value)
    assert guarded.paused_until is not None


async def test_documents_refused() -> None:
    """[catalog/topic-recommendation] 질의 인코딩 쉬기 (문서는 인코딩하지 않음)"""
    with pytest.raises(EmbeddingError):
        await _guarded(Inner()).encode_documents(["문서"])
