"""[agent/admin] 결과 사건의 모양(`schemas/admin_results.py`)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.library.schemas.admin_results import MAX_ROWS, DraftLink, ResultPayload, TableResult


def _table(**values) -> TableResult:
    base = {
        "title": "묶음별 장서",
        "caption": None,
        "columns": ["분야", "사본"],
        "rows": [["문학", 3], ["분류 없음", None]],
        "bar_column": 1,
        "total": None,
        "truncated": False,
    }
    return TableResult(**{**base, **values})


def test_table_keys() -> None:
    """[agent/admin] 결과 사건의 모양 / 표 모양"""
    data = _table().model_dump(mode="json")
    assert set(data) == {
        "kind",
        "title",
        "caption",
        "columns",
        "rows",
        "bar_column",
        "total",
        "truncated",
    }
    assert data["kind"] == "table"
    assert all(len(row) == len(data["columns"]) for row in data["rows"])


def test_table_rejects_bad_shape() -> None:
    """[agent/admin] 결과 사건의 모양 / 표 모양 (칸 수, 막대 열, 50줄)"""
    with pytest.raises(ValidationError):
        _table(rows=[["문학"]])
    with pytest.raises(ValidationError):
        _table(bar_column=2)
    with pytest.raises(ValidationError):
        _table(rows=[["책", 1]] * (MAX_ROWS + 1))
    assert len(_table(rows=[["책", 1]] * MAX_ROWS).rows) == MAX_ROWS


def test_draft_keys() -> None:
    """[agent/admin] 결과 사건의 모양 / 초안 모양"""
    data = DraftLink(draft="curation", id=12).model_dump(mode="json")
    assert data == {"kind": "draft", "draft": "curation", "id": 12}
    with pytest.raises(ValidationError):
        DraftLink(draft="loan", id=1)


def test_payload_discriminated_by_kind() -> None:
    """[agent/admin] 결과 사건의 모양 / 두 모양을 kind로 나눔"""
    adapter = TypeAdapter(ResultPayload)
    assert isinstance(
        adapter.validate_python({"kind": "draft", "draft": "template", "id": 3}), DraftLink
    )
    assert isinstance(adapter.validate_python(_table().model_dump()), TableResult)
