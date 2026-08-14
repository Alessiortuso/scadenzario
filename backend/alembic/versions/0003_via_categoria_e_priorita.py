"""Via categoria e priorità

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13

Compilare un promemoria era diventato un lavoro: dieci campi per annotare una
riunione. Categoria e priorità sono i primi a saltare — nessuno dei due era
obbligatorio, ma entrambi occupavano spazio nella schermata e chiedevano una
decisione a ogni inserimento.

**La migrazione cancella dei dati**: le categorie e i preavvisi che si
portavano dietro spariscono dal database condiviso. I promemoria restano tutti,
senza più categoria né priorità. Chi volesse tornare indietro ritrova le
colonne (`downgrade`) ma non il loro contenuto.

I preavvisi continuano a funzionare: quelli scritti sul singolo promemoria
valgono come prima, e in mancanza si usano quelli generali delle impostazioni.
Viene meno solo il livello intermedio, quello per categoria.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_PRIORITY = sa.Enum(
    "LOW", "NORMAL", "HIGH", "CRITICAL", name="priority", native_enum=False, length=16
)


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


# ------------------------------------------------------------------ condiviso


def upgrade_shared() -> None:
    # Prima la colonna che punta alla tabella, poi la tabella: al contrario la
    # chiave esterna terrebbe in piedi `categories` e la DROP fallirebbe.
    #
    # In modalità batch perché su SQLite — il database condiviso di sviluppo —
    # togliere una colonna con una chiave esterna significa ricostruire la
    # tabella. Sui database veri (PostgreSQL) diventa una ALTER normale.
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("category_id")
        batch.drop_column("priority")

    op.drop_table("categories")


def downgrade_shared() -> None:
    """Ripristina la forma dello schema, non il suo contenuto.

    Le categorie assegnate ai promemoria non tornano: erano righe, e le righe
    la upgrade le ha cancellate.
    """
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=False),
        sa.Column("alert_offsets", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    with op.batch_alter_table("reminders") as batch:
        batch.add_column(sa.Column("priority", _PRIORITY, nullable=False, server_default="NORMAL"))
        batch.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_reminders_category_id", "categories", ["category_id"], ["id"], ondelete="SET NULL"
        )


# --------------------------------------------------------------------- locale


def upgrade_local() -> None:
    """Niente da fare: gli avvisi non hanno mai saputo di categorie o priorità."""


def downgrade_local() -> None:
    pass
