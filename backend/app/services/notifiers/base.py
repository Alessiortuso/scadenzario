from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...models import Notification, Reminder
from ...schemas import AppSettings


@dataclass(slots=True)
class ChannelResult:
    ok: bool
    detail: str = ""


class Notifier(ABC):
    """Canale di consegna di un avviso.

    Aggiungere un canale (Telegram, SMS, ...) significa solo implementare questa
    interfaccia e registrarla nel dispatcher.

    `db` è la sessione sul database locale; `reminder` è il promemoria letto dal
    database condiviso e può essere `None` se nel frattempo è stato rimosso.
    """

    name: str = "base"

    @abstractmethod
    def enabled(self, app_settings: AppSettings) -> bool: ...

    @abstractmethod
    def send(
        self,
        db: Session,
        notification: Notification,
        reminder: Reminder | None,
        app_settings: AppSettings,
    ) -> ChannelResult: ...
