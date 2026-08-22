"""Due database, due responsabilità.

- **Condiviso** (PostgreSQL in cloud): promemoria e impostazioni. È la
  fonte di verità comune a tutte le postazioni. La sua connessione arriva dalla
  configurazione di primo avvio, quindi può non esserci ancora: in quel caso
  l'applicazione parte lo stesso e mostra la schermata di configurazione.
- **Locale** (SQLite nella cartella utente): stato di consegna delle notifiche
  *di questa postazione*. Sempre disponibile.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import runtime_config
from .config import settings


class NotConfigured(RuntimeError):
    """Il database condiviso non è ancora stato configurato su questa postazione."""


def _make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - infrastruttura
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


# Il database locale è sempre raggiungibile: si lega subito.
local_engine = _make_engine(settings.resolved_local_database_url)
LocalSession = sessionmaker(bind=local_engine, autoflush=False, expire_on_commit=False)

# Quello condiviso si lega solo quando la configurazione è disponibile.
SharedSession = sessionmaker(autoflush=False, expire_on_commit=False)
shared_engine: Engine | None = None

#: Perché l'ultimo tentativo di collegamento è fallito. Senza questo la
#: schermata di configurazione dice solo «manca la configurazione», e chi ha un
#: `config.json` valido ma uno schema che non si prepara riscrive le credenziali
#: per niente — è successo davvero, su tutte le postazioni in una volta.
shared_error: str | None = None


class Base(DeclarativeBase):
    """Tabelle del database condiviso."""


class LocalBase(DeclarativeBase):
    """Tabelle del database locale alla postazione."""


def configure_shared(url: str, *, migrate: bool = False) -> Engine:
    """Collega (o ricollega) il database condiviso all'URL indicato."""
    global shared_engine, shared_error

    engine = _make_engine(url)

    if migrate:
        from . import migrations, models  # noqa: F401  (i modelli registrano i metadata)

        try:
            migrations.upgrade(engine, "shared")
        except Exception as exc:
            shared_error = str(exc).splitlines()[0]
            raise

    SharedSession.configure(bind=engine)
    shared_engine = engine
    shared_error = None
    return engine


def is_shared_configured() -> bool:
    return shared_engine is not None


def get_db() -> Iterator[Session]:
    if shared_engine is None:
        raise NotConfigured
    db = SharedSession()
    try:
        yield db
    finally:
        db.close()


def get_local_db() -> Iterator[Session]:
    db = LocalSession()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Prepara il database locale e, se configurato, quello condiviso.

    Entrambi gli schemi passano dalle migrazioni: il locale sempre, il condiviso
    solo quando la postazione è già configurata.
    """
    from . import migrations, models  # noqa: F401  (registra i modelli sui metadata)

    migrations.upgrade(local_engine, "local")

    url = runtime_config.database_url()
    if url:
        configure_shared(url, migrate=True)
