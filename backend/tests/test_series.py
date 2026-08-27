"""Ricorrenze con una fine: le occorrenze esistono tutte, con i loro importi.

La differenza che conta rispetto alla ricorrenza aperta: qui le occorrenze
nascono insieme al salvataggio, perché è l'unico modo per dire fin da subito
quanto si paga a marzo e per vederle tutte sul calendario.
"""

from __future__ import annotations

from datetime import date

from app.models import Recurrence, RecurrenceUnit
from app.services import reminders as reminder_service


# ------------------------------------------------------------------ le date


def test_le_rate_restano_ancorate_al_giorno_di_partenza():
    """Chi paga il 31 vuole il 31, e febbraio non deve spostare il resto.

    Sommando un mese al risultato precedente le rate scivolerebbero al 28 per
    sempre dopo il primo febbraio incontrato.
    """
    date_serie = reminder_service.occurrence_dates(
        date(2026, 1, 31), Recurrence.MONTHLY, date(2026, 6, 30)
    )

    assert date_serie == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
    ]


def test_la_prima_occorrenza_e_quella_inserita():
    """Dodici rate vuol dire dodici promemoria, non uno più dodici."""
    date_serie = reminder_service.occurrence_dates(
        date(2026, 1, 15), Recurrence.MONTHLY, date(2026, 12, 31)
    )

    assert date_serie[0] == date(2026, 1, 15)
    assert len(date_serie) == 12


def test_senza_data_di_fine_resta_una_sola():
    """La ricorrenza aperta continua a generarsi una alla volta, come prima."""
    assert reminder_service.occurrence_dates(date(2026, 1, 15), Recurrence.MONTHLY, None) == [
        date(2026, 1, 15)
    ]


def test_senza_ricorrenza_la_data_di_fine_non_conta():
    assert reminder_service.occurrence_dates(
        date(2026, 1, 15), Recurrence.NONE, date(2030, 1, 1)
    ) == [date(2026, 1, 15)]


def test_una_fine_prima_dell_inizio_non_moltiplica_nulla():
    assert reminder_service.occurrence_dates(
        date(2026, 6, 1), Recurrence.MONTHLY, date(2026, 1, 1)
    ) == [date(2026, 6, 1)]


def test_c_e_un_tetto_alle_occorrenze():
    """Una data di fine sbagliata non deve riempire il calendario di migliaia
    di righe difficili da togliere."""
    date_serie = reminder_service.occurrence_dates(
        date(2026, 1, 1), Recurrence.MONTHLY, date(2999, 1, 1)
    )

    assert len(date_serie) == reminder_service.MAX_OCCORRENZE


# ---------------------------------------------------------------- creazione


def test_creare_una_serie_con_importi_diversi(client):
    risposta = client.post(
        "/api/reminders",
        json={
            "title": "Rata finanziamento",
            "due_date": "2026-01-31",
            "recurrence": "monthly",
            "recurrence_until": "2026-03-31",
            "amount": 100.0,
            "occurrences": [
                {"due_date": "2026-02-28", "amount": 250.5},
                {"due_date": "2026-03-31", "amount": 90.0},
            ],
        },
    )

    assert risposta.status_code == 201, risposta.text

    elenco = client.get("/api/reminders", params={"q": "Rata", "sort": "due_date"}).json()["items"]
    assert [(r["due_date"], r["amount"]) for r in elenco] == [
        ("2026-01-31", 100.0),  # non elencata: tiene l'importo generale
        ("2026-02-28", 250.5),
        ("2026-03-31", 90.0),
    ]


def test_le_occorrenze_di_una_serie_sono_legate(client):
    creato = client.post(
        "/api/reminders",
        json={
            "title": "Rata",
            "due_date": "2026-01-15",
            "recurrence": "monthly",
            "recurrence_until": "2026-04-15",
        },
    ).json()

    elenco = client.get("/api/reminders", params={"q": "Rata"}).json()["items"]
    serie = {r["series_id"] for r in elenco}

    assert len(elenco) == 4
    assert len(serie) == 1 and creato["series_id"] is not None


def test_una_ricorrenza_aperta_non_crea_una_serie(client):
    creato = client.post(
        "/api/reminders",
        json={"title": "Perpetua", "due_date": "2026-01-15", "recurrence": "monthly"},
    ).json()

    assert creato["series_id"] is None
    assert client.get("/api/reminders", params={"q": "Perpetua"}).json()["total"] == 1


def test_la_posizione_nella_serie(client):
    client.post(
        "/api/reminders",
        json={
            "title": "Rata",
            "due_date": "2026-01-15",
            "recurrence": "monthly",
            "recurrence_until": "2026-03-15",
        },
    )
    elenco = client.get("/api/reminders", params={"q": "Rata", "sort": "due_date"}).json()["items"]

    seconda = client.get(f"/api/reminders/{elenco[1]['id']}").json()

    assert seconda["series_position"] == [2, 3]


# ----------------------------------------------------------- comportamento


