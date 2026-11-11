"""add catalog lookup: jamo keys, fuzzystrmatch, chat message note

Revision ID: d7a3c1e9b5f2
Revises: c4e2a7d9f1b3
Create Date: 2026-11-10 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7a3c1e9b5f2"
down_revision: str | Sequence[str] | None = "c4e2a7d9f1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# app/core/text.py의 decompose_jamo와 같은 규칙. 표를 바꾸면 새 리비전으로 함수를 다시 만든다.
# tests/core/test_text.py가 두 쪽의 결과를 DB에서 비교한다.
KO_JAMO = """
CREATE FUNCTION ko_jamo(value text) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    cho text[] := ARRAY[
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ',
        'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ];
    jung text[] := ARRAY[
        'ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅗㅏ', 'ㅗㅐ', 'ㅗㅣ', 'ㅛ',
        'ㅜ', 'ㅜㅓ', 'ㅜㅔ', 'ㅜㅣ', 'ㅠ', 'ㅡ', 'ㅡㅣ', 'ㅣ'
    ];
    jong text[] := ARRAY[
        '', 'ㄱ', 'ㄲ', 'ㄱㅅ', 'ㄴ', 'ㄴㅈ', 'ㄴㅎ', 'ㄷ', 'ㄹ', 'ㄹㄱ', 'ㄹㅁ', 'ㄹㅂ',
        'ㄹㅅ', 'ㄹㅌ', 'ㄹㅍ', 'ㄹㅎ', 'ㅁ', 'ㅂ', 'ㅂㅅ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ',
        'ㅌ', 'ㅍ', 'ㅎ'
    ];
    parts text[] := ARRAY[]::text[];
    ch text;
    code int;
BEGIN
    FOREACH ch IN ARRAY regexp_split_to_array(value, '') LOOP
        code := ascii(ch) - 44032;
        IF code >= 0 AND code < 11172 THEN
            parts := parts
                || (cho[code / 588 + 1] || jung[code % 588 / 28 + 1] || jong[code % 28 + 1]);
        ELSE
            parts := parts || (CASE ch
                WHEN 'ㄳ' THEN 'ㄱㅅ'
                WHEN 'ㄵ' THEN 'ㄴㅈ'
                WHEN 'ㄶ' THEN 'ㄴㅎ'
                WHEN 'ㄺ' THEN 'ㄹㄱ'
                WHEN 'ㄻ' THEN 'ㄹㅁ'
                WHEN 'ㄼ' THEN 'ㄹㅂ'
                WHEN 'ㄽ' THEN 'ㄹㅅ'
                WHEN 'ㄾ' THEN 'ㄹㅌ'
                WHEN 'ㄿ' THEN 'ㄹㅍ'
                WHEN 'ㅀ' THEN 'ㄹㅎ'
                WHEN 'ㅄ' THEN 'ㅂㅅ'
                WHEN 'ㅘ' THEN 'ㅗㅏ'
                WHEN 'ㅙ' THEN 'ㅗㅐ'
                WHEN 'ㅚ' THEN 'ㅗㅣ'
                WHEN 'ㅝ' THEN 'ㅜㅓ'
                WHEN 'ㅞ' THEN 'ㅜㅔ'
                WHEN 'ㅟ' THEN 'ㅜㅣ'
                WHEN 'ㅢ' THEN 'ㅡㅣ'
                ELSE ch END);
        END IF;
    END LOOP;
    RETURN array_to_string(parts, '');
END
$$
"""

# app/core/text.py의 jamo_starts와 같은 규칙: clean_spaces, 소문자, 자모, 낱말마다 끝까지 이은 키.
KO_JAMO_STARTS = """
CREATE FUNCTION ko_jamo_starts(value text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(array_to_string(x.words[i:], '') ORDER BY i), ARRAY[]::text[])
    FROM (
        SELECT string_to_array(nullif(ko_jamo(lower(btrim(regexp_replace(
            regexp_replace(value, '[​﻿]', '', 'g'), '[\\s ]+', ' ', 'g'
        ), ' '))), ''), ' ') AS words
    ) AS x, generate_subscripts(x.words, 1) AS i
$$
"""

KEY_COLUMNS = {"title_jamo_starts": "title", "author_jamo_starts": "author"}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")
    op.execute(KO_JAMO)
    op.execute(KO_JAMO_STARTS)
    for table in ("books", "library_books"):
        for column, source in KEY_COLUMNS.items():
            op.add_column(
                table,
                sa.Column(
                    column,
                    postgresql.ARRAY(sa.Text()),
                    sa.Computed(f"ko_jamo_starts({source})", persisted=True),
                    nullable=True,
                ),
            )
    op.add_column("chat_messages", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "note")
    for table in ("books", "library_books"):
        for column in KEY_COLUMNS:
            op.drop_column(table, column)
    op.execute("DROP FUNCTION IF EXISTS ko_jamo_starts(text)")
    op.execute("DROP FUNCTION IF EXISTS ko_jamo(text)")
    op.execute("DROP EXTENSION IF EXISTS fuzzystrmatch")
