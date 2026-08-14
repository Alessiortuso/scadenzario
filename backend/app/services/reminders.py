from __future__ import annotations

import uuid
from calendar import Calendar
from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Recurrence, Reminder, ReminderKind, ReminderStatus
from ..schemas import CalendarDay, CalendarMonth, CalendarYear, KindStat, ReminderStats, YearDay
from . import alerts, settings_service

_RECURRENCE_STEP = {
    Recurrence.MONTHLY: relativedelta(months=1),
    Recurrence.QUARTERLY: relativedelta(months=3),
    Recurrence.SEMIANNUAL: relativedelta(months=6),
    Recurrence.YEARLY: relativedelta(years=1),
}

#: La griglia del calendario comincia di lunedì, come ogni calendario italiano.
_CALENDAR = Calendar(firstweekday=0)

#: Quante occorrenze si accetta di creare in un colpo solo. Con la ricorrenza
#: più fitta (mensile) sono dieci anni: oltre, quasi certamente è una data di
#: fine sbagliata, e crearne migliaia riempirebbe il calendario di spazzatura
#: difficile da togliere.
MAX_OCCORRENZE = 120


def next_due_date(current: date, recurrence: Recurrence) -> date | None:
    step = _RECURRENCE_STEP.get(recurrence)
    return current + step if step else None


def occurrence_dates(
    start: date, recurrence: Recurrence, until: date | None
) -> list[date]:
    """Le date in cui un promemoria ricorrente si ripresenta, fino a `until`.

    La prima è sempre quella di partenza: chi crea dodici rate mensili si
    aspetta dodici promemoria in tutto, non uno più dodici.

    Senza ricorrenza o senza data di fine la lista è la sola data iniziale: la
    ricorrenza aperta continua a generare un'occorrenza per volta alla
    chiusura, com'è sempre stato.
    """
    passo = _RECURRENCE_STEP.get(recurrence)
    if passo is None or until is None or until < start:
        return [start]

    # Ogni data si calcola dalla partenza moltiplicando il passo, non sommando
    # al risultato precedente: chi paga il 31 del mese vuole il 31, e il
    # febbraio corto non deve spostare all'indietro tutte le rate successive.
    date_serie: list[date] = []
    for n in range(MAX_OCCORRENZE):
        quando = start + passo * n
        if quando > until:
            break
        date_serie.append(quando)
    return date_serie


def create_series(
    db: Session,
    local_db: Session,
    dati: dict,
    importi: dict[date, float | None] | None = None,
) -> list[Reminder]:
    """Crea un promemoria e, se ha una fine, tutte le sue occorrenze.

    `importi` permette di dare a ogni occorrenza il proprio valore — le rate
    di un finanziamento raramente sono uguali fra loro. Le date che non
    compaiono tengono l'importo del promemoria di partenza.

    Ritorna le occorrenze in ordine di data; la prima è quella che l'utente ha
    appena compilato.
    """
    from . import alerts, settings_service

    date_serie = occurrence_dates(
        dati["due_date"], dati.get("recurrence") or Recurrence.NONE, dati.get("recurrence_until")
    )
    serie = str(uuid.uuid4()) if len(date_serie) > 1 else None

    creati: list[Reminder] = []
    for quando in date_serie:
        occorrenza = Reminder(**{**dati, "due_date": quando, "series_id": serie})
        if importi and quando in importi:
            occorrenza.amount = importi[quando]
        db.add(occorrenza)
        creati.append(occorrenza)

    db.commit()

    app_settings = settings_service.get_settings(db)
    for occorrenza in creati:
        alerts.sync_reminder_notifications(local_db, occorrenza, app_settings, commit=False)
    local_db.commit()

    return creati


def delete_series(db: Session, local_db: Session, series_id: str) -> list[int]:
    """Elimina tutte le occorrenze di una serie. Ritorna gli id rimossi."""
    from ..models import Notification

    occorrenze = list(db.scalars(select(Reminder).where(Reminder.series_id == series_id)).all())
    ids = [r.id for r in occorrenze]
    for occorrenza in occorrenze:
        db.delete(occorrenza)
    db.commit()

    if ids:
        local_db.execute(delete(Notification).where(Notification.reminder_id.in_(ids)))
        local_db.commit()
    return ids


def series_position(db: Session, reminder: Reminder) -> tuple[int, int] | None:
    """«La terza di dodici», per chi apre una singola occorrenza."""
    if reminder.series_id is None:
        return None

    date_serie = list(
        db.scalars(
            select(Reminder.due_date)
            .where(Reminder.series_id == reminder.series_id)
            .order_by(Reminder.due_date.asc())
        ).all()
    )
    if reminder.due_date not in date_serie:
        return None
    return date_serie.index(reminder.due_date) + 1, len(date_serie)


def complete(db: Session, local_db: Session, reminder: Reminder) -> tuple[Reminder, Reminder | None]:
    """Marca un promemoria come evaso e, se ricorrente, genera l'occorrenza successiva."""
    reminder.status = ReminderStatus.DONE
    reminder.completed_at = datetime.now(timezone.utc)

    # Le occorrenze di una serie con una fine esistono già tutte: generarne
    # un'altra alla chiusura significherebbe sdoppiare l'ultima rata.
    nxt: Reminder | None = None
    next_date = None if reminder.series_id else next_due_date(reminder.due_date, reminder.recurrence)
    if next_date is not None:
        nxt = Reminder(
            title=reminder.title,
            description=reminder.description,
            due_date=next_date,
            start_time=reminder.start_time,
            kind=reminder.kind,
            recurrence=reminder.recurrence,
            amount=reminder.amount,
            owner=reminder.owner,
            reference=reminder.reference,
            alert_offsets=reminder.alert_offsets,
            notify_emails=reminder.notify_emails,
            source=reminder.source,
            external_id=None,  # l'occorrenza successiva non appartiene alla fonte esterna
            extra=reminder.extra,
        )
        db.add(nxt)

    db.commit()

    app_settings = settings_service.get_settings(db)
    alerts.sync_reminder_notifications(local_db, reminder, app_settings, commit=False)
    if nxt is not None:
        alerts.sync_reminder_notifications(local_db, nxt, app_settings, commit=False)
    local_db.commit()
    return reminder, nxt


