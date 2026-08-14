"""Endpoint delle notifiche, con attenzione a cosa succede quando il database
condiviso non risponde: è il caso che decide se un avviso arriva o si perde."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api import notifications as notifications_api
from app.models import ReminderStatus, Notification, NotificationStatus


def _avviso_consegnato(local_db, reminder_id: int, *, chiave: str = "k1") -> Notification:
    notifica = Notification(
        reminder_id=reminder_id,
        dedupe_key=chiave,
        offset_days=0,
        title="Scade oggi: prova",
        body="corpo",
        severity="critical",
        scheduled_for=datetime.now(timezone.utc) - timedelta(hours=1),
        status=NotificationStatus.SENT,
        sent_at=datetime.now(timezone.utc),
    )
    local_db.add(notifica)
    local_db.commit()
    return notifica


def test_to_display_restituisce_gli_avvisi_di_scadenze_aperte(client, local_db, make_reminder):
    reminder = make_reminder(0)
    _avviso_consegnato(local_db, reminder.id)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["reminder_id"] for n in risposta.json()] == [reminder.id]


def test_to_display_annulla_gli_avvisi_di_scadenze_gia_evase(client, shared_db, local_db, make_reminder):
    reminder = make_reminder(0)
    notifica = _avviso_consegnato(local_db, reminder.id)
    reminder.status = ReminderStatus.DONE
    shared_db.commit()

    risposta = client.get("/api/notifications/to-display")

    assert risposta.json() == []
    local_db.refresh(notifica)
    assert notifica.status == NotificationStatus.CANCELLED
    assert notifica.displayed_at is not None


def test_to_display_mostra_comunque_se_il_condiviso_non_risponde(
    client, local_db, make_reminder, monkeypatch
):
    """Neon in standby o rete assente: un promemoria di troppo si ignora, uno
    mancato fa perdere una scadenza."""
    reminder = make_reminder(0)
    notifica = _avviso_consegnato(local_db, reminder.id)

    monkeypatch.setattr(notifications_api, "is_shared_configured", lambda: False)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["reminder_id"] for n in risposta.json()] == [reminder.id]
    local_db.refresh(notifica)
    assert notifica.status == NotificationStatus.SENT, "l'avviso non va annullato al buio"


def test_to_display_sopravvive_a_un_errore_del_database_condiviso(
    client, local_db, make_reminder, monkeypatch
):
    reminder = make_reminder(0)
    _avviso_consegnato(local_db, reminder.id)

    from sqlalchemy.exc import OperationalError

    class SessioneRotta:
        def scalars(self, *_args, **_kwargs):
            raise OperationalError("select 1", {}, Exception("server chiuso"))

        def close(self):
            pass

    monkeypatch.setattr(notifications_api, "SharedSession", SessioneRotta)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["reminder_id"] for n in risposta.json()] == [reminder.id]


def test_marcare_mostrato_non_ripresenta_il_toast(client, local_db, make_reminder):
    reminder = make_reminder(0)
    notifica = _avviso_consegnato(local_db, reminder.id)

    assert client.post(f"/api/notifications/{notifica.id}/displayed").status_code == 204
    assert client.get("/api/notifications/to-display").json() == []


def test_gli_orari_arrivano_al_browser_con_il_fuso(client, local_db, make_reminder):
    """Senza offset il browser li interpreta come ora locale e mostra un orario
    sbagliato: `scheduled_for` deve essere esplicitamente in UTC."""
    reminder = make_reminder(0)
    _avviso_consegnato(local_db, reminder.id)

    quando = client.get("/api/notifications").json()[0]["scheduled_for"]

    assert quando.endswith("Z") or "+00:00" in quando, quando
    assert datetime.fromisoformat(quando.replace("Z", "+00:00")).tzinfo is not None


def test_eliminare_una_scadenza_ripulisce_gli_avvisi_locali(client, local_db, make_reminder):
    """Altrimenti la campanella rimanderebbe a una scadenza che non esiste."""
    reminder = make_reminder(30, alert_offsets=[7])
    _avviso_consegnato(local_db, reminder.id)

    assert client.delete(f"/api/reminders/{reminder.id}").status_code == 204

    assert local_db.scalars(select(Notification)).all() == []
