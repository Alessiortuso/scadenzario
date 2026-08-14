"""Endpoint dei promemoria: filtri e ordinamenti dell'elenco."""

from __future__ import annotations


def _titoli(risposta) -> list[str]:
    return [r["title"] for r in risposta.json()["items"]]


def test_ordinamento_per_data(client, make_reminder):
    make_reminder(30, title="Bravo")
    make_reminder(10, title="Alfa")

    assert _titoli(client.get("/api/reminders", params={"sort": "due_date"})) == ["Alfa", "Bravo"]
    assert _titoli(client.get("/api/reminders", params={"sort": "-due_date"})) == ["Bravo", "Alfa"]


def test_ordinamento_per_titolo(client, make_reminder):
    make_reminder(30, title="Bravo")
    make_reminder(10, title="Alfa")

    assert _titoli(client.get("/api/reminders", params={"sort": "-title"})) == ["Bravo", "Alfa"]


def test_ordinamento_per_importo(client, make_reminder):
    make_reminder(30, title="Piccolo", amount=10.0)
    make_reminder(10, title="Grande", amount=900.0)

    assert _titoli(client.get("/api/reminders", params={"sort": "-amount"})) == ["Grande", "Piccolo"]


def test_ordinamento_sconosciuto_rifiutato(client):
    """Il nome della colonna finisce in un getattr: va tenuto su una lista chiusa."""
    assert client.get("/api/reminders", params={"sort": "password"}).status_code == 422


def test_la_priorita_non_e_piu_un_ordinamento_valido(client):
    """Rimossa con la colonna: chiederla ora è un errore, non un ordine casuale."""
    assert client.get("/api/reminders", params={"sort": "priority"}).status_code == 422


def test_filtro_per_ricerca_testuale(client, make_reminder):
    make_reminder(10, title="Versamento IVA")
    make_reminder(10, title="Riunione", owner="Studio Bianchi")

    assert _titoli(client.get("/api/reminders", params={"q": "iva"})) == ["Versamento IVA"]
    assert _titoli(client.get("/api/reminders", params={"q": "bianchi"})) == ["Riunione"]
