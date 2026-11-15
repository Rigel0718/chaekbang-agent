"""add book contributors: book_contributors, library_books.author_keys, NFC·전각 찾기 키

Revision ID: 49392728f35a
Revises: 84d5d8bd4caf
Create Date: 2026-11-13 12:26:30.044170

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "49392728f35a"
down_revision: str | Sequence[str] | None = "84d5d8bd4caf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 전각 영문·숫자·기호(U+FF01~U+FF5E)와 같은 자리의 반각. app/core/text.py의 표와 같다.
# 마이그레이션은 그때의 값으로 고정한다(앱 코드를 import하지 않는다).
FULLWIDTH = "".join(chr(code) for code in range(0xFF01, 0xFF5F))
HALFWIDTH = "".join(chr(code) for code in range(0x21, 0x7F))


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# app/core/text.py의 jamo_starts와 같은 규칙. 이전 리비전(e2b8f4a6c1d3)에 두 가지를 더했다.
# 1) 정리 단계에서 NFC(clean_spaces) 2) 소문자 앞에서 전각 → 반각(jamo_spaced)
KO_JAMO_STARTS = (
    """
CREATE OR REPLACE FUNCTION ko_jamo_starts(value text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
SELECT coalesce(array_agg(array_to_string(x.words[i:], '') ORDER BY i), ARRAY[]::text[])
FROM (SELECT btrim(regexp_replace(
        regexp_replace(normalize(value, NFC), '[​﻿]', '', 'g'), '[\\s ]+', ' ', 'g'
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
LATERAL (SELECT string_to_array(
    nullif(ko_jamo(lower(translate(e.title, """
    + _literal(FULLWIDTH)
    + ", "
    + _literal(HALFWIDTH)
    + """))), ''), ' '
) AS words) AS x,
generate_subscripts(x.words, 1) AS i
$$
"""
)

# 이전 리비전(e2b8f4a6c1d3)의 규칙. 되돌릴 때 쓴다.
PREVIOUS_KO_JAMO_STARTS = """
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


def _recompute() -> None:
    """생성 열은 행이 바뀔 때만 다시 계산된다. 함수를 바꾼 뒤 저장된 찾기 키를 다시 만든다."""
    op.execute("UPDATE books SET title = title")
    op.execute("UPDATE library_books SET title = title")


def upgrade() -> None:
    op.create_table(
        "book_contributors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "author",
                "illustrator",
                "translator",
                "editor",
                "supervisor",
                "original",
                "other",
                name="contributor_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("role_text", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_book_contributors_name_not_empty")),
        sa.CheckConstraint("name_key <> ''", name=op.f("ck_book_contributors_name_key_not_empty")),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_book_contributors_book_id_books"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_contributors")),
        sa.UniqueConstraint("book_id", "position", name="uq_book_contributors_book_id_position"),
    )
    op.create_index(
        op.f("ix_book_contributors_name_key"), "book_contributors", ["name_key"], unique=False
    )
    # 기존 행은 빈 목록으로 두고 기본값을 뗀다. 값은 scripts/rebuild_contributors.py가 채운다.
    op.add_column(
        "library_books",
        sa.Column(
            "author_keys",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.alter_column("library_books", "author_keys", server_default=None)
    op.execute(KO_JAMO_STARTS)
    _recompute()


def downgrade() -> None:
    op.execute(PREVIOUS_KO_JAMO_STARTS)
    _recompute()
    op.drop_column("library_books", "author_keys")
    op.drop_index(op.f("ix_book_contributors_name_key"), table_name="book_contributors")
    op.drop_table("book_contributors")
