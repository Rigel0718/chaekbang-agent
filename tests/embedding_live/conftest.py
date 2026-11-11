"""실제 임베딩 서버(TEI)를 쓰는 테스트. 서버에 닿지 않으면 이 폴더의 테스트를 모두 건너뛴다.

서버: docker compose --profile embedding up -d embedder
CPU에서 느리므로 입력을 작게 둔다. 표본 87권 전체는 `scripts/embedding_search.py --sample`로 본다.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.central.external.tei import TeiEmbedder
from app.core.config import get_settings


def _server_is_up() -> bool:
    try:
        return httpx.get(f"{get_settings().embedding_base_url}/health", timeout=2).is_success
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    mine = [item for item in items if Path(item.fspath).is_relative_to(here)]
    if not mine:
        return
    skip = None
    if not _server_is_up():
        skip = pytest.mark.skip(
            reason=f"임베딩 서버가 없습니다: {get_settings().embedding_base_url}"
        )
    for item in mine:
        item.add_marker(pytest.mark.tei)
        if skip is not None:
            item.add_marker(skip)


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
    ) as client:
        yield client


@pytest.fixture
def embedder(http: httpx.AsyncClient) -> TeiEmbedder:
    return TeiEmbedder(http, get_settings())
