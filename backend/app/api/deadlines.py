from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db, get_local_db
from ..models import Deadline, DeadlineStatus, Notification, Priority
from ..schemas import (
    DeadlineCreate,
    DeadlinePage,
    DeadlineRead,
    DeadlineStats,
    DeadlineUpdate,
)
from ..services import alerts, deadlines as deadline_service, settings_service

router = APIRouter(prefix="/api/deadlines", tags=["scadenze"])

#: Ordine di urgenza della priorità.
#:
#: In tabella la priorità è una parola ("CRITICAL", "HIGH", ...), quindi
#: ordinarla direttamente darebbe l'ordine alfabetico — critica, alta, bassa,
#: normale — che non vuol dire niente. Qui la si traduce in un rango numerico.
_PRIORITY_RANK = case(
    (Deadline.priority == Priority.CRITICAL, 0),
    (Deadline.priority == Priority.HIGH, 1),
    (Deadline.priority == Priority.NORMAL, 2),
    else_=3,
)


def _get_or_404(db: Session, deadline_id: int) -> Deadline:
    deadline = deadline_service.get_with_relations(db, deadline_id)
    if deadline is None:
        raise HTTPException(status_code=404, detail="Scadenza non trovata")
    return deadline


@router.get("", response_model=DeadlinePage)
def list_deadlines(
    db: Session = Depends(get_db),
    q: str | None = None,
    status: DeadlineStatus | None = None,
    category_id: int | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort: str = Query("due_date", pattern="^-?(due_date|title|amount|created_at|priority)$"),
) -> DeadlinePage:
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                Deadline.title.ilike(like),
                Deadline.description.ilike(like),
                Deadline.owner.ilike(like),
                Deadline.reference.ilike(like),
            )
        )
    if status is not None:
        conditions.append(Deadline.status == status)
    if category_id is not None:
        conditions.append(Deadline.category_id == category_id)
    if due_from is not None:
        conditions.append(Deadline.due_date >= due_from)
    if due_to is not None:
        conditions.append(Deadline.due_date <= due_to)
    if overdue_only:
        conditions.append(Deadline.due_date < date.today())
        conditions.append(Deadline.status == DeadlineStatus.OPEN)

    total = db.scalar(select(func.count(Deadline.id)).where(*conditions)) or 0

    descending = sort.startswith("-")
    field = sort.lstrip("-")
    # `sort=priority` mette le più urgenti in cima, `-priority` le meno urgenti.
    column = _PRIORITY_RANK if field == "priority" else getattr(Deadline, field)

    order = [column.desc() if descending else column.asc()]
    if field == "priority":
        # A parità di priorità conta la data: fra due critiche viene prima
        # quella che scade prima.
        order.append(Deadline.due_date.asc())
    order.append(Deadline.id.asc())

    items = db.scalars(
        select(Deadline)
        .options(selectinload(Deadline.category))
        .where(*conditions)
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return DeadlinePage(items=list(items), total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=DeadlineStats)
def get_stats(db: Session = Depends(get_db)) -> DeadlineStats:
    return deadline_service.stats(db)


@router.get("/upcoming", response_model=list[DeadlineRead])
def upcoming(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Deadline]:
    from datetime import timedelta

    today = date.today()
    return list(
        db.scalars(
            select(Deadline)
            .options(selectinload(Deadline.category))
            .where(
                Deadline.status == DeadlineStatus.OPEN,
                Deadline.due_date <= today + timedelta(days=days),
            )
            .order_by(Deadline.due_date.asc())
            .limit(limit)
        ).all()
    )


@router.get("/{deadline_id}", response_model=DeadlineRead)
def get_deadline(deadline_id: int, db: Session = Depends(get_db)) -> Deadline:
    return _get_or_404(db, deadline_id)


@router.post("", response_model=DeadlineRead, status_code=201)
def create_deadline(
    payload: DeadlineCreate,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Deadline:
    data = payload.model_dump()
    data["notify_emails"] = [str(e) for e in (data.get("notify_emails") or [])] or None
    deadline = Deadline(**data)
    db.add(deadline)
    db.commit()
    saved = _get_or_404(db, deadline.id)
    alerts.sync_deadline_notifications(local_db, saved, settings_service.get_settings(db))
    return saved


@router.patch("/{deadline_id}", response_model=DeadlineRead)
def update_deadline(
    deadline_id: int,
    payload: DeadlineUpdate,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Deadline:
    deadline = _get_or_404(db, deadline_id)
    data = payload.model_dump(exclude_unset=True)
    if "notify_emails" in data:
        data["notify_emails"] = [str(e) for e in (data["notify_emails"] or [])] or None
    for field, value in data.items():
        setattr(deadline, field, value)
    db.commit()
    saved = _get_or_404(db, deadline_id)
    alerts.sync_deadline_notifications(local_db, saved, settings_service.get_settings(db))
    return saved


@router.post("/{deadline_id}/complete", response_model=DeadlineRead)
def complete_deadline(
    deadline_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Deadline:
    deadline = _get_or_404(db, deadline_id)
    deadline_service.complete(db, local_db, deadline)
    return _get_or_404(db, deadline_id)


@router.post("/{deadline_id}/reopen", response_model=DeadlineRead)
def reopen_deadline(
    deadline_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> Deadline:
    deadline = _get_or_404(db, deadline_id)
    deadline_service.reopen(db, local_db, deadline)
    return _get_or_404(db, deadline_id)


@router.delete("/{deadline_id}", status_code=204)
def delete_deadline(
    deadline_id: int,
    db: Session = Depends(get_db),
    local_db: Session = Depends(get_local_db),
) -> None:
    deadline = _get_or_404(db, deadline_id)
    db.delete(deadline)
    db.commit()

    # Gli avvisi di questa postazione sopravvivrebbero fino al ciclo successivo
    # dello scheduler, con la campanella che rimanda a una scadenza inesistente.
    # Sulle altre postazioni ci pensa `alerts.sync_all`.
    local_db.execute(delete(Notification).where(Notification.deadline_id == deadline_id))
    local_db.commit()
