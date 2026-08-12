"""Consegna degli avvisi: cosa parte, cosa viene annullato, cosa non riparte."""

from __future__ import annotations

from sqlalchemy import select

from app.models import DeadlineStatus, Notification, NotificationStatus
from app.services import dispatcher, settings_service


def _prepara(shared_db, app_settings):
    """Avvisi già dovuti: l'orario di invio è mezzanotte, quindi oggi è passato."""
    app_settings.daily_send_time = "00:00"
    app_settings.channel_inapp = True
    app_settings.channel_push = False
    app_settings.channel_email = False
    settings_service.save_settings(shared_db, app_settings)


def test_un_avviso_dovuto_viene_consegnato(shared_db, local_db, make_deadline, app_settings):
    _prepara(shared_db, app_settings)
    make_deadline(-1, alert_offsets=[0])

    esito = dispatcher.run_cycle(shared_db, local_db)

    assert esito["sent"] >= 1
    consegnate = local_db.scalars(
        select(Notification).where(Notification.status == NotificationStatus.SENT)
    ).all()
    assert consegnate
    assert all(n.sent_at is not None for n in consegnate)
    assert all(n.channel_results["inapp"]["ok"] for n in consegnate)


def test_un_avviso_non_viene_consegnato_due_volte(shared_db, local_db, make_deadline, app_settings):
    _prepara(shared_db, app_settings)
    make_deadline(-1, alert_offsets=[0])

    primo = dispatcher.run_cycle(shared_db, local_db)
    secondo = dispatcher.run_cycle(shared_db, local_db)

    assert primo["sent"] >= 1
    assert secondo["sent"] == 0


def test_scadenza_evasa_altrove_annulla_l_avviso(shared_db, local_db, make_deadline, app_settings):
    """La scadenza viene chiusa da un'altra postazione dopo che l'avviso è
    stato generato: non deve più essere consegnato."""
    _prepara(shared_db, app_settings)
    deadline = make_deadline(-1, alert_offsets=[0])

    from app.services import alerts

    alerts.sync_deadline_notifications(local_db, deadline, app_settings)
    assert local_db.scalars(select(Notification)).all()

    deadline.status = DeadlineStatus.DONE
    shared_db.commit()

    esito = dispatcher.dispatch_due(shared_db, local_db)

    assert esito["sent"] == 0
    assert esito["obsolete"] >= 1

    # I solleciti futuri restano pendenti finché lo scheduler non li ripulisce;
    # quello che contava è che nessuno sia partito.
    stati = {n.status for n in local_db.scalars(select(Notification)).all()}
    assert NotificationStatus.SENT not in stati
    assert NotificationStatus.CANCELLED in stati


def test_un_canale_in_errore_non_blocca_gli_altri(shared_db, local_db, make_deadline, app_settings, monkeypatch):
    _prepara(shared_db, app_settings)
    make_deadline(-1, alert_offsets=[0])

    class CanaleRotto:
        name = "rotto"

        def enabled(self, _app_settings):
            return True

        def send(self, *_args, **_kwargs):
            raise RuntimeError("server irraggiungibile")

    from app.services import notifiers

    monkeypatch.setattr(
        dispatcher, "NOTIFIERS", [CanaleRotto(), notifiers.InAppNotifier()], raising=True
    )

    esito = dispatcher.run_cycle(shared_db, local_db)

    assert esito["sent"] >= 1
    consegnata = local_db.scalars(
        select(Notification).where(Notification.status == NotificationStatus.SENT)
    ).first()
    assert consegnata.channel_results["rotto"]["ok"] is False
    assert "irraggiungibile" in consegnata.channel_results["rotto"]["detail"]
    assert consegnata.channel_results["inapp"]["ok"] is True
