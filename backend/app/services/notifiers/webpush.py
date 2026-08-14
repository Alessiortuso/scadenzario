from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings as env_settings
from ...models import Notification, PushSubscription, Reminder
from ...schemas import AppSettings
from .base import ChannelResult, Notifier

logger = logging.getLogger(__name__)


def _payload(notification: Notification) -> str:
    return json.dumps(
        {
            "title": notification.title,
            "body": notification.body,
            "severity": notification.severity,
            "notificationId": notification.id,
            "reminderId": notification.reminder_id,
            "url": f"/promemoria/{notification.reminder_id}",
            "tag": f"reminder-{notification.reminder_id}",
        },
        ensure_ascii=False,
    )


def send_raw(db: Session, payload: str) -> tuple[int, int, list[str]]:
    """Invia un payload a tutte le subscription attive.

    Ritorna (inviate, fallite, dettagli). Le subscription non più valide
    (404/410) vengono disattivate.
    """
    from pywebpush import WebPushException, webpush

    subs = db.scalars(select(PushSubscription).where(PushSubscription.active.is_(True))).all()
    sent = failed = 0
    details: list[str] = []

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=env_settings.vapid_private_key,
                vapid_claims={"sub": env_settings.vapid_subject},
                ttl=60 * 60 * 24,
            )
            sent += 1
        except WebPushException as exc:  # pragma: no cover - dipende dal push service
            status = getattr(exc.response, "status_code", None)
            failed += 1
            sub.last_error = str(exc)[:500]
            if status in (404, 410):
                sub.active = False
                details.append(f"subscription {sub.id} disattivata ({status})")
            else:
                details.append(f"subscription {sub.id}: {status or exc}")
            logger.warning("Web push fallito per subscription %s: %s", sub.id, exc)

    db.commit()
    return sent, failed, details


class WebPushNotifier(Notifier):
    name = "push"

    def enabled(self, app_settings: AppSettings) -> bool:
        return app_settings.channel_push and env_settings.push_enabled

    def send(
        self,
        db: Session,
        notification: Notification,
        reminder: Reminder | None,
        app_settings: AppSettings,
    ) -> ChannelResult:
        sent, failed, details = send_raw(db, _payload(notification))
        if sent == 0 and failed == 0:
            return ChannelResult(ok=False, detail="nessun dispositivo registrato")
        return ChannelResult(
            ok=sent > 0,
            detail=f"inviate {sent}, fallite {failed}" + (f" ({'; '.join(details)})" if details else ""),
        )