def reopen(db: Session, local_db: Session, reminder: Reminder) -> Reminder:
    reminder.status = ReminderStatus.OPEN
    reminder.completed_at = None
    db.commit()
    alerts.sync_reminder_notifications(
        local_db, reminder, settings_service.get_settings(db), commit=True
    )
    return reminder


def stats(db: Session) -> ReminderStats:
    today = date.today()
    open_filter = Reminder.status == ReminderStatus.OPEN

    def count(*conditions) -> int:
        return db.scalar(select(func.count(Reminder.id)).where(*conditions)) or 0

    by_kind_rows = dict(
        db.execute(
            select(Reminder.kind, func.count(Reminder.id)).where(open_filter).group_by(Reminder.kind)
        ).all()
    )

    return ReminderStats(
        overdue=count(open_filter, Reminder.due_date < today),
        due_today=count(open_filter, Reminder.due_date == today),
        due_in_7_days=count(open_filter, Reminder.due_date >= today, Reminder.due_date <= today + timedelta(days=7)),
        due_in_30_days=count(open_filter, Reminder.due_date >= today, Reminder.due_date <= today + timedelta(days=30)),
        open_total=count(open_filter),
        done_total=count(Reminder.status == ReminderStatus.DONE),
        amount_open=float(db.scalar(select(func.coalesce(func.sum(Reminder.amount), 0.0)).where(open_filter)) or 0.0),
        # Tutti i tipi, anche quelli a zero: una griglia che cambia numero di
        # riquadri a seconda dei dati si legge peggio di una con degli zeri.
        by_kind=[KindStat(kind=kind, count=by_kind_rows.get(kind, 0)) for kind in ReminderKind],
    )


def get(db: Session, reminder_id: int) -> Reminder | None:
    return db.get(Reminder, reminder_id)


def month_grid(year: int, month: int) -> list[list[date]]:
    """Le settimane complete che coprono il mese, lunedì → domenica."""
    return [list(week) for week in _CALENDAR.monthdatescalendar(year, month)]


def calendar_month(
    db: Session,
    year: int,
    month: int,
    *,
    kind: ReminderKind | None = None,
    include_done: bool = True,
) -> CalendarMonth:
    """I promemoria del mese, già distribuiti sui giorni della griglia.

    La griglia comprende la coda del mese precedente e l'inizio del successivo,
    così il calendario mostra settimane intere: quei giorni portano i propri
    promemoria come tutti gli altri, marcati `in_month=False`.
    """
    weeks = month_grid(year, month)
    grid_start, grid_end = weeks[0][0], weeks[-1][-1]

    conditions = [Reminder.due_date >= grid_start, Reminder.due_date <= grid_end]
    if kind is not None:
        conditions.append(Reminder.kind == kind)
    if not include_done:
        conditions.append(Reminder.status == ReminderStatus.OPEN)

    items = db.scalars(
        select(Reminder)
        .where(*conditions)
        # Prima chi ha un orario, in ordine di ora; poi gli impegni di giornata.
        .order_by(
            Reminder.due_date.asc(),
            Reminder.start_time.asc().nulls_last(),
            Reminder.id.asc(),
        )
    ).all()

    by_day: dict[date, list[Reminder]] = {}
    for item in items:
        by_day.setdefault(item.due_date, []).append(item)

    return CalendarMonth(
        year=year,
        month=month,
        grid_start=grid_start,
        grid_end=grid_end,
        days=[
            CalendarDay(date=day, in_month=day.month == month, items=by_day.get(day, []))
            for week in weeks
            for day in week
        ],
    )


def calendar_year(
    db: Session,
    year: int,
    *,
    kind: ReminderKind | None = None,
    include_done: bool = True,
) -> CalendarYear:
    """Quanti promemoria cadono in ogni giorno dell'anno, divisi per tipo.

    Solo conteggi: la vista annuale disegna dodici mesi in miniatura, dove di
    un promemoria si vede un pallino e nient'altro. Restituire i promemoria
    interi per un anno significherebbe spedire migliaia di righe per colorare
    dei puntini.
    """
    conditions = [
        Reminder.due_date >= date(year, 1, 1),
        Reminder.due_date <= date(year, 12, 31),
    ]
    if kind is not None:
        conditions.append(Reminder.kind == kind)
    if not include_done:
        conditions.append(Reminder.status == ReminderStatus.OPEN)

    righe = db.execute(
        select(Reminder.due_date, Reminder.kind, func.count(Reminder.id))
        .where(*conditions)
        .group_by(Reminder.due_date, Reminder.kind)
    ).all()

    giorni: dict[date, YearDay] = {}
    for quando, tipo, quanti in righe:
        giorno = giorni.setdefault(quando, YearDay(date=quando))
        setattr(giorno, tipo.value, getattr(giorno, tipo.value) + quanti)
        giorno.total += quanti

    return CalendarYear(year=year, days=[giorni[k] for k in sorted(giorni)])
