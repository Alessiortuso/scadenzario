"""Come viene servita l'interfaccia compilata.

Dietro c'è una schermata bianca vista in produzione dopo un aggiornamento: il
browser aveva in cache l'`index.html` della versione precedente e chiedeva
script che non esistevano più; il fallback della SPA rispondeva `index.html`
anche a quelli, e il browser si ritrovava HTML dove aspettava JavaScript. Niente
veniva eseguito, la finestra restava bianca e i click non facevano nulla.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SpaStaticFiles


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Promemoria</title>", encoding="utf-8")
    (tmp_path / "main-ABC123.js").write_text("console.log('ciao')", encoding="utf-8")

    app = FastAPI()
    app.mount("/", SpaStaticFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_index_non_si_mette_in_cache(client):
    risposta = client.get("/")
    assert risposta.status_code == 200
    assert risposta.headers["cache-control"] == "no-store"


def test_le_rotte_dell_interfaccia_ricadono_su_index(client):
    risposta = client.get("/calendario")
    assert risposta.status_code == 200
    assert "Promemoria" in risposta.text
    assert risposta.headers["cache-control"] == "no-store"


def test_uno_script_che_non_esiste_piu_risponde_404(client):
    """Il fallback non deve trasformare uno script mancante in una pagina HTML."""
    risposta = client.get("/main-VECCHIO.js")
    assert risposta.status_code == 404


def test_gli_script_presenti_si_rivalidano(client):
    risposta = client.get("/main-ABC123.js")
    assert risposta.status_code == 200
    assert risposta.headers["cache-control"] == "no-cache"
