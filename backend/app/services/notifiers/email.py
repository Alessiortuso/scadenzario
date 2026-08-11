from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ... import runtime_config
from ...config import settings as env_settings
from ...models import Deadline, Notification
from ...schemas import AppSettings
from .base import ChannelResult, Notifier

logger = logging.getLogger(__name__)


def _recipients(deadline: Deadline | None, app_settings: AppSettings) -> list[str]:
    if deadline is not None and deadline.notify_emails:
        return list(deadline.notify_emails)
    return [str(e) for e in app_settings.notify_emails]


def send_mail(to: list[str], subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env_settings.smtp_from
    msg["To"] = ", ".join(to)
    msg.set_content(body)

    with smtplib.SMTP(env_settings.smtp_host, env_settings.smtp_port, timeout=20) as smtp:
        if env_settings.smtp_use_tls:
            smtp.starttls()
        if env_settings.smtp_user:
            smtp.login(env_settings.smtp_user, env_settings.smtp_password)
        smtp.send_message(msg)


class EmailNotifier(Notifier):
    name = "email"

    def enabled(self, app_settings: AppSettings) -> bool:
        # Con l'applicazione installata su più postazioni, solo quella designata
        # invia le email: altrimenti ogni destinatario ne riceverebbe una copia
        # per ogni PC acceso.
        return (
            app_settings.channel_email
            and env_settings.email_enabled
            and runtime_config.email_sender_device()
        )

    def send(
        self,
        db: Session,
        notification: Notification,
        deadline: Deadline | None,
        app_settings: AppSettings,
    ) -> ChannelResult:
        to = _recipients(deadline, app_settings)
        if not to:
            return ChannelResult(ok=False, detail="nessun destinatario configurato")

        lines = [notification.body, ""]
        if deadline is not None:
            lines.append(f"Scadenza: {deadline.due_date.strftime('%d/%m/%Y')}")
            if deadline.description:
                lines.append(f"Note: {deadline.description}")
            if deadline.reference:
                lines.append(f"Riferimento: {deadline.reference}")
        lines += ["", "-- Scadenzario"]

        try:
            send_mail(to, notification.title, "\n".join(lines))
        except Exception as exc:  # pragma: no cover - dipende dal server SMTP
            logger.warning("Invio email fallito: %s", exc)
            return ChannelResult(ok=False, detail=str(exc)[:300])
        return ChannelResult(ok=True, detail=f"inviata a {len(to)} destinatari")
