"""Ricorrenze, chiusura di una scadenza e statistiche della dashboard."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.models import Category, Deadline, DeadlineStatus, Notification, Recurrence
from app.services import deadlines as deadline_service


def test_passo_delle_ricorrenze():
    partenza = date(2026, 1, 31)
    assert deadline_service.next_due_date(partenza, Recurrence.MONTHLY) == date(2026, 2, 28)
    assert deadline_service.next_due_date(date(2026, 3, 15), Recurrence.QUARTERLY) == date(2026, 6, 15)
    assert deadline_service.next_due_date(date(2026, 3, 15), Recurrence.SEMIANNUAL) == date(2026, 9, 15)
    assert deadline_service.next_due_date(date(2026, 3, 15), Recurrence.YEARLY) == date(2027, 3, 15)
    assert deadline_service.next_due_date(date(2026, 3, 15), Recurrence.NONE) is None


def test_chiudere_una_scadenza_non_ricorrente_non_ne_crea_altre(shared_db, local_db, make_deadline):
    deadline = make_deadline(30)
    evasa, successiva = deadline_service.complete(shared_db, local_db, deadline)

    assert evasa.status == DeadlineStatus.DONE
    assert evasa.completed_at is not None
    assert successiva is None
    assert shared_db.scalar(select(Deadline).where(Deadline.status == DeadlineStatus.OPEN)) is None


def test_chiudere_una_ricorrente_genera_l_occorrenza_successiva(shared_db, local_db, make_deadline):
    categoria = Category(name="Fiscale", color="#ef4444")
    shared_db.add(categoria)
    shared_db.commit()

    deadline = make_deadline(
        30,
        title="Versamento IVA",
        recurrence=Recurrence.QUARTERLY,
        amount=1200.0,
        owner="Amministrazione",
        category=categoria,
    )
    _, successiva = deadline_service.complete(shared_db, local_db, deadline)

    assert successiva is not None
    assert successiva.due_date == deadline.due_date + relativedelta(months=3)
    assert successiva.status == DeadlineStatus.OPEN
    assert (successiva.title, successiva.amount, successiva.owner) == ("Versamento IVA", 1200.0, "Amministrazione")
    assert successiva.category_id == categoria.id


def test_l_occorrenza_successiva_non_eredita_l_id_esterno(shared_db, local_db, make_deadline):
    """Altrimenti l'upsert dell'import la sovrascriverebbe con la riga vecchia."""
    deadline = make_deadline(30, recurrence=Recurrence.MONTHLY, source="csv", external_id="RIGA-42")
    _, successiva = deadline_service.complete(shared_db, local_db, deadline)

    assert successiva.external_id is None
    assert successiva.source == "csv"


def test_chiudere_sposta_gli_avvisi_sulla_nuova_occorrenza(shared_db, local_db, make_deadline):
    deadline = make_deadline(30, recurrence=Recurrence.MONTHLY, alert_offsets=[7])
    _, successiva = deadline_service.complete(shared_db, local_db, deadline)

    riferimenti = {n.deadline_id for n in local_db.scalars(select(Notification)).all()}
    assert deadline.id not in riferimenti
    assert successiva.id in riferimenti


def test_riaprire_ripristina_gli_avvisi(shared_db, local_db, make_deadline):
    deadline = make_deadline(30, alert_offsets=[7])
    deadline_service.complete(shared_db, local_db, deadline)
    assert local_db.scalar(select(Notification).where(Notification.deadline_id == deadline.id)) is None

    deadline_service.reopen(shared_db, local_db, deadline)

    assert deadline.status == DeadlineStatus.OPEN
    assert deadline.completed_at is None
    assert local_db.scalar(select(Notification).where(Notification.deadline_id == deadline.id)) is not None


def test_statistiche_della_dashboard(shared_db, local_db, make_deadline):
    categoria = Category(name="Fiscale", color="#ef4444")
    shared_db.add(categoria)
    shared_db.commit()

    make_deadline(-2, title="Scaduta", amount=100.0, category=categoria)
    make_deadline(0, title="Oggi", amount=200.0, category=categoria)
    make_deadline(5, title="Fra cinque giorni", amount=300.0)
    make_deadline(20, title="Fra venti giorni")
    make_deadline(100, title="Lontana")
    evasa = make_deadline(3, title="Evasa", amount=999.0)
    deadline_service.complete(shared_db, local_db, evasa)

    stats = deadline_service.stats(shared_db)

    assert stats.overdue == 1
    assert stats.due_today == 1
    assert stats.due_in_7_days == 2  # oggi + fra cinque giorni
    assert stats.due_in_30_days == 3  # ... + fra venti giorni
    assert stats.open_total == 5
    assert stats.done_total == 1
    assert stats.amount_open == 600.0  # l'importo della scadenza evasa non conta
    assert {c.name: c.count for c in stats.by_category} == {"Fiscale": 2, "Senza categoria": 3}
