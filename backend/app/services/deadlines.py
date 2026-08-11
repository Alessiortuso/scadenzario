from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Category, Deadline, DeadlineStatus, Recurrence
from ..schemas import CategoryStat, DeadlineStats
from . import alerts, settings_service

_RECURRENCE_STEP = {
    Recurrence.MONTHLY: relativedelta(months=1),
    Recurrence.QUARTERLY: relativedelta(months=3),
    Recurrence.SEMIANNUAL: relativedelta(months=6),
    Recurrence.YEARLY: relativedelta(years=1),
}


def next_due_date(current: date, recurrence: Recurrence) -> date | None:
    step = _RECURRENCE_STEP.get(recurrence)
    return current + step if step else None


def complete(db: Session, local_db: Session, deadline: Deadline) -> tuple[Deadline, Deadline | None]:
    """Marca una scadenza come evasa e, se ricorrente, genera l'occorrenza successiva."""
    deadline.status = DeadlineStatus.DONE
    deadline.completed_at = datetime.now(timezone.utc)

    nxt: Deadline | None = None
    next_date = next_due_date(deadline.due_date, deadline.recurrence)
    if next_date is not None:
        nxt = Deadline(
            title=deadline.title,
            description=deadline.description,
            due_date=next_date,
            priority=deadline.priority,
            recurrence=deadline.recurrence,
            amount=deadline.amount,
            owner=deadline.owner,
            reference=deadline.reference,
            category_id=deadline.category_id,
            alert_offsets=deadline.alert_offsets,
            notify_emails=deadline.notify_emails,
            source=deadline.source,
            external_id=None,  # l'occorrenza successiva non appartiene alla fonte esterna
            extra=deadline.extra,
        )
        db.add(nxt)

    db.commit()

    app_settings = settings_service.get_settings(db)
    alerts.sync_deadline_notifications(local_db, deadline, app_settings, commit=False)
    if nxt is not None:
        alerts.sync_deadline_notifications(local_db, nxt, app_settings, commit=False)
    local_db.commit()
    return deadline, nxt


def reopen(db: Session, local_db: Session, deadline: Deadline) -> Deadline:
    deadline.status = DeadlineStatus.OPEN
    deadline.completed_at = None
    db.commit()
    alerts.sync_deadline_notifications(
        local_db, deadline, settings_service.get_settings(db), commit=True
    )
    return deadline


def stats(db: Session) -> DeadlineStats:
    today = date.today()
    open_filter = Deadline.status == DeadlineStatus.OPEN

    def count(*conditions) -> int:
        return db.scalar(select(func.count(Deadline.id)).where(*conditions)) or 0

    by_category_rows = db.execute(
        select(
            Deadline.category_id,
            func.coalesce(Category.name, "Senza categoria"),
            func.coalesce(Category.color, "#94a3b8"),
            func.count(Deadline.id),
        )
        .join(Category, Category.id == Deadline.category_id, isouter=True)
        .where(open_filter)
        .group_by(Deadline.category_id, Category.name, Category.color)
        .order_by(func.count(Deadline.id).desc())
    ).all()

    return DeadlineStats(
        overdue=count(open_filter, Deadline.due_date < today),
        due_today=count(open_filter, Deadline.due_date == today),
        due_in_7_days=count(open_filter, Deadline.due_date >= today, Deadline.due_date <= today + timedelta(days=7)),
        due_in_30_days=count(open_filter, Deadline.due_date >= today, Deadline.due_date <= today + timedelta(days=30)),
        open_total=count(open_filter),
        done_total=count(Deadline.status == DeadlineStatus.DONE),
        amount_open=float(db.scalar(select(func.coalesce(func.sum(Deadline.amount), 0.0)).where(open_filter)) or 0.0),
        by_category=[
            CategoryStat(category_id=cid, name=name, color=color, count=cnt)
            for cid, name, color, cnt in by_category_rows
        ],
    )


def get_with_relations(db: Session, deadline_id: int) -> Deadline | None:
    return db.scalar(
        select(Deadline).options(selectinload(Deadline.category)).where(Deadline.id == deadline_id)
    )
