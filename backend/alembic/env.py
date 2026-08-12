"""Ambiente Alembic per i due database dello Scadenzario.

Ogni esecuzione riguarda **un solo** database, indicato da
`config.attributes["target"]`:

- ``shared`` — PostgreSQL condiviso: scadenze, categorie, impostazioni;
- ``local``  — SQLite della postazione: notifiche e iscrizioni push.

I due hanno storie separate, quindi anche tabelle di versione separate
(`alembic_version` e `alembic_version_local`): girano sullo stesso file di
migrazioni ma nessuno dei due vede le revisioni dell'altro.

La connessione arriva sempre da `app.migrations`, mai dall'ini: le credenziali
del database condiviso stanno nel `config.json` della postazione.
"""

from __future__ import annotations

from alembic import context

from app.db import Base, LocalBase

TARGETS = {
    "shared": (Base.metadata, "alembic_version"),
    "local": (LocalBase.metadata, "alembic_version_local"),
}

config = context.config
target = config.attributes.get("target", "shared")
metadata, version_table = TARGETS[target]


def run_migrations_offline() -> None:
    """Genera l'SQL senza connettersi: utile per applicare a mano su un server."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=metadata,
        version_table=version_table,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations(target=target)


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError(
            "Nessuna connessione fornita: le migrazioni si avviano da app.migrations"
        )

    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table=version_table,
        # SQLite non sa alterare una colonna: senza questo le migrazioni future
        # sul database locale fallirebbero.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations(target=target)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
