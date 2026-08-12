"""Endpoint delle notifiche, con attenzione a cosa succede quando il database
condiviso non risponde: è il caso che decide se un avviso arriva o si perde."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import notifications as notifications_api
from app.db import get_db, get_local_db
from app.main import app
from app.models import DeadlineStatus, Notification, NotificationStatus


@pytest.fixture
def client(shared_db, local_db, monkeypatch):
    """Client HTTP con i due database di test al posto di quelli reali.

    `to-display` non passa dalle dipendenze per il database condiviso — lo apre
    da sé, proprio per non rispondere 503 quando manca — quindi va sostituita
    anche la sessione che usa.
    """
    app.dependency_overrides[get_db] = lambda: shared_db
    app.dependency_overrides[get_local_db] = lambda: local_db
    monkeypatch.setattr(notifications_api, "SharedSession", lambda: shared_db)
    monkeypatch.setattr(notifications_api, "is_shared_configured", lambda: True)

    # Senza `with`: il lifespan non parte, quindi i test non toccano il
    # database reale della postazione né il PostgreSQL condiviso.
    yield TestClient(app)

    app.dependency_overrides.clear()


def _avviso_consegnato(local_db, deadline_id: int, *, chiave: str = "k1") -> Notification:
    notifica = Notification(
        deadline_id=deadline_id,
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


def test_to_display_restituisce_gli_avvisi_di_scadenze_aperte(client, local_db, make_deadline):
    deadline = make_deadline(0)
    _avviso_consegnato(local_db, deadline.id)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["deadline_id"] for n in risposta.json()] == [deadline.id]


def test_to_display_annulla_gli_avvisi_di_scadenze_gia_evase(client, shared_db, local_db, make_deadline):
    deadline = make_deadline(0)
    notifica = _avviso_consegnato(local_db, deadline.id)
    deadline.status = DeadlineStatus.DONE
    shared_db.commit()

    risposta = client.get("/api/notifications/to-display")

    assert risposta.json() == []
    local_db.refresh(notifica)
    assert notifica.status == NotificationStatus.CANCELLED
    assert notifica.displayed_at is not None


def test_to_display_mostra_comunque_se_il_condiviso_non_risponde(
    client, local_db, make_deadline, monkeypatch
):
    """Neon in standby o rete assente: un promemoria di troppo si ignora, uno
    mancato fa perdere una scadenza."""
    deadline = make_deadline(0)
    notifica = _avviso_consegnato(local_db, deadline.id)

    monkeypatch.setattr(notifications_api, "is_shared_configured", lambda: False)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["deadline_id"] for n in risposta.json()] == [deadline.id]
    local_db.refresh(notifica)
    assert notifica.status == NotificationStatus.SENT, "l'avviso non va annullato al buio"


def test_to_display_sopravvive_a_un_errore_del_database_condiviso(
    client, local_db, make_deadline, monkeypatch
):
    deadline = make_deadline(0)
    _avviso_consegnato(local_db, deadline.id)

    from sqlalchemy.exc import OperationalError

    class SessioneRotta:
        def scalars(self, *_args, **_kwargs):
            raise OperationalError("select 1", {}, Exception("server chiuso"))

        def close(self):
            pass

    monkeypatch.setattr(notifications_api, "SharedSession", SessioneRotta)

    risposta = client.get("/api/notifications/to-display")

    assert risposta.status_code == 200
    assert [n["deadline_id"] for n in risposta.json()] == [deadline.id]


def test_marcare_mostrato_non_ripresenta_il_toast(client, local_db, make_deadline):
    deadline = make_deadline(0)
    notifica = _avviso_consegnato(local_db, deadline.id)

    assert client.post(f"/api/notifications/{notifica.id}/displayed").status_code == 204
    assert client.get("/api/notifications/to-display").json() == []


def test_gli_orari_arrivano_al_browser_con_il_fuso(client, local_db, make_deadline):
    """Senza offset il browser li interpreta come ora locale e mostra un orario
    sbagliato: `scheduled_for` deve essere esplicitamente in UTC."""
    deadline = make_deadline(0)
    _avviso_consegnato(local_db, deadline.id)

    quando = client.get("/api/notifications").json()[0]["scheduled_for"]

    assert quando.endswith("Z") or "+00:00" in quando, quando
    assert datetime.fromisoformat(quando.replace("Z", "+00:00")).tzinfo is not None


def test_eliminare_una_scadenza_ripulisce_gli_avvisi_locali(client, local_db, make_deadline):
    """Altrimenti la campanella rimanderebbe a una scadenza che non esiste."""
    deadline = make_deadline(30, alert_offsets=[7])
    _avviso_consegnato(local_db, deadline.id)

    assert client.delete(f"/api/deadlines/{deadline.id}").status_code == 204

    assert local_db.scalars(select(Notification)).all() == []
