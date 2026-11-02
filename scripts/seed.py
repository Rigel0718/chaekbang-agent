"""로컬 개발용 더미 데이터를 넣는다: uv run python scripts/seed.py"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.seed.runner import run  # noqa: E402


def main() -> int:
    return asyncio.run(run(get_settings().database_url))


if __name__ == "__main__":
    sys.exit(main())
