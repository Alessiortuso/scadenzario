"""Cosa succede quando il database è più avanti dell'applicazione.

Il caso è capitato in produzione: una postazione si aggiorna, applica la nuova
revisione sul database condiviso, e tutte le altre — ancora alla versione
precedente — smettono di collegarsi. Alembic dice «Can't locate revision
identified by 0004», l'applicazione conclude che la postazione non sia
configurata e mostra la schermata di primo avvio, così gli utenti riscrivono a
mano una stringa di connessione che era già giusta.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app import migrations


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_revisione_sconosciuta_lo_dice_con_parole_utili():
    engine = _engine()
    migrations.upgrade(engine, "local")

    # Il database viene portato a una revisione che questo codice non ha.
    with engine.begin() as connection:
        connection.execute(text("update alembic_version_local set version_num = '9999'"))

    with pytest.raises(migrations.SchemaPiuRecente) as errore:
        migrations.upgrade(engine, "local")

    messaggio = str(errore.value)
    assert "9999" in messaggio
    assert "Aggiorna Promemoria" in messaggio


def test_database_allineato_non_fa_nulla():
    engine = _engine()
    prima = migrations.upgrade(engine, "shared")
    assert migrations.upgrade(engine, "shared") == prima
