"""Punto d'ingresso del backend impacchettato.

Nel pacchetto distribuito non esiste `uvicorn` da riga di comando: è questo
eseguibile a farlo partire. Viene avviato dall'applicazione Electron, che gli
passa la porta.

    promemoria-backend.exe --port 8010
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend di Promemoria")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    # Nel pacchetto i log su console non sono visibili: si scrivono su file
    # accanto al database locale, per poter diagnosticare i problemi.
    from app.config import settings

    log_file = Path(settings.data_dir) / "promemoria.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    # In un eseguibile senza console i flussi standard possono non esistere.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        # Si riusa la configurazione di logging qui sopra: quella di uvicorn
        # scriverebbe su flussi che nel pacchetto potrebbero non esserci.
        log_config=None,
    )


if __name__ == "__main__":
    main()
