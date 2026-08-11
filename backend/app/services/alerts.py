"""Motore degli avvisi.

Per ogni scadenza aperta calcola le date di preavviso (X giorni prima) e i
solleciti post-scadenza, e materializza le relative notifiche in tabella.
La generazione è idempotente grazie a `Notification.dedupe_key`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings as env_settings
from ..models import Deadline, DeadlineStatus, Notification, NotificationStatus
from ..schemas import AppSettings
from . import settings_service


def effective_offsets(deadline: Deadline, app_settings: AppSettings) -> list[int]:
    if deadline.alert_offsets:
        offsets = deadline.alert_offsets
    elif deadline.category is not None and deadline.category.alert_offsets:
        offsets = deadline.category.alert_offsets
    else:
        offsets = app_settings.default_alert_offsets
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


def _body(deadline: Deadline, days_left: int) -> str:
    due = deadline.due_date.strftime("%d/%m/%Y")
    if days_left < 0:
        n = abs(days_left)
        when = f"è scaduta da {n} giorno" if n == 1 else f"è scaduta da {n} giorni"
    elif days_left == 0:
        when = "scade oggi"
    elif days_left == 1:
        when = "scade domani"
    else:
        when = f"scade tra {days_left} giorni"

    parts = [f"«{deadline.title}» {when} ({due})."]
    if deadline.amount is not None:
        parts.append(f"Importo: € {deadline.amount:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
    if deadline.owner:
        parts.append(f"Riferimento: {deadline.owner}.")
    return " ".join(parts)


def _title(deadline: Deadline, days_left: int) -> str:
    if days_left < 0:
        return f"Scadenza superata: {deadline.title}"
    if days_left == 0:
        return f"Scade oggi: {deadline.title}"
    if days_left == 1:
        return f"Scade domani: {deadline.title}"
    return f"Tra {days_left} giorni: {deadline.title}"


def _planned_alerts(
    deadline: Deadline, app_settings: AppSettings, today: date
) -> list[tuple[str, int, date]]:
    """Ritorna (dedupe_key, offset_days, giorno_di_invio) per la scadenza."""
    created_day = (
        deadline.created_at.astimezone(env_settings.tz).date()
        if deadline.created_at
        else today
    )
    planned: list[tuple[str, int, date]] = []
    due = deadline.due_date

    for offset in effective_offsets(deadline, app_settings):
        alert_day = due - timedelta(days=offset)
        # Non rigenerare preavvisi già "passati" al momento dell'inserimento:
        # evita che una scadenza inserita a ridosso spari tutti i preavvisi.
        if alert_day < created_day and alert_day < today:
            continue
        planned.append((f"{deadline.id}:{due.isoformat()}:-{offset}", offset, alert_day))

    repeat = max(0, app_settings.overdue_repeat_days)
    if repeat:
        for n in range(1, app_settings.overdue_max_reminders + 1):
            alert_day = due + timedelta(days=n * repeat)
            if alert_day < created_day and alert_day < today:
                continue
            planned.append((f"{deadline.id}:{due.isoformat()}:+{n}", -(n * repeat), alert_day))

    return planned


def sync_deadline_notifications(
    db: Session,
    deadline: Deadline,
    app_settings: AppSettings,
    *,
    commit: bool = True,
) -> int:
    """Allinea le notifiche pendenti di una scadenza al suo stato attuale.

    `db` è la sessione sul **database locale**: gli avvisi appartengono alla
    postazione. `deadline` arriva invece dal database condiviso e deve avere la
    categoria già caricata.

    Le notifiche già inviate restano come storico; quelle pendenti vengono
    ricreate (utile quando cambia data, categoria o preavvisi).
    """
    today = datetime.now(env_settings.tz).date()

    db.execute(
        delete(Notification).where(
            Notification.deadline_id == deadline.id,
            Notification.status == NotificationStatus.PENDING,
        )
    )

    created = 0
    if deadline.status == DeadlineStatus.OPEN:
        existing = set(
            db.scalars(
                select(Notification.dedupe_key).where(Notification.deadline_id == deadline.id)
            ).all()
        )

        def add(key: str, offset: int, alert_day: date) -> bool:
            days_left = (deadline.due_date - alert_day).days
            db.add(
                Notification(
                    deadline_id=deadline.id,
                    dedupe_key=key,
                    offset_days=offset,
                    title=_title(deadline, days_left),
                    body=_body(deadline, days_left),
                    severity=_severity(days_left),
                    scheduled_for=_send_datetime(alert_day, app_settings),
                    status=NotificationStatus.PENDING,
                )
            )
            existing.add(key)
            return True

        planned = _planned_alerts(deadline, app_settings, today)
        covers_today = any(alert_day <= today for _, _, alert_day in planned)

        for key, offset, alert_day in planned:
            if key in existing:
                continue
            created += add(key, offset, alert_day)

        # Recupero: una scadenza inserita quando è già scaduta (o già dentro la
        # finestra di preavviso) non avrebbe alcun avviso, perché tutte le date
        # di preavviso sono nel passato. In quel caso ne emettiamo uno subito.
        days_left = (deadline.due_date - today).days
        offsets = effective_offsets(deadline, app_settings)
        in_window = days_left <= max(offsets, default=0)
        catchup_key = f"{deadline.id}:{deadline.due_date.isoformat()}:now"
        if in_window and not covers_today and catchup_key not in existing:
            created += add(catchup_key, days_left, today)

    if commit:
        db.commit()
    else:
        db.flush()
    return created


def sync_all(shared_db: Session, local_db: Session) -> int:
    """Rigenera le notifiche pendenti per tutte le scadenze aperte."""
    app_settings = settings_service.get_settings(shared_db)
    deadlines = shared_db.scalars(
        select(Deadline)
        .options(selectinload(Deadline.category))
        .where(Deadline.status == DeadlineStatus.OPEN)
    ).all()
    total = 0
    for deadline in deadlines:
        total += sync_deadline_notifications(local_db, deadline, app_settings, commit=False)

    # Una scadenza cancellata o evasa da un'altra postazione non deve lasciare
    # avvisi pendenti su questa.
    open_ids = {d.id for d in deadlines}
    stale = local_db.scalars(
        select(Notification).where(Notification.status == NotificationStatus.PENDING)
    ).all()
    for notification in stale:
        if notification.deadline_id not in open_ids:
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
