"""Tipo e orario: come cambiano il testo degli avvisi e la scrittura via API."""

from __future__ import annotations

from datetime import time

import pytest

from app.models import ReminderKind
from app.services import alerts


def _avviso(local_db):
    from sqlalchemy import select

    from app.models import Notification

    return local_db.scalars(select(Notification).order_by(Notification.scheduled_for)).first()


def test_un_appuntamento_non_scade_ma_e_fissato(local_db, make_reminder, app_settings):
    """«La riunione scade domani» sarebbe italiano sbagliato, prima ancora che
    un dettaglio estetico."""
    reminder = make_reminder(1, title="Riunione", kind=ReminderKind.APPOINTMENT, alert_offsets=[1])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    avviso = _avviso(local_db)
    assert avviso.title == "Domani: Riunione"
    assert "è domani" in avviso.body
    assert "scade" not in avviso.body.lower()


def test_una_scadenza_scade(local_db, make_reminder, app_settings):
    reminder = make_reminder(1, title="IVA", kind=ReminderKind.DEADLINE, alert_offsets=[1])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    avviso = _avviso(local_db)
    assert avviso.title == "Scade domani: IVA"
    assert "scade domani" in avviso.body


def test_l_orario_compare_nel_testo_dell_avviso(local_db, make_reminder, app_settings):
    reminder = make_reminder(
        1, title="Riunione", kind=ReminderKind.APPOINTMENT, start_time=time(9, 30), alert_offsets=[1]
    )
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    assert "alle 09:30" in _avviso(local_db).body


def test_senza_orario_non_si_inventa_un_ora(local_db, make_reminder, app_settings):
    reminder = make_reminder(1, title="IVA", alert_offsets=[1])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    assert "alle" not in _avviso(local_db).body


def test_un_appuntamento_passato_non_e_una_scadenza_superata(local_db, make_reminder, app_settings):
    reminder = make_reminder(-2, title="Riunione", kind=ReminderKind.APPOINTMENT, alert_offsets=[0])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    avviso = _avviso(local_db)
    assert "Appuntamento passato" in avviso.title
    assert "era 2 giorni fa" in avviso.body


def test_una_nota_generica_non_scade(local_db, make_reminder, app_settings):
    """«La partita di calcetto scade oggi» non si può leggere: il verbo delle
    scadenze vale solo per le scadenze, non per tutto ciò che non è un
    appuntamento."""
    reminder = make_reminder(0, title="Partita di calcetto", kind=ReminderKind.OTHER, alert_offsets=[0])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    avviso = _avviso(local_db)
    assert avviso.title == "Oggi: Partita di calcetto"
    assert "è oggi" in avviso.body
    assert "scade" not in avviso.body.lower()


def test_una_nota_generica_passata(local_db, make_reminder, app_settings):
    reminder = make_reminder(-2, title="Nota", kind=ReminderKind.OTHER, alert_offsets=[0])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    avviso = _avviso(local_db)
    assert avviso.title == "Già passato: Nota"
    assert "era 2 giorni fa" in avviso.body
    assert "scaduta" not in avviso.body.lower()


@pytest.mark.parametrize(
    ("kind", "atteso"),
    [
        (ReminderKind.DEADLINE, "Scade domani: X"),
        (ReminderKind.APPOINTMENT, "Domani: X"),
        (ReminderKind.OTHER, "Domani: X"),
    ],
)
def test_titolo_di_domani_per_ogni_tipo(local_db, make_reminder, app_settings, kind, atteso):
    """Le tre diciture a confronto sullo stesso giorno: solo la scadenza scade."""
    reminder = make_reminder(1, title="X", kind=kind, alert_offsets=[1])
    alerts.sync_reminder_notifications(local_db, reminder, app_settings)

    assert _avviso(local_db).title == atteso


# ------------------------------------------------------------------- API


def test_creare_un_appuntamento_con_orario(client):
    risposta = client.post(
        "/api/reminders",
        json={
            "title": "Riunione commercialista",
            "due_date": "2026-09-20",
            "start_time": "09:30",
            "kind": "appointment",
        },
    )

    assert risposta.status_code == 201, risposta.text
    corpo = risposta.json()
    assert corpo["kind"] == "appointment"
    assert corpo["start_time"] == "09:30:00"


def test_il_tipo_predefinito_resta_la_scadenza(client):
    """I promemoria creati prima del tipo, e chi non lo passa, sono scadenze."""
    risposta = client.post("/api/reminders", json={"title": "IVA", "due_date": "2026-09-20"})

    assert risposta.json()["kind"] == "deadline"
    assert risposta.json()["start_time"] is None


def test_un_orario_svuotato_dal_form_azzera_il_campo(client):
    """Un <input type="time"> svuotato manda "" e non null: se arrivasse fino
    al database la modifica fallirebbe con un 422."""
    creato = client.post(
        "/api/reminders",
        json={"title": "Riunione", "due_date": "2026-09-20", "start_time": "09:30"},
    ).json()

    risposta = client.patch(f"/api/reminders/{creato['id']}", json={"start_time": ""})

    assert risposta.status_code == 200, risposta.text
    assert risposta.json()["start_time"] is None


def test_filtro_per_tipo_nell_elenco(client, make_reminder):
    make_reminder(5, title="Scadenza IVA", kind=ReminderKind.DEADLINE)
    make_reminder(5, title="Riunione", kind=ReminderKind.APPOINTMENT)
    make_reminder(5, title="Nota varia", kind=ReminderKind.OTHER)

    risposta = client.get("/api/reminders", params={"kind": "appointment"})

    assert [r["title"] for r in risposta.json()["items"]] == ["Riunione"]


def test_a_parita_di_giorno_ordina_per_orario(client, make_reminder):
    make_reminder(5, title="Senza orario")
    make_reminder(5, title="Pomeriggio", start_time=time(15, 0))
    make_reminder(5, title="Mattina", start_time=time(9, 30))

    risposta = client.get("/api/reminders", params={"sort": "due_date"})

    assert [r["title"] for r in risposta.json()["items"]] == ["Mattina", "Pomeriggio", "Senza orario"]


def test_la_ricorrenza_conserva_tipo_e_orario(shared_db, local_db, make_reminder):
    from app.models import Recurrence
    from app.services import reminders as reminder_service

    reminder = make_reminder(
        5,
        title="Riunione mensile",
        kind=ReminderKind.APPOINTMENT,
        start_time=time(9, 30),
        recurrence=Recurrence.MONTHLY,
    )

    _, successiva = reminder_service.complete(shared_db, local_db, reminder)

    assert successiva.kind == ReminderKind.APPOINTMENT
    assert successiva.start_time == time(9, 30)


def test_le_statistiche_contano_i_tipi(shared_db, make_reminder):
    from app.services import reminders as reminder_service

    make_reminder(5, title="IVA", kind=ReminderKind.DEADLINE)
    make_reminder(5, title="Riunione", kind=ReminderKind.APPOINTMENT)
    make_reminder(5, title="Altra riunione", kind=ReminderKind.APPOINTMENT)

    stats = reminder_service.stats(shared_db)

    assert {k.kind: k.count for k in stats.by_kind} == {
        ReminderKind.DEADLINE: 1,
        ReminderKind.APPOINTMENT: 2,
        ReminderKind.OTHER: 0,
    }
