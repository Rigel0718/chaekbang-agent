"""strip edition markers from lookup keys

Revision ID: e2b8f4a6c1d3
Revises: d7a3c1e9b5f2
Create Date: 2026-11-11 01:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2b8f4a6c1d3"
down_revision: str | Sequence[str] | None = "d7a3c1e9b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# app/core/text.py의 jamo_starts와 같은 규칙. tests/core/test_text.py가 DB에서 비교한다.
# 1) clean_spaces 2) 판본·묶음 표기 지우기(strip_edition, 지워서 비면 원래 서명) 3) 소문자, 자모
# 4) 낱말마다 끝까지 이은 키
KO_JAMO_STARTS = """
CREATE OR REPLACE FUNCTION ko_jamo_starts(value text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
SELECT coalesce(array_agg(array_to_string(x.words[i:], '') ORDER BY i), ARRAY[]::text[])
FROM (SELECT btrim(regexp_replace(
        regexp_replace(value, '[​﻿]', '', 'g'), '[\\s ]+', ' ', 'g'
    ), ' ') AS cleaned) AS c,
LATERAL (SELECT regexp_replace(
    regexp_replace(c.cleaned, '\\[[^]]*\\]', ' ', 'g'), '\\([^)]*\\)', ' ', 'g'
) AS t) AS closed,
LATERAL (SELECT regexp_replace(
    regexp_replace(closed.t, '[(\\[].*$', ' '), ' \\+ .*$', ' '
) AS t) AS rest,
LATERAL (SELECT coalesce(
    nullif(btrim(regexp_replace(rest.t, ' +', ' ', 'g'), ' '), ''), c.cleaned
) AS title) AS e,
LATERAL (SELECT string_to_array(nullif(ko_jamo(lower(e.title)), ''), ' ') AS words) AS x,
generate_subscripts(x.words, 1) AS i
$$
"""

# 이전 리비전(d7a3c1e9b5f2)의 규칙. 되돌릴 때 쓴다.
PREVIOUS_KO_JAMO_STARTS = """
CREATE OR REPLACE FUNCTION ko_jamo_starts(value text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
SELECT coalesce(array_agg(array_to_string(x.words[i:], '') ORDER BY i), ARRAY[]::text[])
FROM (SELECT btrim(regexp_replace(
        regexp_replace(value, '[​﻿]', '', 'g'), '[\\s ]+', ' ', 'g'
    ), ' ') AS cleaned) AS c,
LATERAL (SELECT string_to_array(nullif(ko_jamo(lower(c.cleaned)), ''), ' ') AS words) AS x,
generate_subscripts(x.words, 1) AS i
$$
"""


def _recompute() -> None:
    """생성 열은 행이 바뀔 때만 다시 계산된다. 함수를 바꾼 뒤 저장된 찾기 키를 다시 만든다."""
    op.execute("UPDATE books SET title = title")
    op.execute("UPDATE library_books SET title = title")


def upgrade() -> None:
    op.execute(KO_JAMO_STARTS)
    _recompute()


def downgrade() -> None:
    op.execute(PREVIOUS_KO_JAMO_STARTS)
    _recompute()
