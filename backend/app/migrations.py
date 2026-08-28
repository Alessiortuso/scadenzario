"""Applicazione delle migrazioni allo schema.

Perché non basta `create_all`: le postazioni installate hanno già un database
condiviso popolato, e `create_all` crea solo le tabelle mancanti — non aggiunge
una colonna a una tabella che esiste. Lo schema si evolve quindi con Alembic,
così un aggiornamento dell'applicazione porta con sé il proprio adeguamento del
database.

Due database, due storie separate (vedi `alembic/env.py`):

- il **condiviso** viene migrato da qualunque postazione si colleghi;
- il **locale** a ogni avvio, prima ancora di sapere se il condiviso esiste.

Le installazioni nate prima di Alembic hanno le tabelle ma non la tabella delle
versioni: in quel caso lo schema viene *marcato* alla revisione iniziale invece
di ricrearlo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

#: Revisione che fotografa lo schema della 1.0.0, quando le migrazioni non
#: esistevano ancora.
BASELINE = "0001"

#: Tabella già presente prima di Alembic: se c'è, il database non è nuovo.
#:
#: Resta `deadlines` anche dopo la rinomina in `reminders` della 0002: la spia
#: serve a riconoscere le installazioni 1.0.0, che quel nome ce l'hanno ancora.
#: Un database già migrato ha la tabella delle versioni e non arriva qui.
_WITNESS = {"shared": "deadlines", "local": "notifications"}

_VERSION_TABLE = {"shared": "alembic_version", "local": "alembic_version_local"}

_NOME = {"shared": "condiviso", "local": "di questa postazione"}


class SchemaPiuRecente(RuntimeError):
    """Il database è stato migrato da una versione più recente dell'app.

    Succede sul condiviso appena una postazione si aggiorna prima delle altre:
    quella applica la nuova revisione, e chi è rimasto indietro se la trova
    scritta nel database senza avere il file che la descrive. Alembic da solo
    direbbe soltanto «Can't locate revision identified by 0004», che non
    suggerisce a nessuno la cosa da fare — cioè aggiornare l'applicazione.
    """

    #: Codice stabile, per chi deve *decidere* e non solo scrivere.
    #:
    #: È l'unico guasto del collegamento che la postazione sa riparare da sé:
    #: riconoscendolo, la schermata di configurazione offre il pulsante che
    #: scarica e applica l'aggiornamento, invece di rimandare a GitHub. Il testo
    #: del messaggio non serve allo scopo — cambia, si traduce, si riformula.
    codice = "schema_piu_recente"


def _script_location() -> Path:
    """Dove stanno le migrazioni, in sviluppo e dentro l'eseguibile."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "alembic"
    return Path(__file__).resolve().parent.parent / "alembic"


def _config(target: str, connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_script_location()))
    config.attributes["connection"] = connection
    config.attributes["target"] = target
    return config


def _head(config: Config) -> str | None:
    return ScriptDirectory.from_config(config).get_current_head()


def _current(connection: Connection, target: str) -> str | None:
    context = MigrationContext.configure(
        connection, opts={"version_table": _VERSION_TABLE[target]}
    )
    return context.get_current_revision()


def _verifica_conoscenza(config: Config, current: str | None, target: str) -> None:
    """Ferma l'aggiornamento se la revisione nel database è sconosciuta.

    Andare avanti non è un'opzione: Alembic non sa da dove partire e le tabelle
    hanno comunque una forma che questo codice non si aspetta. L'unica cosa
    utile è dirlo con parole che indichino il rimedio.
    """
    if current is None:
        return

    script = ScriptDirectory.from_config(config)
    try:
        script.get_revision(current)
    except Exception as exc:
        raise SchemaPiuRecente(
            f"Il database {_NOME[target]} è alla revisione {current}, che questa versione di "
            "Promemoria non conosce: è stato aggiornato da una postazione con una versione più "
            "recente. Aggiorna Promemoria su questo computer e riprova."
        ) from exc


def upgrade(engine: Engine, target: str) -> str | None:
    """Porta lo schema di `target` ("shared" o "local") all'ultima revisione.

    Ritorna la revisione applicata. Gli errori non vengono nascosti: uno schema
    disallineato è esattamente il caso in cui l'applicazione non deve partire
    facendo finta di niente.
    """
    with engine.begin() as connection:
        config = _config(target, connection)
        current = _current(connection, target)

        if current is None and inspect(connection).has_table(_WITNESS[target]):
            # Installazione precedente ad Alembic: le tabelle ci sono già, va
            # solo registrato il punto di partenza.
            logger.info("Schema %s preesistente: marcato alla revisione %s", target, BASELINE)
            command.stamp(config, BASELINE)
            current = BASELINE

        head = _head(config)
        if current == head:
            return current

        _verifica_conoscenza(config, current, target)

        logger.info("Migrazione schema %s: %s -> %s", target, current or "vuoto", head)
        command.upgrade(config, "head")
        return head
