from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class SourceTable:
    columns: list[str]
    rows: list[dict[str, str]] = field(default_factory=list)


class SourceAdapter(ABC):
    """Fonte da cui leggere le scadenze.

    Oggi implementata da CSV/Excel. Quando il cliente indicherà il gestionale,
    basterà aggiungere un adapter (REST, database, cartella condivisa) che
    restituisca una `SourceTable`: il resto della pipeline non cambia.
    """

    name: str = "base"
    #: Estensioni file gestite; vuoto per fonti non basate su file.
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def read(self, content: bytes, filename: str) -> SourceTable: ...
