"""Da scadenzario a promemoria

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13

L'applicazione non gestisce più solo scadenze: un appuntamento o una nota in
agenda sono la stessa cosa vista da un'altra angolazione. La tabella cambia
nome, guadagna il tipo (`kind`) e l'ora di inizio facoltativa.

Le tabelle vengono **rinominate**, non ricreate: le installazioni esistenti si
portano dietro tutti i dati. Il prezzo è che una postazione ferma alla 1.0.x
non riconosce più lo schema, quindi l'aggiornamento va fatto ovunque.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_KIND = sa.Enum(
    "DEADLINE", "APPOINTMENT", "OTHER", name="reminderkind", native_enum=False, length=16
)

#: Indici da riportare sul nuovo nome della tabella: rinominare la tabella non
#: rinomina gli indici, e `ix_deadlines_*` su `reminders` sarebbe solo confusione.
_RENAMED_INDEXES = [
    ("ix_deadlines_title", "ix_reminders_title", "title"),
    ("ix_deadlines_due_date", "ix_reminders_due_date", "due_date"),
    ("ix_deadlines_status", "ix_reminders_status", "status"),
    ("ix_deadlines_source", "ix_reminders_source", "source"),
]


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


# ------------------------------------------------------------------ condiviso


def upgrade_shared() -> None:
    op.rename_table("deadlines", "reminders")

    for old, new, column in _RENAMED_INDEXES:
        op.drop_index(old, table_name="reminders")
        op.create_index(new, "reminders", [column])

    _rename_constraint("uq_deadline_source_external", "uq_reminder_source_external")

    # Il default lato database resta: permette di dichiarare la colonna NOT NULL
    # sulle righe già esistenti senza ricostruire la tabella, e non dà fastidio
    # perché il valore coincide con quello del modello.
    op.add_column(
        "reminders",
        sa.Column("kind", _KIND, nullable=False, server_default="DEADLINE"),
    )
    op.add_column("reminders", sa.Column("start_time", sa.Time(), nullable=True))
    op.create_index("ix_reminders_kind", "reminders", ["kind"])


def downgrade_shared() -> None:
    op.drop_index("ix_reminders_kind", table_name="reminders")
    op.drop_column("reminders", "start_time")
    op.drop_column("reminders", "kind")

    _rename_constraint("uq_reminder_source_external", "uq_deadline_source_external")

    for old, new, column in _RENAMED_INDEXES:
        op.drop_index(new, table_name="reminders")
        op.create_index(old, "reminders", [column])

    op.rename_table("reminders", "deadlines")


def _rename_constraint(old: str, new: str) -> None:
    """Rinomina il vincolo di unicità, dove il database sa farlo.

    SQLite tiene il nome dentro il DDL della tabella e non ha modo di
    cambiarlo se non ricostruendola: lì il vecchio nome resta, senza
    conseguenze pratiche perché a runtime nessuno lo usa.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'ALTER TABLE reminders RENAME CONSTRAINT "{old}" TO "{new}"')


# --------------------------------------------------------------------- locale


def upgrade_local() -> None:
    op.drop_index("ix_notifications_deadline_id", table_name="notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.alter_column(
            "deadline_id",
            new_column_name="reminder_id",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    op.create_index("ix_notifications_reminder_id", "notifications", ["reminder_id"])


def downgrade_local() -> None:
    op.drop_index("ix_notifications_reminder_id", table_name="notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.alter_column(
            "reminder_id",
            new_column_name="deadline_id",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    op.create_index("ix_notifications_deadline_id", "notifications", ["deadline_id"])
