"""Configurazione scritta dalla schermata di primo avvio.

Le credenziali del database condiviso **non** vengono impacchettate
nell'installer: ogni postazione le riceve alla prima apertura e le salva in
`%LOCALAPPDATA%\\Promemoria\\config.json`. Così l'installer è un file neutro,
pubblicabile senza esporre nulla, e cambiare la password del database non
richiede di ridistribuire l'applicazione.

Precedenza: `config.json` → variabili d'ambiente / `.env` (comodo in sviluppo).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

CONFIG_FILE = settings.data_dir / "config.json"


def load() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("File di configurazione illeggibile: %s", CONFIG_FILE)
        return {}


def save(data: dict[str, Any]) -> None:
    current = load()
    current.update({k: v for k, v in data.items() if v is not None})
    CONFIG_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Configurazione salvata in %s", CONFIG_FILE)


def database_url() -> str:
    return str(load().get("database_url") or settings.database_url or "")


def device_name() -> str:
    return str(load().get("device_name") or settings.resolved_device_name)


def email_sender_device() -> bool:
    value = load().get("email_sender_device")
    return bool(settings.email_sender_device if value is None else value)


def source() -> str:
    """Da dove arriva la configurazione attuale: utile da mostrare all'utente."""
    if load().get("database_url"):
        return "config"
    return "env" if settings.database_url else "none"


def mask(url: str) -> str:
    """Nasconde la password per poter mostrare la stringa nell'interfaccia."""
    if "@" not in url or "//" not in url:
        return url
    scheme, _, rest = url.partition("//")
    credentials, _, host = rest.partition("@")
    user, sep, _password = credentials.partition(":")
    if not sep:
        return url
    return f"{scheme}//{user}:••••••@{host}"
