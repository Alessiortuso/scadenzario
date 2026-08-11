from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Deadline, DeadlineStatus, Notification, NotificationStatus
from ..schemas import AppSettings
from . import alerts, settings_service
from .notifiers import NOTIFIERS

logger = logging.getLogger(__name__)


def dispatch_notification(
    local_db: Session,
    notification: Notification,
    deadline: Deadline | None,
    app_settings: AppSettings,
) -> dict:
    results: dict[str, dict] = {}
    any_ok = False

    for notifier in NOTIFIERS:
        if not notifier.enabled(app_settings):
            results[notifier.name] = {"ok": False, "detail": "canale disattivato"}
            continue
        try:
            outcome = notifier.send(local_db, notification, deadline, app_settings)
        except Exception as exc:  # pragma: no cover - difensivo
            logger.exception("Canale %s in errore", notifier.name)
            outcome_dict = {"ok": False, "detail": str(exc)[:300]}
        else:
            outcome_dict = {"ok": outcome.ok, "detail": outcome.detail}
        results[notifier.name] = outcome_dict
        any_ok = any_ok or outcome_dict["ok"]

    notification.channel_results = results
    notification.status = NotificationStatus.SENT if any_ok else NotificationStatus.FAILED
    notification.sent_at = datetime.now(timezone.utc)
    return results


def dispatch_due(shared_db: Session, local_db: Session, now: datetime | None = None) -> dict:
    """Consegna tutte le notifiche pendenti la cui ora di invio è arrivata."""
    app_settings = settings_service.get_settings(shared_db)
    pending = alerts.due_notifications(local_db, now)
    if not pending:
        return {"processed": 0, "sent": 0, "failed": 0}

    deadlines = {
        d.id: d
        for d in shared_db.scalars(
            select(Deadline)
            .options(selectinload(Deadline.category))
            .where(Deadline.id.in_({n.deadline_id for n in pending}))
        ).all()
    }

    sent = failed = obsolete = 0
    for notification in pending:
        deadline = deadlines.get(notification.deadline_id)
        # Nel frattempo un'altra postazione può aver evaso o eliminato la
        # scadenza: in quel caso l'avviso non va consegnato.
        if deadline is None or deadline.status != DeadlineStatus.OPEN:
            notification.status = NotificationStatus.CANCELLED
            notification.channel_results = {"motivo": "scadenza non più aperta"}
            obsolete += 1
            continue

        dispatch_notification(local_db, notification, deadline, app_settings)
        if notification.status == NotificationStatus.SENT:
            sent += 1
        else:
            failed += 1

    local_db.commit()
    logger.info(
        "Dispatch notifiche: %s consegnate, %s fallite, %s obsolete", sent, failed, obsolete
    )
    return {"processed": len(pending), "sent": sent, "failed": failed, "obsolete": obsolete}


def run_cycle(shared_db: Session, local_db: Session) -> dict:
    """Un ciclo completo: rigenera gli avvisi e consegna quelli dovuti."""
    generated = alerts.sync_all(shared_db, local_db)
    result = dispatch_due(shared_db, local_db)
    result["generated"] = generated
    return result
