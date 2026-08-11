from __future__ import annotations

from sqlalchemy.orm import Session

from ...models import Deadline, Notification
from ...schemas import AppSettings
from .base import ChannelResult, Notifier


class InAppNotifier(Notifier):
    """L'avviso è già persistito: marcarlo inviato lo rende visibile nel centro
    notifiche dell'applicazione. Non serve altro."""

    name = "inapp"

    def enabled(self, app_settings: AppSettings) -> bool:
        return app_settings.channel_inapp

    def send(
        self,
        db: Session,
        notification: Notification,
        deadline: Deadline | None,
        app_settings: AppSettings,
    ) -> ChannelResult:
        return ChannelResult(ok=True, detail="disponibile nel centro notifiche")
