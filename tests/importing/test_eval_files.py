"""가져오기 평가가 돌아가고, 가상 파일에서 기대한 수치가 나오는지 확인한다."""

import pytest

from evals.holdings_import.files import generate_files
from evals.holdings_import.metrics import score_file


@pytest.mark.parametrize("file", generate_files(), ids=lambda f: f.name)
def test_eval_file(file) -> None:
    score = score_file(file)
    assert score.rows == len(file.truth)
    assert score.skipped == 0
    assert score.children_precision in (None, 1.0)
    if file.has_children_signal:
        assert score.isbn_recognition == 1.0
        assert score.invalid_flagged == 1.0
        assert score.children_recall == 1.0
    else:
        assert score.children_recall == 0.0  # 근거가 없으면 일반 도서로 둔다


def test_generation_is_deterministic() -> None:
    assert [f.truth for f in generate_files(1)] == [f.truth for f in generate_files(1)]
