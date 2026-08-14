from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db import SharedSession, get_local_db, is_shared_configured
from ..models import Notification, NotificationStatus, Reminder, ReminderStatus
from ..schemas import NotificationCounts, NotificationRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifiche"])


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    db: Session = Depends(get_local_db),
    only_unread: bool = False,
    include_pending: bool = False,
    reminder_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[Notification]:
    conditions = []
    if not include_pending:
        conditions.append(Notification.status != NotificationStatus.PENDING)
    if only_unread:
        conditions.append(Notification.read_at.is_(None))
    if reminder_id is not None:
        conditions.append(Notification.reminder_id == reminder_id)

    return list(
        db.scalars(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.scheduled_for.desc(), Notification.id.desc())
            .limit(limit)
        ).all()
    )


@router.get("/counts", response_model=NotificationCounts)
def counts(db: Session = Depends(get_local_db)) -> NotificationCounts:
    base = Notification.status != NotificationStatus.PENDING
    return NotificationCounts(
        unread=db.scalar(select(func.count(Notification.id)).where(base, Notification.read_at.is_(None))) or 0,
        total=db.scalar(select(func.count(Notification.id)).where(base)) or 0,
    )


def _open_reminder_ids(reminder_ids: set[int]) -> set[int] | None:
    """Quali di questi promemoria risultano ancora aperti sul database condiviso.

    Ritorna `None` quando la domanda non è rispondibile — postazione non ancora
    configurata, Neon in fase di risveglio, rete assente: casi in cui *non
    sappiamo*, che vanno tenuti distinti da "il promemoria non è più aperto".
    """
    if not is_shared_configured():
        return None

    shared_db = SharedSession()
    try:
        return set(
            shared_db.scalars(
                select(Reminder.id).where(
                    Reminder.id.in_(reminder_ids),
                    Reminder.status == ReminderStatus.OPEN,
                )
            ).all()
        )
    except SQLAlchemyError as exc:
        logger.warning("Database condiviso non raggiungibile per la verifica avvisi: %s", exc)
        return None
    finally:
        shared_db.close()


@router.get("/to-display", response_model=list[NotificationRead])
def to_display(
    db: Session = Depends(get_local_db),
    limit: int = Query(10, ge=1, le=50),
) -> list[Notification]:
    """Avvisi consegnati ma non ancora mostrati come toast su questa postazione.

    Interrogato dal processo principale di Electron, che mostra la notifica
    nativa di Windows e poi chiama `/displayed`.

    Prima di restituirli si ricontrolla lo stato reale dei promemoria: fra la
    consegna e il toast un collega può aver evaso o eliminato il promemoria da
    un'altra postazione, e mostrare un avviso per qualcosa di già fatto è
    peggio che non mostrarlo affatto.

    Se però il database condiviso non risponde, gli avvisi si mostrano lo
    stesso: un promemoria di troppo si ignora, uno mancato fa perdere una
    scadenza. Per lo stesso motivo l'endpoint **non** dipende dal database
    condiviso: rispondere 503 qui significherebbe nessuna notifica finché Neon
    dorme.
    """
    candidates = list(
        db.scalars(
            select(Notification)
            .where(
                Notification.status == NotificationStatus.SENT,
                Notification.displayed_at.is_(None),
            )
            .order_by(Notification.scheduled_for.asc())
            .limit(limit)
        ).all()
    )
    if not candidates:
        return []

    still_open = _open_reminder_ids({n.reminder_id for n in candidates})
    if still_open is None:
        return candidates

    now = datetime.now(timezone.utc)
    fresh: list[Notification] = []
    for notification in candidates:
        if notification.reminder_id in still_open:
            fresh.append(notification)
        else:
            # Obsoleto: niente toast, e fuori anche dai non letti.
            notification.displayed_at = now
            notification.read_at = notification.read_at or now
            notification.status = NotificationStatus.CANCELLED

    db.commit()
    return fresh


@router.post("/{notification_id}/displayed", status_code=204)
def mark_displayed(notification_id: int, db: Session = Depends(get_local_db)) -> None:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    notification.displayed_at = notification.displayed_at or datetime.now(timezone.utc)
    db.commit()


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, db: Session = Depends(get_local_db)) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    notification.read_at = notification.read_at or datetime.now(timezone.utc)
    db.commit()
    return notification


@router.post("/read-all", response_model=NotificationCounts)
def mark_all_read(db: Session = Depends(get_local_db)) -> NotificationCounts:
    db.execute(
        update(Notification)
        .where(Notification.read_at.is_(None), Notification.status != NotificationStatus.PENDING)
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
    return counts(db)
