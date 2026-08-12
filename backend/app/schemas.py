from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import DeadlineStatus, NotificationStatus, Priority, Recurrence


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _as_utc(value: datetime | None) -> datetime | None:
    """Riattacca il fuso ai timestamp che tornano nudi.

    SQLite non memorizza l'offset: i valori scritti in UTC si rileggono senza
    fuso. Serializzati così, il browser li interpreta come ora locale e mostra
    un orario sbagliato (due ore indietro d'estate). Il database condiviso in
    PostgreSQL non ne soffre, ma quello locale delle notifiche sì.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# --------------------------------------------------------------------------- categorie
class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str = "#6366f1"
    alert_offsets: list[int] | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = None
    alert_offsets: list[int] | None = None


class CategoryRead(ORMModel, CategoryBase):
    id: int


# --------------------------------------------------------------------------- scadenze
class DeadlineBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: date
    priority: Priority = Priority.NORMAL
    recurrence: Recurrence = Recurrence.NONE
    amount: float | None = None
    owner: str | None = None
    reference: str | None = None
    category_id: int | None = None
    alert_offsets: list[int] | None = None
    notify_emails: list[EmailStr] | None = None

    @field_validator("alert_offsets")
    @classmethod
    def _clean_offsets(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        return sorted({int(x) for x in v if int(x) >= 0}, reverse=True)


class DeadlineCreate(DeadlineBase):
    source: str = "manual"
    external_id: str | None = None
    extra: dict | None = None


class DeadlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_date: date | None = None
    status: DeadlineStatus | None = None
    priority: Priority | None = None
    recurrence: Recurrence | None = None
    amount: float | None = None
    owner: str | None = None
    reference: str | None = None
    category_id: int | None = None
    alert_offsets: list[int] | None = None
    notify_emails: list[EmailStr] | None = None
    extra: dict | None = None


class DeadlineRead(ORMModel, DeadlineBase):
    id: int
    status: DeadlineStatus
    source: str
    external_id: str | None
    extra: dict | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    category: CategoryRead | None = None
    days_left: int
    is_overdue: bool

    # Serve quando il database condiviso è uno SQLite di sviluppo.
    @field_validator("completed_at", "created_at", "updated_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return _as_utc(v)


class DeadlinePage(BaseModel):
    items: list[DeadlineRead]
    total: int
    page: int
    page_size: int


class DeadlineStats(BaseModel):
    overdue: int
    due_today: int
    due_in_7_days: int
    due_in_30_days: int
    open_total: int
    done_total: int
    amount_open: float
    by_category: list["CategoryStat"]


class CategoryStat(BaseModel):
    category_id: int | None
    name: str
    color: str
    count: int


# --------------------------------------------------------------------------- notifiche
class NotificationRead(ORMModel):
    id: int
    deadline_id: int
    offset_days: int
    title: str
    body: str
    severity: str
    scheduled_for: datetime
    status: NotificationStatus
    sent_at: datetime | None
    read_at: datetime | None
    displayed_at: datetime | None
    channel_results: dict | None

    @field_validator("scheduled_for", "sent_at", "read_at", "displayed_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return _as_utc(v)


class NotificationCounts(BaseModel):
    unread: int
    total: int


# --------------------------------------------------------------------------- push
class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    keys: PushKeys
    label: str | None = None


class PushSubscriptionRead(ORMModel):
    id: int
    endpoint: str
    label: str | None
    active: bool
    created_at: datetime


class PublicKeyRead(BaseModel):
    public_key: str
    enabled: bool


# --------------------------------------------------------------------------- import
class ImportPreviewRow(BaseModel):
    row: int
    data: dict
    errors: list[str] = []


class ImportPreview(BaseModel):
    columns: list[str]
    suggested_mapping: dict[str, str]
    rows: list[ImportPreviewRow]
    total_rows: int


class ImportMapping(BaseModel):
    """Mappa campo-scadenza -> nome colonna del file."""

    title: str
    due_date: str
    description: str | None = None
    amount: str | None = None
    owner: str | None = None
    reference: str | None = None
    category: str | None = None
    external_id: str | None = None
    date_format: str | None = None
    source: str = "import"
    default_alert_offsets: list[int] | None = None


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


# --------------------------------------------------------------------------- impostazioni
class AppSettings(BaseModel):
    channel_inapp: bool = True
    channel_push: bool = True
    channel_email: bool = False
    default_alert_offsets: list[int] = [30, 15, 7, 3, 1, 0]
    overdue_repeat_days: int = 3
    overdue_max_reminders: int = 5
    daily_send_time: str = "08:00"
    notify_emails: list[EmailStr] = []
    quiet_until_next_day: bool = True


class SettingsRead(AppSettings):
    push_configured: bool
    email_configured: bool
    timezone: str


DeadlineStats.model_rebuild()
