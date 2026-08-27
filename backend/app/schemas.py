from __future__ import annotations

from datetime import date, datetime, time, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import (
    MAX_INTERVALLO,
    NotificationStatus,
    Recurrence,
    RecurrenceUnit,
    ReminderKind,
    ReminderStatus,
)


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


# ------------------------------------------------------------------ promemoria
class ReminderBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: date
    start_time: time | None = None
    kind: ReminderKind = ReminderKind.DEADLINE
    recurrence: Recurrence = Recurrence.NONE
    #: Quando la ricorrenza ha una fine, le occorrenze esistono tutte da
    #: subito. Vuoto = ricorrenza aperta, che ne genera una alla volta.
    recurrence_until: date | None = None
    #: Ogni quanto, per la ricorrenza personalizzata: «ogni 45 giorni».
    recurrence_every: int | None = Field(default=None, ge=1, le=MAX_INTERVALLO)
    recurrence_unit: RecurrenceUnit | None = None
    amount: float | None = None
    owner: str | None = None
    reference: str | None = None
    alert_offsets: list[int] | None = None
    notify_emails: list[EmailStr] | None = None

    @field_validator("alert_offsets")
    @classmethod
    def _clean_offsets(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        return sorted({int(x) for x in v if int(x) >= 0}, reverse=True)

    @field_validator("start_time", mode="before")
    @classmethod
    def _empty_time_is_none(cls, v: object) -> object:
        # Un <input type="time"> svuotato manda una stringa vuota, non null.
        return None if v == "" else v

    @model_validator(mode="after")
    def _check_intervallo(self) -> "ReminderBase":
        """Un intervallo personalizzato ha senso solo con la voce «ogni…».

        Fuori da quella, quantità e unità restano vuote: altrimenti un
        promemoria annuale con dentro «ogni 45 giorni» racconterebbe due cose
        diverse a chi lo rilegge.
        """
        if self.recurrence == Recurrence.CUSTOM:
            if self.recurrence_every is None or self.recurrence_unit is None:
                raise ValueError("Una ricorrenza personalizzata vuole ogni quanto si ripete")
        else:
            self.recurrence_every = None
            self.recurrence_unit = None
        return self


class Occurrence(BaseModel):
    """Una data della serie con il suo importo."""

    due_date: date
    amount: float | None = None


class ReminderCreate(ReminderBase):
    source: str = "manual"
    external_id: str | None = None
    extra: dict | None = None
    #: Importi per singola occorrenza: le rate di un finanziamento raramente
    #: sono uguali. Le date non elencate tengono l'importo generale.
    occurrences: list[Occurrence] | None = None


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_date: date | None = None
    start_time: time | None = None
    kind: ReminderKind | None = None
    status: ReminderStatus | None = None
    recurrence: Recurrence | None = None
    recurrence_until: date | None = None
    recurrence_every: int | None = Field(default=None, ge=1, le=MAX_INTERVALLO)
    recurrence_unit: RecurrenceUnit | None = None
    amount: float | None = None
    owner: str | None = None
    reference: str | None = None
    alert_offsets: list[int] | None = None
    notify_emails: list[EmailStr] | None = None
    extra: dict | None = None

    @field_validator("start_time", mode="before")
    @classmethod
    def _empty_time_is_none(cls, v: object) -> object:
        return None if v == "" else v


class ReminderRead(ORMModel, ReminderBase):
    id: int
    status: ReminderStatus
    source: str
    external_id: str | None
    extra: dict | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    days_left: int
    is_overdue: bool
    series_id: str | None = None
    #: Posizione nella serie, es. (3, 12). Valorizzata solo leggendo il
    #: singolo promemoria: negli elenchi costerebbe una query per riga.
    series_position: tuple[int, int] | None = None

    # Serve quando il database condiviso è uno SQLite di sviluppo.
    @field_validator("completed_at", "created_at", "updated_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return _as_utc(v)


class ReminderPage(BaseModel):
    items: list[ReminderRead]
    total: int
    page: int
    page_size: int


class ReminderStats(BaseModel):
    overdue: int
    due_today: int
    due_in_7_days: int
    due_in_30_days: int
    open_total: int
    done_total: int
    amount_open: float
    by_kind: list["KindStat"]


class KindStat(BaseModel):
    kind: ReminderKind
    count: int


# ----------------------------------------------------------------- calendario
class CalendarDay(BaseModel):
    """Un giorno della griglia mensile con i suoi promemoria.

    `in_month` distingue i giorni del mese richiesto da quelli di riempimento
    agli estremi della griglia (la coda di settembre in una vista di ottobre).
    """

    date: date
    in_month: bool
    items: list[ReminderRead]


class YearDay(BaseModel):
    """Un giorno dell'anno con quanti promemoria porta, divisi per tipo.

    Nella vista annuale i titoli non ci starebbero: servono solo i pallini, e
    mandare i promemoria interi per trecentosessantacinque giorni sarebbe un
    payload enorme per disegnare dei puntini.
    """

    date: date
    deadline: int = 0
    appointment: int = 0
    other: int = 0
    total: int = 0


class CalendarYear(BaseModel):
    year: int
    #: Solo i giorni che hanno qualcosa: gli altri il frontend li disegna vuoti.
    days: list[YearDay]


class CalendarMonth(BaseModel):
    year: int
    month: int
    #: Estremi della griglia mostrata, non del mese: comodi al frontend per
    #: sapere che cosa ha già in mano senza ricalcolarli.
    grid_start: date
    grid_end: date
    days: list[CalendarDay]


# --------------------------------------------------------------------------- notifiche
class NotificationRead(ORMModel):
    id: int
    reminder_id: int
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


class AttentionState(BaseModel):
    """Quanti avvisi imminenti sono stati consegnati e non ancora guardati.

    È quello che serve al processo Electron per decidere se tenere accesa la
    segnalazione sulla barra delle applicazioni.
    """

    count: int
    days: int
    #: Il più urgente dei promemoria coinvolti, per il testo del suggerimento.
    title: str | None = None


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
    """Mappa campo-promemoria -> nome colonna del file."""

    title: str
    due_date: str
    description: str | None = None
    #: Tipo assegnato a tutte le righe importate: i tracciati gestionali
    #: portano scadenze, ma un'agenda esportata porta appuntamenti.
    kind: ReminderKind = ReminderKind.DEADLINE
    amount: str | None = None
    owner: str | None = None
    reference: str | None = None
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
    #: Entro quanti giorni dalla data un avviso ignorato continua a farsi
    #: notare sulla barra delle applicazioni. 0 = mai, si comporta come prima.
    insistent_alert_days: int = 3


class SettingsRead(AppSettings):
    push_configured: bool
    email_configured: bool
    timezone: str


ReminderStats.model_rebuild()
