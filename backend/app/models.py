from __future__ import annotations

import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, LocalBase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReminderStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class ReminderKind(str, enum.Enum):
    """Di che natura è il promemoria.

    Non cambia il funzionamento degli avvisi — un appuntamento si preavvisa
    come una scadenza — ma cambia il modo di leggerlo: "scade tra tre giorni"
    ha senso per una scadenza, non per una riunione.
    """

    DEADLINE = "deadline"
    APPOINTMENT = "appointment"
    OTHER = "other"


class Recurrence(str, enum.Enum):
    NONE = "none"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    YEARLY = "yearly"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_reminder_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    #: Ora di inizio, facoltativa: un appuntamento ce l'ha, una scadenza di
    #: solito no. Senza orario il promemoria vale per l'intera giornata.
    start_time: Mapped[time | None] = mapped_column(Time, default=None)
    kind: Mapped[ReminderKind] = mapped_column(
        Enum(ReminderKind, native_enum=False, length=16), default=ReminderKind.DEADLINE, index=True
    )
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus, native_enum=False, length=16), default=ReminderStatus.OPEN, index=True
    )
    recurrence: Mapped[Recurrence] = mapped_column(
        Enum(Recurrence, native_enum=False, length=16), default=Recurrence.NONE
    )
    amount: Mapped[float | None] = mapped_column(Float, default=None)
    owner: Mapped[str | None] = mapped_column(String(120), default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)

    # Preavvisi specifici del promemoria; se None si usano quelli globali.
    alert_offsets: Mapped[list[int] | None] = mapped_column(JSON, default=None)
    notify_emails: Mapped[list[str] | None] = mapped_column(JSON, default=None)

    # Tracciabilità della fonte: "manual", "csv", "excel", "erp", ...
    source: Mapped[str] = mapped_column(String(60), default="manual", index=True)
    external_id: Mapped[str | None] = mapped_column(String(190), default=None)
    extra: Mapped[dict | None] = mapped_column(JSON, default=None)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def days_left(self) -> int:
        return (self.due_date - date.today()).days

    @property
    def is_overdue(self) -> bool:
        return self.status == ReminderStatus.OPEN and self.due_date < date.today()


class Notification(LocalBase):
    """Un avviso generato per un promemoria a un dato preavviso.

    Vive nel database **locale**: ogni postazione mostra e traccia i propri
    avvisi. Per questo `reminder_id` è un semplice riferimento numerico al
    promemoria nel database condiviso, non una foreign key.

    `dedupe_key` garantisce che lo stesso avviso non venga mostrato due volte.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(Integer, index=True)

    dedupe_key: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    offset_days: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")

    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False, length=16),
        default=NotificationStatus.PENDING,
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Quando il toast di Windows è stato effettivamente mostrato su questa
    #: postazione: evita di ripresentarlo a ogni avvio dell'applicazione.
    displayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    channel_results: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushSubscription(LocalBase):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    label: Mapped[str | None] = mapped_column(String(190), default=None)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Impostazioni runtime modificabili dall'interfaccia (chiave -> valore JSON)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
