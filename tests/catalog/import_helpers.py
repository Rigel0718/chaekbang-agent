"""장서 가져오기 테스트 도우미."""

import csv
import io

from httpx import AsyncClient


def csv_bytes(*rows: list, encoding: str = "utf-8") -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode(encoding)


async def upload(client: AsyncClient, *rows: list, column_mapping: str | None = None):
    data = {"column_mapping": column_mapping} if column_mapping else None
    files = {"file": ("export.csv", csv_bytes(*rows), "text/csv")}
    return await client.post("/holding-imports", files=files, data=data)


async def import_file(client: AsyncClient, *rows: list, confirm_withdraw: bool = False) -> dict:
    """올리고 바로 적용한다. 적용한 기록을 돌려준다."""
    res = await upload(client, *rows)
    assert res.status_code == 201, res.text
    url = f"/holding-imports/{res.json()['id']}/apply"
    params = {"confirm_withdraw": "true"} if confirm_withdraw else None
    applied = await client.post(url, params=params)
    assert applied.status_code == 200, applied.text
    return applied.json()
