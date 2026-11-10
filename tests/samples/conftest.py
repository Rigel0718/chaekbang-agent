"""표본 테스트 공통. 표본 파일이 없으면 이 폴더의 테스트를 모두 건너뛴다.

표본은 저장소에 없다(YES24 이용 조건). 테스트 DB 트랜잭션 안에서 적재하고 되돌린다.
`LIBRARIAN_SAMPLE_FILE`로 경로를 바꿀 수 있다. 없는 경로를 주면 건너뛰는지 확인할 수 있다.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from evals.librarian.catalog import DATA_FILE, Sample, SampleCatalog, load_catalog, load_sample

SAMPLE_FILE = Path(os.environ.get("LIBRARIAN_SAMPLE_FILE", DATA_FILE))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    skip = pytest.mark.skip(reason=f"표본이 없습니다: {SAMPLE_FILE}")
    for item in items:
        if Path(item.fspath).is_relative_to(here):
            item.add_marker(pytest.mark.sample)
            if not SAMPLE_FILE.exists():
                item.add_marker(skip)


@pytest.fixture(scope="session")
def sample() -> Sample:
    return load_sample(SAMPLE_FILE)


@pytest.fixture
async def catalog(session: AsyncSession, sample: Sample) -> SampleCatalog:
    return await load_catalog(session, sample)
