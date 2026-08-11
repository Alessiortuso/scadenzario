"""Popola il database con categorie e scadenze di esempio.

Uso:
    python -m app.tools.seed
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from ..db import LocalSession, SharedSession, init_db
from ..models import Category, Deadline, Priority, Recurrence

CATEGORIES = [
    ("Fiscale", "#ef4444", [30, 15, 7, 3, 1, 0]),
    ("Contratti", "#6366f1", [60, 30, 15, 7, 0]),
    ("Assicurazioni", "#0ea5e9", [45, 30, 15, 7, 1, 0]),
    ("Certificazioni", "#22c55e", [90, 60, 30, 7, 0]),
]


def run() -> None:
    init_db()
    db = SharedSession()
    local_db = LocalSession()
    try:
        by_name: dict[str, Category] = {}
        for name, color, offsets in CATEGORIES:
            category = db.scalar(select(Category).where(Category.name == name))
            if category is None:
                category = Category(name=name, color=color, alert_offsets=offsets)
                db.add(category)
            by_name[name] = category
        db.flush()

        today = date.today()
        samples = [
            ("Versamento IVA trimestrale", "Fiscale", today + timedelta(days=5), 4820.50, Recurrence.QUARTERLY, Priority.HIGH),
            ("Rinnovo polizza RC professionale", "Assicurazioni", today + timedelta(days=21), 1250.00, Recurrence.YEARLY, Priority.NORMAL),
            ("Scadenza contratto fornitore Rossi Srl", "Contratti", today + timedelta(days=45), None, Recurrence.NONE, Priority.NORMAL),
            ("Rinnovo certificazione ISO 9001", "Certificazioni", today + timedelta(days=95), 3000.00, Recurrence.YEARLY, Priority.HIGH),
            ("Modello F24 dipendenti", "Fiscale", today + timedelta(days=1), 7310.20, Recurrence.MONTHLY, Priority.CRITICAL),
            ("Visita medica periodica addetti", "Certificazioni", today - timedelta(days=4), None, Recurrence.YEARLY, Priority.HIGH),
        ]

        created = 0
        for title, category_name, due, amount, recurrence, priority in samples:
            if db.scalar(select(Deadline).where(Deadline.title == title, Deadline.due_date == due)):
                continue
            db.add(
                Deadline(
                    title=title,
                    due_date=due,
                    amount=amount,
                    recurrence=recurrence,
                    priority=priority,
                    category_id=by_name[category_name].id,
                    owner="Amministrazione",
                    source="seed",
                )
            )
            created += 1
        db.commit()

        from ..services import alerts

        generated = alerts.sync_all(db, local_db)
        print(f"Categorie pronte: {len(by_name)} | scadenze create: {created} | avvisi generati: {generated}")
    finally:
        local_db.close()
        db.close()


if __name__ == "__main__":
    run()