def test_chiudere_un_occorrenza_di_una_serie_non_ne_crea_altre(client):
    """Esistono già tutte: generarne una alla chiusura sdoppierebbe l'ultima."""
    client.post(
        "/api/reminders",
        json={
            "title": "Rata",
            "due_date": "2026-01-15",
            "recurrence": "monthly",
            "recurrence_until": "2026-03-15",
        },
    )
    elenco = client.get("/api/reminders", params={"q": "Rata", "sort": "due_date"}).json()["items"]

    client.post(f"/api/reminders/{elenco[0]['id']}/complete")

    # Senza filtro di stato: l'occorrenza chiusa c'è ancora, ma non se ne sono
    # aggiunte altre.
    assert client.get("/api/reminders", params={"q": "Rata"}).json()["total"] == 3


def test_eliminare_una_sola_occorrenza(client):
    client.post(
        "/api/reminders",
        json={
            "title": "Rata",
            "due_date": "2026-01-15",
            "recurrence": "monthly",
            "recurrence_until": "2026-03-15",
        },
    )
    elenco = client.get("/api/reminders", params={"q": "Rata", "sort": "due_date"}).json()["items"]

    client.delete(f"/api/reminders/{elenco[0]['id']}")

    assert client.get("/api/reminders", params={"q": "Rata"}).json()["total"] == 2


def test_eliminare_tutta_la_serie(client):
    client.post(
        "/api/reminders",
        json={
            "title": "Rata",
            "due_date": "2026-01-15",
            "recurrence": "monthly",
            "recurrence_until": "2026-03-15",
        },
    )
    elenco = client.get("/api/reminders", params={"q": "Rata", "sort": "due_date"}).json()["items"]

    client.delete(f"/api/reminders/{elenco[1]['id']}", params={"series": True})

    assert client.get("/api/reminders", params={"q": "Rata"}).json()["total"] == 0


def test_anteprima_delle_occorrenze(client):
    """Il form la usa per costruire la tabella degli importi prima di salvare."""
    risposta = client.get(
        "/api/reminders/occurrences",
        params={
            "due_date": "2026-01-31",
            "recurrence": "monthly",
            "recurrence_until": "2026-04-30",
            "amount": 50,
        },
    )

    assert [o["due_date"] for o in risposta.json()] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
    ]
    assert all(o["amount"] == 50 for o in risposta.json())


# ------------------------------------------------------------- vista anno


def test_il_calendario_annuale_conta_per_giorno_e_per_tipo(client, make_reminder):
    oggi = date.today()
    make_reminder(0, title="Scadenza")
    make_reminder(0, title="Riunione", kind="appointment")
    make_reminder(1, title="Domani")

    anno = client.get("/api/reminders/calendar/year", params={"year": oggi.year}).json()
    per_data = {g["date"]: g for g in anno["days"]}

    assert per_data[oggi.isoformat()]["total"] == 2
    assert per_data[oggi.isoformat()]["deadline"] == 1
    assert per_data[oggi.isoformat()]["appointment"] == 1


def test_il_calendario_annuale_manda_solo_i_giorni_pieni(client, make_reminder):
    """Trecentosessantacinque righe vuote per disegnare dei pallini sarebbero
    solo peso."""
    make_reminder(0)

    anno = client.get("/api/reminders/calendar/year", params={"year": date.today().year}).json()

    assert len(anno["days"]) == 1


def test_una_serie_su_misura_riempie_le_date_fino_alla_fine():
    """«Ogni 45 giorni» non ha un nome, ma è una serie come le altre."""
    date_serie = reminder_service.occurrence_dates(
        date(2026, 1, 1), Recurrence.CUSTOM, date(2026, 5, 1), 45, RecurrenceUnit.DAYS
    )

    assert date_serie == [
        date(2026, 1, 1),
        date(2026, 2, 15),
        date(2026, 4, 1),
    ]


def test_l_api_crea_una_serie_su_misura(client):
    risposta = client.post(
        "/api/reminders",
        json={
            "title": "Manutenzione impianto",
            "due_date": "2026-01-01",
            "recurrence": "custom",
            "recurrence_every": 45,
            "recurrence_unit": "days",
            "recurrence_until": "2026-05-01",
        },
    )

    assert risposta.status_code == 201
    creato = risposta.json()
    assert creato["recurrence_every"] == 45
    assert creato["recurrence_unit"] == "days"
    # Tre occorrenze: 1 gennaio, 15 febbraio, 1 aprile.
    letto = client.get(f"/api/reminders/{creato['id']}").json()
    assert letto["series_position"] == [1, 3]


def test_l_api_rifiuta_un_su_misura_senza_intervallo(client):
    """Senza «ogni quanto» la ricorrenza personalizzata non vuol dire nulla."""
    risposta = client.post(
        "/api/reminders",
        json={"title": "Boh", "due_date": "2026-01-01", "recurrence": "custom"},
    )

    assert risposta.status_code == 422


def test_una_cadenza_con_un_nome_non_si_porta_dietro_un_intervallo(client):
    risposta = client.post(
        "/api/reminders",
        json={
            "title": "Revisione biennale",
            "due_date": "2026-01-01",
            "recurrence": "biennial",
            "recurrence_every": 45,
            "recurrence_unit": "days",
        },
    )

    assert risposta.status_code == 201
    assert risposta.json()["recurrence_every"] is None
    assert risposta.json()["recurrence_unit"] is None
