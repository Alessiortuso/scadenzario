"""Endpoint delle scadenze: filtri e ordinamenti dell'elenco."""

from __future__ import annotations

from app.models import Priority


def _titoli(risposta) -> list[str]:
    return [d["title"] for d in risposta.json()["items"]]


def test_ordinamento_per_priorita_segue_l_urgenza_non_l_alfabeto(client, make_deadline):
    """In tabella la priorità è una parola: ordinarla direttamente darebbe
    critica, alta, bassa, normale — cioè l'alfabeto, non l'urgenza."""
    make_deadline(30, title="Bassa", priority=Priority.LOW)
    make_deadline(30, title="Critica", priority=Priority.CRITICAL)
    make_deadline(30, title="Normale", priority=Priority.NORMAL)
    make_deadline(30, title="Alta", priority=Priority.HIGH)

    risposta = client.get("/api/deadlines", params={"sort": "priority"})

    assert _titoli(risposta) == ["Critica", "Alta", "Normale", "Bassa"]


def test_ordinamento_per_priorita_invertito(client, make_deadline):
    make_deadline(30, title="Bassa", priority=Priority.LOW)
    make_deadline(30, title="Critica", priority=Priority.CRITICAL)
    make_deadline(30, title="Alta", priority=Priority.HIGH)

    risposta = client.get("/api/deadlines", params={"sort": "-priority"})

    assert _titoli(risposta) == ["Bassa", "Alta", "Critica"]


def test_a_parita_di_priorita_viene_prima_chi_scade_prima(client, make_deadline):
    make_deadline(60, title="Critica lontana", priority=Priority.CRITICAL)
    make_deadline(2, title="Critica imminente", priority=Priority.CRITICAL)
    make_deadline(10, title="Critica intermedia", priority=Priority.CRITICAL)

    risposta = client.get("/api/deadlines", params={"sort": "priority"})

    assert _titoli(risposta) == ["Critica imminente", "Critica intermedia", "Critica lontana"]


def test_gli_altri_ordinamenti_restano_invariati(client, make_deadline):
    make_deadline(30, title="Bravo")
    make_deadline(10, title="Alfa")

    per_data = client.get("/api/deadlines", params={"sort": "due_date"})
    per_titolo = client.get("/api/deadlines", params={"sort": "-title"})

    assert _titoli(per_data) == ["Alfa", "Bravo"]
    assert _titoli(per_titolo) == ["Bravo", "Alfa"]


def test_ordinamento_sconosciuto_rifiutato(client):
    """Il nome della colonna finisce in un getattr: va tenuto su una lista chiusa."""
    assert client.get("/api/deadlines", params={"sort": "password"}).status_code == 422
