"""Vista mensile: come i promemoria si distribuiscono sulla griglia dei giorni."""

from __future__ import annotations

from datetime import date, time

from app.models import ReminderKind
from app.services import reminders as reminder_service


def _giorno(mese, giorno: date):
    return next(d for d in mese.days if d.date == giorno)


def test_la_griglia_copre_settimane_intere_da_lunedi(shared_db):
    """Agosto 2026 comincia di sabato: la griglia parte dal lunedì precedente."""
    mese = reminder_service.calendar_month(shared_db, 2026, 8)

    assert mese.grid_start == date(2026, 7, 27)  # lunedì
    assert mese.grid_end == date(2026, 9, 6)  # domenica
    assert len(mese.days) % 7 == 0
    assert mese.days[0].date.weekday() == 0
    assert mese.days[-1].date.weekday() == 6


def test_i_giorni_di_riempimento_sono_marcati(shared_db):
    mese = reminder_service.calendar_month(shared_db, 2026, 8)

    assert _giorno(mese, date(2026, 7, 30)).in_month is False
    assert _giorno(mese, date(2026, 8, 1)).in_month is True
    assert _giorno(mese, date(2026, 9, 2)).in_month is False


def test_ogni_promemoria_finisce_nel_suo_giorno(shared_db, make_reminder):
    oggi = date.today()
    riferimento = make_reminder(0, title="Oggi")
    domani = make_reminder(1, title="Domani")

    mese = reminder_service.calendar_month(shared_db, oggi.year, oggi.month)

    assert [r.title for r in _giorno(mese, riferimento.due_date).items] == ["Oggi"]
    assert [r.title for r in _giorno(mese, domani.due_date).items] == ["Domani"]


def test_dentro_il_giorno_gli_orari_vengono_prima(shared_db, make_reminder):
    """Chi ha un'ora si legge in ordine di ora; chi non ce l'ha sta in coda."""
    oggi = date.today()
    make_reminder(0, title="Senza orario")
    make_reminder(0, title="Pomeriggio", start_time=time(15, 0))
    make_reminder(0, title="Mattina", start_time=time(9, 30))

    mese = reminder_service.calendar_month(shared_db, oggi.year, oggi.month)

    assert [r.title for r in _giorno(mese, oggi).items] == ["Mattina", "Pomeriggio", "Senza orario"]


def test_i_giorni_di_riempimento_portano_i_loro_promemoria(shared_db, make_reminder):
    """Un promemoria del mese scorso visibile nella prima riga della griglia
    deve esserci: altrimenti la settimana a cavallo sembra vuota."""
    primo = date.today().replace(day=1)
    if primo.weekday() == 0:
        return  # mese che comincia di lunedì: nessun giorno di riempimento davanti

    giorno_prima = primo.fromordinal(primo.toordinal() - 1)
    atteso = make_reminder((giorno_prima - date.today()).days, title="Coda del mese scorso")

    mese = reminder_service.calendar_month(shared_db, primo.year, primo.month)
    cella = _giorno(mese, atteso.due_date)

    assert cella.in_month is False
    assert [r.title for r in cella.items] == ["Coda del mese scorso"]


def test_filtro_per_tipo(shared_db, make_reminder):
    oggi = date.today()
    make_reminder(0, title="Scadenza IVA", kind=ReminderKind.DEADLINE)
    make_reminder(0, title="Riunione", kind=ReminderKind.APPOINTMENT)

    mese = reminder_service.calendar_month(
        shared_db, oggi.year, oggi.month, kind=ReminderKind.APPOINTMENT
    )

    assert [r.title for r in _giorno(mese, oggi).items] == ["Riunione"]


def test_si_possono_escludere_i_promemoria_evasi(shared_db, local_db, make_reminder):
    oggi = date.today()
    make_reminder(0, title="Aperto")
    evaso = make_reminder(0, title="Evaso")
    reminder_service.complete(shared_db, local_db, evaso)

    con_evasi = reminder_service.calendar_month(shared_db, oggi.year, oggi.month)
    senza = reminder_service.calendar_month(shared_db, oggi.year, oggi.month, include_done=False)

    assert {r.title for r in _giorno(con_evasi, oggi).items} == {"Aperto", "Evaso"}
    assert [r.title for r in _giorno(senza, oggi).items] == ["Aperto"]


# ------------------------------------------------------------------- endpoint


def test_endpoint_calendario(client, make_reminder):
    oggi = date.today()
    make_reminder(0, title="Riunione", start_time=time(9, 30), kind=ReminderKind.APPOINTMENT)

    risposta = client.get("/api/reminders/calendar", params={"year": oggi.year, "month": oggi.month})

    assert risposta.status_code == 200
    corpo = risposta.json()
    assert (corpo["year"], corpo["month"]) == (oggi.year, oggi.month)

    cella = next(d for d in corpo["days"] if d["date"] == oggi.isoformat())
    assert cella["items"][0]["title"] == "Riunione"
    assert cella["items"][0]["start_time"] == "09:30:00"
    assert cella["items"][0]["kind"] == "appointment"


def test_endpoint_calendario_rifiuta_un_mese_inesistente(client):
    assert client.get("/api/reminders/calendar", params={"year": 2026, "month": 13}).status_code == 422
