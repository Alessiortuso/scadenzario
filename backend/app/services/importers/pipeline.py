from __future__ import annotations

import re
from datetime import date, datetime

from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Category, Deadline
from ...schemas import ImportMapping, ImportPreview, ImportPreviewRow, ImportResult
from .. import alerts, settings_service
from .base import SourceTable

#: Sinonimi (in minuscolo) usati per indovinare la mappatura delle colonne.
FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "due_date": ("data scadenza", "scadenza", "data_scadenza", "due date", "due_date", "data", "expiry"),
    "title": ("titolo", "oggetto", "descrizione breve", "title", "nome", "documento", "tipo documento"),
    "description": ("descrizione", "note", "dettaglio", "description", "notes"),
    "amount": ("importo", "totale", "valore", "amount", "imponibile"),
    "owner": ("cliente", "fornitore", "intestatario", "referente", "responsabile", "owner", "assegnatario"),
    "reference": ("riferimento", "numero", "protocollo", "documento n", "reference", "n. doc", "fattura"),
    "category": ("categoria", "tipo", "tipologia", "category", "gruppo"),
    "external_id": ("id", "codice", "id esterno", "external_id", "chiave", "key"),
}

_AMOUNT_CLEAN = re.compile(r"[^\d,.\-]")


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Associa i campi della scadenza alle colonne del file, per nome."""
    normalized = {c: c.strip().lower() for c in columns}
    mapping: dict[str, str] = {}
    used: set[str] = set()

    for field, hints in FIELD_HINTS.items():
        best: tuple[int, str] | None = None
        for column, low in normalized.items():
            if column in used:
                continue
            for rank, hint in enumerate(hints):
                if low == hint:
                    score = 100 - rank
                elif hint in low:
                    score = 50 - rank
                else:
                    continue
                if best is None or score > best[0]:
                    best = (score, column)
        if best is not None:
            mapping[field] = best[1]
            used.add(best[1])

    # Molti tracciati hanno solo "Descrizione": usiamola come titolo.
    if "title" not in mapping and "description" in mapping:
        mapping["title"] = mapping["description"]

    return mapping


def parse_date(value: str, fmt: str | None = None) -> date:
    value = (value or "").strip()
    if not value:
        raise ValueError("data mancante")
    if fmt:
        return datetime.strptime(value, fmt).date()
    # Numero seriale Excel (es. 45678) usato da alcuni export.
    if value.isdigit() and len(value) == 5:
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(value))
    return date_parser.parse(value, dayfirst=True).date()


def parse_amount(value: str) -> float | None:
    value = _AMOUNT_CLEAN.sub("", (value or "").strip())
    if not value:
        return None
    if "," in value and "." in value:
        # Formato italiano 1.234,56 oppure inglese 1,234.56
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _row_values(row: dict[str, str], mapping: ImportMapping) -> tuple[dict, list[str]]:
    errors: list[str] = []
    get = lambda col: (row.get(col) or "").strip() if col else ""  # noqa: E731

    title = get(mapping.title)
    if not title:
        errors.append("titolo mancante")

    due: date | None = None
    try:
        due = parse_date(get(mapping.due_date), mapping.date_format)
    except Exception as exc:
        errors.append(f"data non valida ({get(mapping.due_date) or 'vuota'}): {exc}")

    return (
        {
            "title": title,
            "due_date": due,
            "description": get(mapping.description) or None,
            "amount": parse_amount(get(mapping.amount)),
            "owner": get(mapping.owner) or None,
            "reference": get(mapping.reference) or None,
            "category": get(mapping.category) or None,
            "external_id": get(mapping.external_id) or None,
        },
        errors,
    )


def preview(table: SourceTable, mapping: ImportMapping | None = None, limit: int = 10) -> ImportPreview:
    suggested = suggest_mapping(table.columns)
    rows: list[ImportPreviewRow] = []

    if mapping is not None:
        for idx, raw in enumerate(table.rows[:limit], start=2):
            data, errors = _row_values(raw, mapping)
            rows.append(
                ImportPreviewRow(
                    row=idx,
                    data={k: (v.isoformat() if isinstance(v, date) else v) for k, v in data.items()},
                    errors=errors,
                )
            )
    else:
        rows = [ImportPreviewRow(row=idx, data=raw) for idx, raw in enumerate(table.rows[:limit], start=2)]

    return ImportPreview(
        columns=table.columns,
        suggested_mapping=suggested,
        rows=rows,
        total_rows=len(table.rows),
    )


def _get_or_create_category(db: Session, name: str, cache: dict[str, Category]) -> Category:
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    category = db.scalar(select(Category).where(Category.name == name.strip()))
    if category is None:
        category = Category(name=name.strip())
        db.add(category)
        db.flush()
    cache[key] = category
    return category


def apply_import(
    db: Session, local_db: Session, table: SourceTable, mapping: ImportMapping
) -> ImportResult:
    """Crea/aggiorna le scadenze a partire dalla tabella sorgente.

    L'upsert usa (source, external_id) quando la colonna id è mappata,
    altrimenti (titolo, data) per evitare duplicati su import ripetuti.
    """
    app_settings = settings_service.get_settings(db)
    cache: dict[str, Category] = {}
    created = updated = skipped = 0
    errors: list[str] = []
    touched: list[Deadline] = []

    for idx, raw in enumerate(table.rows, start=2):
        data, row_errors = _row_values(raw, mapping)
        if row_errors:
            skipped += 1
            if len(errors) < 50:
                errors.append(f"riga {idx}: {'; '.join(row_errors)}")
            continue

        category = _get_or_create_category(db, data["category"], cache) if data["category"] else None

        existing: Deadline | None = None
        if data["external_id"]:
            existing = db.scalar(
                select(Deadline).where(
                    Deadline.source == mapping.source,
                    Deadline.external_id == data["external_id"],
                )
            )
        else:
            existing = db.scalar(
                select(Deadline).where(
                    Deadline.title == data["title"],
                    Deadline.due_date == data["due_date"],
                )
            )

        if existing is None:
            deadline = Deadline(
                title=data["title"],
                description=data["description"],
                due_date=data["due_date"],
                amount=data["amount"],
                owner=data["owner"],
                reference=data["reference"],
                category_id=category.id if category else None,
                alert_offsets=mapping.default_alert_offsets,
                source=mapping.source,
                external_id=data["external_id"],
                extra={"import_row": idx},
            )
            db.add(deadline)
            db.flush()
            created += 1
            touched.append(deadline)
        else:
            changed = False
            for field in ("title", "description", "due_date", "amount", "owner", "reference"):
                if getattr(existing, field) != data[field] and data[field] is not None:
                    setattr(existing, field, data[field])
                    changed = True
            if category is not None and existing.category_id != category.id:
                existing.category_id = category.id
                changed = True
            if changed:
                updated += 1
                touched.append(existing)
            else:
                skipped += 1

    db.commit()
    for deadline in touched:
        alerts.sync_deadline_notifications(local_db, deadline, app_settings, commit=False)
    local_db.commit()

    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors)
