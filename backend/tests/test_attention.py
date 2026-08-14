"""Segnalazione insistente: cosa la accende e cosa la spegne.

L'avviso che si ignora non deve sparire nel nulla. Finché un promemoria è
imminente e nessuno l'ha guardato, la barra delle applicazioni continua a
segnalarlo — e questi test descrivono esattamente quando.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Notification, NotificationStatus


def _consegnato(local_db, *, reminder_id: int, offset: int, chiave: str, titolo: str = "Avviso"):
    """Un avviso già consegnato e non ancora letto."""
    notifica = Notification(
        reminder_id=reminder_id,
        dedupe_key=chiave,
        offset_days=offset,
        title=titolo,
        body="corpo",
        severity="warning",
        scheduled_for=datetime.now(timezone.utc) - timedelta(hours=1),
        status=NotificationStatus.SENT,
        sent_at=datetime.now(timezone.utc),
    )
    local_db.add(notifica)
    local_db.commit()
    return notifica


@pytest.fixture
def soglia(client, shared_db, app_settings):
    """Imposta la soglia di insistenza sul database condiviso dei test."""
    from app.services import settings_service

    def _imposta(giorni: int) -> None:
        app_settings.insistent_alert_days = giorni
        settings_service.save_settings(shared_db, app_settings)

    return _imposta


def test_un_avviso_imminente_accende_la_segnalazione(client, local_db, soglia):
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=1, chiave="k1", titolo="Scade domani: IVA")

    stato = client.get("/api/notifications/attention").json()

    assert stato["count"] == 1
    assert stato["days"] == 3
    assert stato["title"] == "Scade domani: IVA"


def test_un_avviso_lontano_non_la_accende(client, local_db, soglia):
    """Un preavviso a trenta giorni è un promemoria, non un'urgenza."""
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=30, chiave="k1")

    assert client.get("/api/notifications/attention").json()["count"] == 0


def test_un_sollecito_di_uno_gia_scaduto_la_accende(client, local_db, soglia):
    """Gli offset negativi sono i giorni *dopo* la data: più urgenti, non meno."""
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=-6, chiave="k1")

    assert client.get("/api/notifications/attention").json()["count"] == 1


def test_un_avviso_gia_letto_non_la_accende(client, local_db, soglia):
    soglia(3)
    notifica = _consegnato(local_db, reminder_id=1, offset=0, chiave="k1")
    notifica.read_at = datetime.now(timezone.utc)
    local_db.commit()

    assert client.get("/api/notifications/attention").json()["count"] == 0


def test_a_soglia_zero_la_segnalazione_e_disattivata(client, local_db, soglia):
    """Chi non la vuole mette 0 e l'applicazione si comporta come prima."""
    soglia(0)
    _consegnato(local_db, reminder_id=1, offset=0, chiave="k1")

    stato = client.get("/api/notifications/attention").json()
    assert stato["count"] == 0
    assert stato["days"] == 0


def test_guardare_spegne_la_segnalazione(client, local_db, soglia):
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=0, chiave="k1")
    _consegnato(local_db, reminder_id=2, offset=1, chiave="k2")

    dopo = client.post("/api/notifications/attention/seen").json()

    assert dopo["count"] == 0
    assert client.get("/api/notifications/attention").json()["count"] == 0


def test_aprire_un_promemoria_spegne_solo_il_suo(client, local_db, soglia):
    """Aprire una scheda non vuol dire aver guardato anche le altre."""
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=0, chiave="k1")
    _consegnato(local_db, reminder_id=2, offset=1, chiave="k2")

    dopo = client.post("/api/notifications/attention/seen", params={"reminder_id": 1}).json()

    assert dopo["count"] == 1
    assert dopo["title"] is not None


def test_guardare_non_marca_letti_gli_avvisi_lontani(client, local_db, soglia):
    """Aprire l'elenco non è "ho letto tutto": un preavviso a trenta giorni
    resta da leggere, e la campanella deve continuare a dirlo."""
    soglia(3)
    _consegnato(local_db, reminder_id=1, offset=0, chiave="vicino")
    _consegnato(local_db, reminder_id=2, offset=30, chiave="lontano")

    client.post("/api/notifications/attention/seen")

    assert client.get("/api/notifications/counts").json()["unread"] == 1
