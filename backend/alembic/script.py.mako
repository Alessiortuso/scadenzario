"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Ogni database ha le sue funzioni: `shared` (PostgreSQL condiviso) e `local`
(SQLite della postazione). Lasciare vuota quella che non riguarda la modifica.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


def upgrade_shared() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade_shared() -> None:
    ${downgrades if downgrades else "pass"}


def upgrade_local() -> None:
    pass


def downgrade_local() -> None:
    pass
