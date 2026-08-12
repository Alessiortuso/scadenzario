"""Motore degli avvisi: quali notifiche nascono, quando, e quante volte.

È la parte del sistema in cui un errore non si vede — non lancia eccezioni,
manda semplicemente un avviso di troppo o, peggio, nessuno.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone

from sqlalchemy import select

from app.config import settings as env_settings
from app.models import Category, DeadlineStatus, Notification, NotificationStatus
from app.services import alerts


def _pending(local_db) -> list[Notification]:
    return list(
        local_db.scalars(select(Notification).order_by(Notification.scheduled_for)).all()
    )


def _alert_days(local_db) -> list[date]:
    """I giorni in cui gli avvisi partiranno, nel fuso dell'utente.

    `scheduled_for` torna da SQLite in UTC ma senza fuso: va riattaccato prima
    di convertire, altrimenti un avviso di primo mattino finisce nel giorno
    sbagliato.
    """
    return [
        n.scheduled_for.replace(tzinfo=timezone.utc).astimezone(env_settings.tz).date()
        for n in _pending(local_db)
    ]


# ------------------------------------------------------------------- preavvisi


def test_offsets_della_scadenza_hanno_la_precedenza(shared_db, make_deadline, app_settings):
    categoria = Category(name="Fiscale", alert_offsets=[10, 5])
    shared_db.add(categoria)
    shared_db.commit()

    deadline = make_deadline(60, alert_offsets=[7, 2], category=categoria)
    assert alerts.effective_offsets(deadline, app_settings) == [7, 2]


def test_senza_offsets_propri_si_eredita_dalla_categoria(shared_db, make_deadline, app_settings):
    categoria = Category(name="Contratti", alert_offsets=[10, 5])
    shared_db.add(categoria)
    shared_db.commit()

    deadline = make_deadline(60, category=categoria)
    assert alerts.effective_offsets(deadline, app_settings) == [10, 5]


def test_senza_categoria_si_usano_gli_offsets_globali(make_deadline, app_settings):
    deadline = make_deadline(60)
    assert alerts.effective_offsets(deadline, app_settings) == [30, 15, 7, 3, 1, 0]


def test_offsets_ripuliti_da_duplicati_e_negativi(make_deadline, app_settings):
    deadline = make_deadline(60, alert_offsets=[7, 7, -3, 1])
    assert alerts.effective_offsets(deadline, app_settings) == [7, 1]


def test_un_preavviso_per_ogni_offset_futuro(local_db, make_deadline, app_settings):
    """Scadenza fra 60 giorni: tutti i preavvisi sono ancora davanti."""
    deadline = make_deadline(60, alert_offsets=[30, 7, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    oggi = date.today()
    assert _alert_days(local_db)[:3] == [oggi + timedelta(days=30), oggi + timedelta(days=53), oggi + timedelta(days=60)]


def test_preavvisi_gia_passati_non_vengono_sparati_tutti_insieme(local_db, make_deadline, app_settings):
    """Scadenza inserita oggi a 10 giorni: i preavvisi a 30 e 15 sono nel
    passato e non devono generare avvisi retroattivi."""
    deadline = make_deadline(10, alert_offsets=[30, 15, 7, 3, 1, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    oggi = date.today()
    assert all(giorno >= oggi for giorno in _alert_days(local_db))


def test_orario_di_invio_rispetta_il_fuso_configurato(local_db, make_deadline, app_settings):
    """L'orario è espresso nel fuso dell'utente e memorizzato in UTC.

    SQLite non conserva l'offset: il valore riletto è UTC senza fuso, ed è
    l'API a riattaccarlo (vedi `test_api_notifications`).
    """
    app_settings.daily_send_time = "08:30"
    deadline = make_deadline(60, alert_offsets=[30])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    salvato = _pending(local_db)[0].scheduled_for.replace(tzinfo=timezone.utc)
    locale = salvato.astimezone(env_settings.tz)
    assert (locale.hour, locale.minute) == (8, 30)


# --------------------------------------------------------------------- recupero


def test_scadenza_gia_scaduta_genera_un_avviso_immediato(local_db, make_deadline, app_settings):
    """Inserita oggi ma scaduta cinque giorni fa: senza recupero non avrebbe
    nessun avviso, perché tutte le date di preavviso sono nel passato."""
    deadline = make_deadline(-5, alert_offsets=[30, 7, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    oggi = date.today()
    subito = [n for n in _pending(local_db) if n.scheduled_for.astimezone(env_settings.tz).date() == oggi]
    assert len(subito) == 1
    assert subito[0].severity == "danger"
    assert "superata" in subito[0].title.lower()


def test_nessun_recupero_se_un_preavviso_cade_gia_oggi(local_db, make_deadline, app_settings):
    """A tre giorni dalla scadenza l'offset 3 copre già oggi: aggiungere un
    avviso di recupero significherebbe mandarne due identici."""
    deadline = make_deadline(3, alert_offsets=[30, 3, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    oggi = date.today()
    assert sum(1 for giorno in _alert_days(local_db) if giorno == oggi) == 1


def test_nessun_recupero_fuori_dalla_finestra_di_preavviso(local_db, make_deadline, app_settings):
    """Scadenza lontana: nessun avviso deve partire oggi."""
    deadline = make_deadline(60, alert_offsets=[30, 7])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    assert date.today() not in _alert_days(local_db)


# --------------------------------------------------------------------- solleciti


def test_solleciti_dopo_la_scadenza(local_db, make_deadline, app_settings):
    app_settings.overdue_repeat_days = 3
    app_settings.overdue_max_reminders = 4
    deadline = make_deadline(30, alert_offsets=[7])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    dopo = [g for g in _alert_days(local_db) if g > deadline.due_date]
    assert dopo == [deadline.due_date + timedelta(days=n * 3) for n in range(1, 5)]


def test_solleciti_disattivabili(local_db, make_deadline, app_settings):
    app_settings.overdue_repeat_days = 0
    deadline = make_deadline(30, alert_offsets=[7])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    assert all(g <= deadline.due_date for g in _alert_days(local_db))


# ----------------------------------------------------------------- idempotenza


def test_risincronizzare_non_duplica_gli_avvisi(local_db, make_deadline, app_settings):
    deadline = make_deadline(60, alert_offsets=[30, 7, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)
    prima = {n.dedupe_key for n in _pending(local_db)}

    alerts.sync_deadline_notifications(local_db, deadline, app_settings)
    dopo = _pending(local_db)

    assert {n.dedupe_key for n in dopo} == prima
    assert len(dopo) == len(prima)


def test_un_avviso_gia_inviato_non_viene_rigenerato(local_db, make_deadline, app_settings):
    deadline = make_deadline(60, alert_offsets=[30, 7, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    inviato = _pending(local_db)[0]
    inviato.status = NotificationStatus.SENT
    chiave = inviato.dedupe_key
    local_db.commit()

    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    con_quella_chiave = [n for n in _pending(local_db) if n.dedupe_key == chiave]
    assert len(con_quella_chiave) == 1
    assert con_quella_chiave[0].status == NotificationStatus.SENT


def test_spostare_la_data_ricalcola_i_preavvisi_pendenti(shared_db, local_db, make_deadline, app_settings):
    app_settings.overdue_repeat_days = 0  # solo i preavvisi, per leggere meglio
    deadline = make_deadline(60, alert_offsets=[30])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)
    assert _alert_days(local_db) == [date.today() + timedelta(days=30)]

    deadline.due_date = date.today() + timedelta(days=90)
    shared_db.commit()
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    assert _alert_days(local_db) == [date.today() + timedelta(days=60)]


def test_scadenza_evasa_non_ha_piu_avvisi_pendenti(shared_db, local_db, make_deadline, app_settings):
    deadline = make_deadline(60, alert_offsets=[30, 7])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)
    assert _pending(local_db)

    deadline.status = DeadlineStatus.DONE
    shared_db.commit()
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    assert _pending(local_db) == []


# ------------------------------------------------------------------- sync_all


def test_sync_all_copre_solo_le_scadenze_aperte(shared_db, local_db, make_deadline):
    aperta = make_deadline(60, title="Aperta", alert_offsets=[30])
    chiusa = make_deadline(60, title="Chiusa", alert_offsets=[30])
    chiusa.status = DeadlineStatus.DONE
    shared_db.commit()

    alerts.sync_all(shared_db, local_db)

    assert {n.deadline_id for n in _pending(local_db)} == {aperta.id}


def test_sync_all_rimuove_avvisi_di_scadenze_sparite(shared_db, local_db, make_deadline, app_settings):
    """Una scadenza evasa o eliminata da un'altra postazione non deve lasciare
    avvisi pendenti su questa."""
    deadline = make_deadline(60, alert_offsets=[30])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    shared_db.delete(deadline)
    shared_db.commit()
    alerts.sync_all(shared_db, local_db)

    assert _pending(local_db) == []


def test_due_notifications_solo_quelle_arrivate_a_scadenza(local_db, make_deadline, app_settings):
    """Il dispatcher deve prendere solo gli avvisi la cui ora è passata."""
    # Mezzanotte: l'avviso di oggi risulta dovuto a qualunque ora giri la suite.
    app_settings.daily_send_time = "00:00"
    deadline = make_deadline(-5, alert_offsets=[30, 7, 0])
    alerts.sync_deadline_notifications(local_db, deadline, app_settings)

    dovuti = alerts.due_notifications(local_db)
    totali = _pending(local_db)

    assert dovuti, "l'avviso di recupero di oggi dovrebbe essere già dovuto"
    assert len(dovuti) < len(totali), "i solleciti futuri non devono essere consegnati adesso"
