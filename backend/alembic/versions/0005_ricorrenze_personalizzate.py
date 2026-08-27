"""Cadenze in più, e la ricorrenza personalizzata

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-27

Le cadenze erano quattro: mensile, trimestrale, semestrale, annuale. Fuori da
quelle non c'era modo di dire «quadrimestrale» — l'IVA di certi regimi — né
«biennale» o «quinquennale», come vogliono revisioni e certificazioni.

Le voci con un nome diventano dodici e stanno tutte nell'enum, che è testo:
nessuna colonna da toccare per loro. Le due colonne nuove servono alla voce
«ogni…», che copre tutto il resto — «ogni 45 giorni», «ogni 18 mesi» — e resta
vuota per tutte le altre.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


# ------------------------------------------------------------------ condiviso


def upgrade_shared() -> None:
    op.add_column("reminders", sa.Column("recurrence_every", sa.Integer(), nullable=True))
    op.add_column("reminders", sa.Column("recurrence_unit", sa.String(length=8), nullable=True))


def downgrade_shared() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("recurrence_unit")
        batch.drop_column("recurrence_every")


# --------------------------------------------------------------------- locale


def upgrade_local() -> None:
    """Gli avvisi non sanno nulla di cadenze: guardano una data e basta."""


def downgrade_local() -> None:
    pass
