"""Ricorrenze, chiusura di un promemoria e statistiche della dashboard."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.models import Reminder, ReminderStatus, Notification, Recurrence
from app.services import reminders as reminder_service


def test_passo_delle_ricorrenze():
    partenza = date(2026, 1, 31)
    assert reminder_service.next_due_date(partenza, Recurrence.MONTHLY) == date(2026, 2, 28)
    assert reminder_service.next_due_date(date(2026, 3, 15), Recurrence.QUARTERLY) == date(2026, 6, 15)
    assert reminder_service.next_due_date(date(2026, 3, 15), Recurrence.SEMIANNUAL) == date(2026, 9, 15)
    assert reminder_service.next_due_date(date(2026, 3, 15), Recurrence.YEARLY) == date(2027, 3, 15)
    assert reminder_service.next_due_date(date(2026, 3, 15), Recurrence.NONE) is None


def test_chiudere_un_promemoria_non_ricorrente_non_ne_crea_altri(shared_db, local_db, make_reminder):
    reminder = make_reminder(30)
    evasa, successiva = reminder_service.complete(shared_db, local_db, reminder)

    assert evasa.status == ReminderStatus.DONE
    assert evasa.completed_at is not None
    assert successiva is None
    assert shared_db.scalar(select(Reminder).where(Reminder.status == ReminderStatus.OPEN)) is None


def test_chiudere_una_ricorrente_genera_l_occorrenza_successiva(shared_db, local_db, make_reminder):
    reminder = make_reminder(
        30,
        title="Versamento IVA",
        recurrence=Recurrence.QUARTERLY,
        amount=1200.0,
        owner="Amministrazione",
    )
    _, successiva = reminder_service.complete(shared_db, local_db, reminder)

    assert successiva is not None
    assert successiva.due_date == reminder.due_date + relativedelta(months=3)
    assert successiva.status == ReminderStatus.OPEN
    assert (successiva.title, successiva.amount, successiva.owner) == ("Versamento IVA", 1200.0, "Amministrazione")


def test_l_occorrenza_successiva_non_eredita_l_id_esterno(shared_db, local_db, make_reminder):
    """Altrimenti l'upsert dell'import la sovrascriverebbe con la riga vecchia."""
    reminder = make_reminder(30, recurrence=Recurrence.MONTHLY, source="csv", external_id="RIGA-42")
    _, successiva = reminder_service.complete(shared_db, local_db, reminder)

    assert successiva.external_id is None
    assert successiva.source == "csv"


def test_chiudere_sposta_gli_avvisi_sulla_nuova_occorrenza(shared_db, local_db, make_reminder):
    reminder = make_reminder(30, recurrence=Recurrence.MONTHLY, alert_offsets=[7])
    _, successiva = reminder_service.complete(shared_db, local_db, reminder)

    riferimenti = {n.reminder_id for n in local_db.scalars(select(Notification)).all()}
    assert reminder.id not in riferimenti
    assert successiva.id in riferimenti


def test_riaprire_ripristina_gli_avvisi(shared_db, local_db, make_reminder):
    reminder = make_reminder(30, alert_offsets=[7])
    reminder_service.complete(shared_db, local_db, reminder)
    assert local_db.scalar(select(Notification).where(Notification.reminder_id == reminder.id)) is None

    reminder_service.reopen(shared_db, local_db, reminder)

    assert reminder.status == ReminderStatus.OPEN
    assert reminder.completed_at is None
    assert local_db.scalar(select(Notification).where(Notification.reminder_id == reminder.id)) is not None


def test_statistiche_della_dashboard(shared_db, local_db, make_reminder):
    make_reminder(-2, title="Scaduta", amount=100.0)
    make_reminder(0, title="Oggi", amount=200.0)
    make_reminder(5, title="Fra cinque giorni", amount=300.0)
    make_reminder(20, title="Fra venti giorni")
    make_reminder(100, title="Lontana")
    evasa = make_reminder(3, title="Evasa", amount=999.0)
    reminder_service.complete(shared_db, local_db, evasa)

    stats = reminder_service.stats(shared_db)

    assert stats.overdue == 1
    assert stats.due_today == 1
    assert stats.due_in_7_days == 2  # oggi + fra cinque giorni
    assert stats.due_in_30_days == 3  # ... + fra venti giorni
    assert stats.open_total == 5
    assert stats.done_total == 1
    assert stats.amount_open == 600.0  # l'importo del promemoria evaso non conta
