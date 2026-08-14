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

        logger.info("Migrazione schema %s: %s -> %s", target, current or "vuoto", head)
        command.upgrade(config, "head")
        return head
