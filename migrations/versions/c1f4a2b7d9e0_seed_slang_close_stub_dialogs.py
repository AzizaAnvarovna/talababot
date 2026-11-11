"""Jargon lugʻatini toʻldirish va 1-bosqich dialoglarini yopish

Revision ID: c1f4a2b7d9e0
Revises: 7a38d67231a5
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "c1f4a2b7d9e0"
down_revision: str | Sequence[str] | None = "7a38d67231a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLANG = {
    "stipuxa": "stipendiya",
    "stependiya": "stipendiya",
    "stipendya": "stipendiya",
    "dekonat": "dekanat",
    "dekanot": "dekanat",
    "yotoqhona": "yotoqxona",
    "obshaga": "yotoqxona",
    "obshejitiye": "yotoqxona",
    "spravka": "maʻlumotnoma",
    "akadem": "akademik taʻtil",
    "akademka": "akademik taʻtil",
    "perevod": "koʻchirish",
}

slang_terms = sa.table(
    "slang_terms",
    sa.column("term", sa.String),
    sa.column("replacement", sa.String),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    now = datetime.now(UTC)
    op.bulk_insert(
        slang_terms,
        [{"term": t, "replacement": r, "created_at": now} for t, r in SLANG.items()],
    )
    # "stage1-stub" modeli endi yoʻq, ochiq qolgan dialoglar davom eta olmaydi.
    op.get_bind().execute(
        sa.text(
            "UPDATE dialogs SET ended_at = :now, end_reason = 'migration' "
            "WHERE ended_at IS NULL AND model_version = 'stage1-stub'"
        ),
        {"now": now},
    )


def downgrade() -> None:
    op.execute(slang_terms.delete().where(slang_terms.c.term.in_(list(SLANG))))
