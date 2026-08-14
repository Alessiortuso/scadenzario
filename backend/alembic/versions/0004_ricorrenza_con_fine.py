"""Ricorrenza con una fine, e occorrenze legate fra loro

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-14

Finora una ricorrenza non finiva mai: alla chiusura di un'occorrenza ne
nasceva la successiva, all'infinito. Va bene per un adempimento perpetuo,
non per una rateizzazione in dodici rate di importo diverso — che è il caso
in cui serve sapere in anticipo quanto si paga a marzo.

Con `recurrence_until` le occorrenze vengono create tutte al salvataggio,
ognuna con il proprio importo, e `series_id` le tiene insieme. Le ricorrenze
senza fine continuano a comportarsi come prima: le colonne restano vuote.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


# ------------------------------------------------------------------ condiviso


def upgrade_shared() -> None:
    op.add_column("reminders", sa.Column("recurrence_until", sa.Date(), nullable=True))
    op.add_column("reminders", sa.Column("series_id", sa.String(length=36), nullable=True))
    op.create_index("ix_reminders_series_id", "reminders", ["series_id"])


def downgrade_shared() -> None:
    op.drop_index("ix_reminders_series_id", table_name="reminders")
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("series_id")
        batch.drop_column("recurrence_until")


# --------------------------------------------------------------------- locale


def upgrade_local() -> None:
    """Gli avvisi non sanno nulla di serie: puntano alle singole occorrenze."""


def downgrade_local() -> None:
    pass
