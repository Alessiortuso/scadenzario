"""Schema iniziale

Revision ID: 0001
Revises:
Create Date: 2026-08-12

Fotografia dello schema alla versione 1.0.0. Le installazioni già esistenti non
la eseguono: `app.migrations` le marca direttamente a questa revisione, perché
le tabelle ci sono già.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_STATUS = sa.Enum(
    "OPEN", "DONE", "CANCELLED", name="deadlinestatus", native_enum=False, length=16
)
_PRIORITY = sa.Enum(
    "LOW", "NORMAL", "HIGH", "CRITICAL", name="priority", native_enum=False, length=16
)
_RECURRENCE = sa.Enum(
    "NONE",
    "MONTHLY",
    "QUARTERLY",
    "SEMIANNUAL",
    "YEARLY",
    name="recurrence",
    native_enum=False,
    length=16,
)
_NOTIFICATION_STATUS = sa.Enum(
    "PENDING",
    "SENT",
    "FAILED",
    "CANCELLED",
    name="notificationstatus",
    native_enum=False,
    length=16,
)


def upgrade(target: str) -> None:
    globals()[f"upgrade_{target}"]()


def downgrade(target: str) -> None:
    globals()[f"downgrade_{target}"]()


# ------------------------------------------------------------------ condiviso


def upgrade_shared() -> None:
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

    op.create_table(
        "deadlines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", _STATUS, nullable=False),
        sa.Column("priority", _PRIORITY, nullable=False),
        sa.Column("recurrence", _RECURRENCE, nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("alert_offsets", sa.JSON(), nullable=True),
        sa.Column("notify_emails", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("external_id", sa.String(length=190), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_deadline_source_external"),
    )
    op.create_index("ix_deadlines_title", "deadlines", ["title"])
    op.create_index("ix_deadlines_due_date", "deadlines", ["due_date"])
    op.create_index("ix_deadlines_status", "deadlines", ["status"])
    op.create_index("ix_deadlines_source", "deadlines", ["source"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade_shared() -> None:
    op.drop_table("settings")
    op.drop_index("ix_deadlines_source", table_name="deadlines")
    op.drop_index("ix_deadlines_status", table_name="deadlines")
    op.drop_index("ix_deadlines_due_date", table_name="deadlines")
    op.drop_index("ix_deadlines_title", table_name="deadlines")
    op.drop_table("deadlines")
    op.drop_table("categories")


# --------------------------------------------------------------------- locale


def upgrade_local() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deadline_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=190), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _NOTIFICATION_STATUS, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("displayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_results", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_deadline_id", "notifications", ["deadline_id"])
    op.create_index("ix_notifications_dedupe_key", "notifications", ["dedupe_key"], unique=True)
    op.create_index("ix_notifications_scheduled_for", "notifications", ["scheduled_for"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=190), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )


def downgrade_local() -> None:
    op.drop_table("push_subscriptions")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_scheduled_for", table_name="notifications")
    op.drop_index("ix_notifications_dedupe_key", table_name="notifications")
    op.drop_index("ix_notifications_deadline_id", table_name="notifications")
    op.drop_table("notifications")
