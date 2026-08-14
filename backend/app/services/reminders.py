from __future__ import annotations

from calendar import Calendar
from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Recurrence, Reminder, ReminderKind, ReminderStatus
from ..schemas import CalendarDay, CalendarMonth, KindStat, ReminderStats
from . import alerts, settings_service

_RECURRENCE_STEP = {
    Recurrence.MONTHLY: relativedelta(months=1),
    Recurrence.QUARTERLY: relativedelta(months=3),
    Recurrence.SEMIANNUAL: relativedelta(months=6),
    Recurrence.YEARLY: relativedelta(years=1),
}

#: La griglia del calendario comincia di lunedì, come ogni calendario italiano.
_CALENDAR = Calendar(firstweekday=0)


def next_due_date(current: date, recurrence: Recurrence) -> date | None:
    step = _RECURRENCE_STEP.get(recurrence)
    return current + step if step else None


def complete(db: Session, local_db: Session, reminder: Reminder) -> tuple[Reminder, Reminder | None]:
    """Marca un promemoria come evaso e, se ricorrente, genera l'occorrenza successiva."""
    reminder.status = ReminderStatus.DONE
    reminder.completed_at = datetime.now(timezone.utc)

    nxt: Reminder | None = None
    next_date = next_due_date(reminder.due_date, reminder.recurrence)
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
