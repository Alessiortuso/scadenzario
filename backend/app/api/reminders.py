from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db, get_local_db
from ..models import Notification, Reminder, ReminderKind, ReminderStatus
from ..schemas import (
    CalendarMonth,
    ReminderCreate,
    ReminderPage,
    ReminderRead,
    ReminderStats,
    ReminderUpdate,
)
from ..services import alerts, reminders as reminder_service, settings_service

router = APIRouter(prefix="/api/reminders", tags=["promemoria"])


def _get_or_404(db: Session, reminder_id: int) -> Reminder:
    reminder = reminder_service.get(db, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Promemoria non trovato")
    return reminder


@router.get("", response_model=ReminderPage)
def list_reminders(
    db: Session = Depends(get_db),
    q: str | None = None,
    status: ReminderStatus | None = None,
    kind: ReminderKind | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort: str = Query("due_date", pattern="^-?(due_date|title|amount|created_at)$"),
) -> ReminderPage:
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                Reminder.title.ilike(like),
                Reminder.description.ilike(like),
                Reminder.owner.ilike(like),
                Reminder.reference.ilike(like),
            )
        )
    if status is not None:
        conditions.append(Reminder.status == status)
    if kind is not None:
        conditions.append(Reminder.kind == kind)
    if due_from is not None:
        conditions.append(Reminder.due_date >= due_from)
    if due_to is not None:
        conditions.append(Reminder.due_date <= due_to)
    if overdue_only:
        conditions.append(Reminder.due_date < date.today())
        conditions.append(Reminder.status == ReminderStatus.OPEN)

    total = db.scalar(select(func.count(Reminder.id)).where(*conditions)) or 0

    descending = sort.startswith("-")
    field = sort.lstrip("-")
    column = getattr(Reminder, field)

    order = [column.desc() if descending else column.asc()]
    if field == "due_date":
        # A parità di giorno decide l'ora: le 9:30 prima delle 15:00, e gli
        # impegni senza orario in coda alla giornata.
        order.append(Reminder.start_time.asc().nulls_last())
    order.append(Reminder.id.asc())

    items = db.scalars(
        select(Reminder)
        .where(*conditions)
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ReminderPage(items=list(items), total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=ReminderStats)
def get_stats(db: Session = Depends(get_db)) -> ReminderStats:
    return reminder_service.stats(db)


@router.get("/calendar", response_model=CalendarMonth)
def calendar(
    year: int = Query(..., ge=1970, le=2200),
    month: int = Query(..., ge=1, le=12),
    kind: ReminderKind | None = None,
    include_done: bool = True,
    db: Session = Depends(get_db),
) -> CalendarMonth:
    """Il mese richiesto pronto da disegnare: settimane intere, giorno per giorno."""
    return reminder_service.calendar_month(db, year, month, kind=kind, include_done=include_done)


@router.get("/upcoming", response_model=list[ReminderRead])
def upcoming(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Reminder]:
    from datetime import timedelta

    today = date.today()
    return list(
        db.scalars(
            select(Reminder)
            .where(
                Reminder.status == ReminderStatus.OPEN,
                Reminder.due_date <= today + timedelta(days=days),
            )
            .order_by(Reminder.due_date.asc(), Reminder.start_time.asc().nulls_last())
            .limit(limit)
        ).all()
    )


@router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(reminder_id: int, db: Session = Depends(get_db)) -> Reminder:
    return _get_or_404(db, reminder_id)


@router.post("", response_model=ReminderRead, status_code=201)
def create_reminder(
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Reminder:
    data = payload.model_dump()
    data["notify_emails"] = [str(e) for e in (data.get("notify_emails") or [])] or None
    reminder = Reminder(**data)
    db.add(reminder)
    db.commit()
    saved = _get_or_404(db, reminder.id)
    alerts.sync_reminder_notifications(local_db, saved, settings_service.get_settings(db))
    return saved


@router.patch("/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Reminder:
    reminder = _get_or_404(db, reminder_id)
    data = payload.model_dump(exclude_unset=True)
    if "notify_emails" in data:
        data["notify_emails"] = [str(e) for e in (data["notify_emails"] or [])] or None
    for field, value in data.items():
        setattr(reminder, field, value)
    db.commit()
    saved = _get_or_404(db, reminder_id)
    alerts.sync_reminder_notifications(local_db, saved, settings_service.get_settings(db))
    return saved


@router.post("/{reminder_id}/complete", response_model=ReminderRead)
def complete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Reminder:
    reminder = _get_or_404(db, reminder_id)
    reminder_service.complete(db, local_db, reminder)
    return _get_or_404(db, reminder_id)


@router.post("/{reminder_id}/reopen", response_model=ReminderRead)
def reopen_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Reminder:
    reminder = _get_or_404(db, reminder_id)
    reminder_service.reopen(db, local_db, reminder)
    return _get_or_404(db, reminder_id)


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> None:
    reminder = _get_or_404(db, reminder_id)
    db.delete(reminder)
    db.commit()

    # Gli avvisi di questa postazione sopravvivrebbero fino al ciclo successivo
    # dello scheduler, con la campanella che rimanda a un promemoria inesistente.
    # Sulle altre postazioni ci pensa `alerts.sync_all`.
    local_db.execute(delete(Notification).where(Notification.reminder_id == reminder_id))
    local_db.commit()
