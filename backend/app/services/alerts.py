"""Motore degli avvisi.

Per ogni promemoria aperto calcola le date di preavviso (X giorni prima) e i
solleciti successivi, e materializza le relative notifiche in tabella.
La generazione è idempotente grazie a `Notification.dedupe_key`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..models import Notification, NotificationStatus, Reminder, ReminderKind, ReminderStatus
from ..schemas import AppSettings
from . import settings_service


def effective_offsets(reminder: Reminder, app_settings: AppSettings) -> list[int]:
    offsets = reminder.alert_offsets or app_settings.default_alert_offsets
    return sorted({int(o) for o in offsets if int(o) >= 0}, reverse=True)


def _send_datetime(day: date, app_settings: AppSettings) -> datetime:
    hh, _, mm = app_settings.daily_send_time.partition(":")
    local = datetime.combine(day, time(int(hh), int(mm or 0)), tzinfo=env_settings.tz)
    return local.astimezone(timezone.utc)


def _severity(days_left: int) -> str:
    if days_left < 0:
        return "danger"
    if days_left <= 1:
        return "critical"
    if days_left <= 7:
        return "warning"
    return "info"


def _scade(reminder: Reminder) -> bool:
    """Se di questo promemoria si può dire che «scade».

    Solo le scadenze. Un appuntamento e una nota generica non scadono: «la
    partita di calcetto scade oggi» è italiano sbagliato, e l'interfaccia nel
    frattempo scrive «Oggi» — due testi che si contraddicono sullo stesso dato.
    """
    return reminder.kind == ReminderKind.DEADLINE


def _when(reminder: Reminder, days_left: int) -> str:
    """Come si dice che manca tanto, in base al tipo di promemoria."""
    scade = _scade(reminder)

    if days_left < 0:
        n = abs(days_left)
        giorni = "giorno" if n == 1 else "giorni"
        return f"è scaduta da {n} {giorni}" if scade else f"era {n} {giorni} fa"
    if days_left == 0:
        return "scade oggi" if scade else "è oggi"
    if days_left == 1:
        return "scade domani" if scade else "è domani"
    return f"scade tra {days_left} giorni" if scade else f"è fra {days_left} giorni"


def _body(reminder: Reminder, days_left: int) -> str:
    quando = reminder.due_date.strftime("%d/%m/%Y")
    if reminder.start_time is not None:
        quando += f" alle {reminder.start_time.strftime('%H:%M')}"

    parts = [f"«{reminder.title}» {_when(reminder, days_left)} ({quando})."]
    if reminder.amount is not None:
        parts.append(f"Importo: € {reminder.amount:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
    if reminder.owner:
        parts.append(f"Riferimento: {reminder.owner}.")
    return " ".join(parts)


def _title(reminder: Reminder, days_left: int) -> str:
    scade = _scade(reminder)
    if days_left < 0:
        passato = "Appuntamento passato" if reminder.kind == ReminderKind.APPOINTMENT else "Già passato"
        return f"{'Scadenza superata' if scade else passato}: {reminder.title}"
    if days_left == 0:
        return f"{'Scade oggi' if scade else 'Oggi'}: {reminder.title}"
    if days_left == 1:
        return f"{'Scade domani' if scade else 'Domani'}: {reminder.title}"
    return f"Tra {days_left} giorni: {reminder.title}"


def _planned_alerts(
    reminder: Reminder, app_settings: AppSettings, today: date
) -> list[tuple[str, int, date]]:
    """Ritorna (dedupe_key, offset_days, giorno_di_invio) per il promemoria."""
    created_day = (
        reminder.created_at.astimezone(env_settings.tz).date()
        if reminder.created_at
        else today
    )
    planned: list[tuple[str, int, date]] = []
    due = reminder.due_date

    for offset in effective_offsets(reminder, app_settings):
        alert_day = due - timedelta(days=offset)
        # Non rigenerare preavvisi già "passati" al momento dell'inserimento:
        # evita che un promemoria inserito a ridosso spari tutti i preavvisi.
        if alert_day < created_day and alert_day < today:
            continue
        planned.append((f"{reminder.id}:{due.isoformat()}:-{offset}", offset, alert_day))

    repeat = max(0, app_settings.overdue_repeat_days)
    if repeat:
        for n in range(1, app_settings.overdue_max_reminders + 1):
            alert_day = due + timedelta(days=n * repeat)
            if alert_day < created_day and alert_day < today:
                continue
            planned.append((f"{reminder.id}:{due.isoformat()}:+{n}", -(n * repeat), alert_day))

    return planned


def sync_reminder_notifications(
    db: Session,
    reminder: Reminder,
    app_settings: AppSettings,
    *,
    commit: bool = True,
) -> int:
    """Allinea le notifiche pendenti di un promemoria al suo stato attuale.

    `db` è la sessione sul **database locale**: gli avvisi appartengono alla
    postazione; `reminder` arriva invece dal database condiviso.

    Le notifiche già inviate restano come storico; quelle pendenti vengono
    ricreate (utile quando cambiano la data o i preavvisi).
    """
    today = datetime.now(env_settings.tz).date()

    db.execute(
        delete(Notification).where(
            Notification.reminder_id == reminder.id,
            Notification.status == NotificationStatus.PENDING,
        )
    )

    created = 0
    if reminder.status == ReminderStatus.OPEN:
        existing = set(
            db.scalars(
                select(Notification.dedupe_key).where(Notification.reminder_id == reminder.id)
            ).all()
        )

        def add(key: str, offset: int, alert_day: date) -> bool:
            days_left = (reminder.due_date - alert_day).days
            db.add(
                Notification(
                    reminder_id=reminder.id,
                    dedupe_key=key,
                    offset_days=offset,
                    title=_title(reminder, days_left),
                    body=_body(reminder, days_left),
                    severity=_severity(days_left),
                    scheduled_for=_send_datetime(alert_day, app_settings),
                    status=NotificationStatus.PENDING,
                )
            )
            existing.add(key)
            return True

        planned = _planned_alerts(reminder, app_settings, today)
        covers_today = any(alert_day <= today for _, _, alert_day in planned)

        for key, offset, alert_day in planned:
            if key in existing:
                continue
            created += add(key, offset, alert_day)

        # Recupero: un promemoria inserito quando è già passato (o già dentro la
        # finestra di preavviso) non avrebbe alcun avviso, perché tutte le date
        # di preavviso sono nel passato. In quel caso ne emettiamo uno subito.
        days_left = (reminder.due_date - today).days
        offsets = effective_offsets(reminder, app_settings)
        in_window = days_left <= max(offsets, default=0)
        catchup_key = f"{reminder.id}:{reminder.due_date.isoformat()}:now"
        if in_window and not covers_today and catchup_key not in existing:
            created += add(catchup_key, days_left, today)

    if commit:
        db.commit()
    else:
        db.flush()
    return created


def sync_all(shared_db: Session, local_db: Session) -> int:
    """Rigenera le notifiche pendenti per tutti i promemoria aperti."""
    app_settings = settings_service.get_settings(shared_db)
    reminders = shared_db.scalars(
        select(Reminder).where(Reminder.status == ReminderStatus.OPEN)
    ).all()
    total = 0
    for reminder in reminders:
        total += sync_reminder_notifications(local_db, reminder, app_settings, commit=False)

    # Un promemoria cancellato o evaso da un'altra postazione non deve lasciare
    # avvisi pendenti su questa.
    open_ids = {r.id for r in reminders}
    stale = local_db.scalars(
        select(Notification).where(Notification.status == NotificationStatus.PENDING)
    ).all()
    for notification in stale:
        if notification.reminder_id not in open_ids:
            local_db.delete(notification)

    local_db.commit()
    return total


def due_notifications(db: Session, now: datetime | None = None) -> list[Notification]:
    now = now or datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.status == NotificationStatus.PENDING,
                Notification.scheduled_for <= now,
            )
            .order_by(Notification.scheduled_for)
        ).all()
    )
