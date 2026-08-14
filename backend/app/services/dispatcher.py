from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, NotificationStatus, Reminder, ReminderStatus
from ..schemas import AppSettings
from . import alerts, settings_service
from .notifiers import NOTIFIERS

logger = logging.getLogger(__name__)


def dispatch_notification(
    local_db: Session,
    notification: Notification,
    reminder: Reminder | None,
    app_settings: AppSettings,
) -> dict:
    results: dict[str, dict] = {}
    any_ok = False

    for notifier in NOTIFIERS:
        if not notifier.enabled(app_settings):
            results[notifier.name] = {"ok": False, "detail": "canale disattivato"}
            continue
        try:
            outcome = notifier.send(local_db, notification, reminder, app_settings)
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

    reminders = {
        r.id: r
        for r in shared_db.scalars(
            select(Reminder).where(Reminder.id.in_({n.reminder_id for n in pending}))
        ).all()
    }

    sent = failed = obsolete = 0
    for notification in pending:
        reminder = reminders.get(notification.reminder_id)
        # Nel frattempo un'altra postazione può aver evaso o eliminato il
        # promemoria: in quel caso l'avviso non va consegnato.
        if reminder is None or reminder.status != ReminderStatus.OPEN:
            notification.status = NotificationStatus.CANCELLED
            notification.channel_results = {"motivo": "promemoria non più aperto"}
            obsolete += 1
            continue

        dispatch_notification(local_db, notification, reminder, app_settings)
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
