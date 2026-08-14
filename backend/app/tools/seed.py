"""Popola il database con promemoria di esempio.

Uso:
    python -m app.tools.seed
"""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import select

from ..db import LocalSession, SharedSession, init_db
from ..models import Recurrence, Reminder, ReminderKind


def run() -> None:
    init_db()
    db = SharedSession()
    local_db = LocalSession()
    try:
        today = date.today()
        D, A, O = ReminderKind.DEADLINE, ReminderKind.APPOINTMENT, ReminderKind.OTHER
        samples = [
            ("Versamento IVA trimestrale", today + timedelta(days=5), None, D, 4820.50, Recurrence.QUARTERLY),
            ("Rinnovo polizza RC professionale", today + timedelta(days=21), None, D, 1250.00, Recurrence.YEARLY),
            ("Scadenza contratto fornitore Rossi Srl", today + timedelta(days=45), None, D, None, Recurrence.NONE),
            ("Rinnovo certificazione ISO 9001", today + timedelta(days=95), None, D, 3000.00, Recurrence.YEARLY),
            ("Modello F24 dipendenti", today + timedelta(days=1), None, D, 7310.20, Recurrence.MONTHLY),
            ("Visita medica periodica addetti", today - timedelta(days=4), time(9, 0), A, None, Recurrence.YEARLY),
            ("Riunione con il commercialista", today + timedelta(days=3), time(15, 30), A, None, Recurrence.NONE),
            ("Sopralluogo cantiere via Verdi", today + timedelta(days=8), time(10, 0), A, None, Recurrence.NONE),
            ("Preparare documenti per il revisore", today + timedelta(days=12), None, O, None, Recurrence.NONE),
        ]

        created = 0
        for title, due, start, kind, amount, recurrence in samples:
            if db.scalar(select(Reminder).where(Reminder.title == title, Reminder.due_date == due)):
                continue
            db.add(
                Reminder(
                    title=title,
                    due_date=due,
                    start_time=start,
                    kind=kind,
                    amount=amount,
                    recurrence=recurrence,
                    owner="Amministrazione",
                    source="seed",
                )
            )
            created += 1
        db.commit()

        from ..services import alerts

        generated = alerts.sync_all(db, local_db)
        print(f"Promemoria creati: {created} | avvisi generati: {generated}")
    finally:
        local_db.close()
        db.close()


if __name__ == "__main__":
    run()
