from __future__ import annotations

from collections import deque
from typing import Protocol

from screensense.models import ScreenObservation


class ObservationWriter(Protocol):
    def persist(self, item: ScreenObservation) -> None:
        ...


class RollingMemory:
    def __init__(self, max_items: int = 40, writer: ObservationWriter | None = None) -> None:
        self._items: deque[ScreenObservation] = deque(maxlen=max_items)
        self._writer = writer

    def add(self, item: ScreenObservation) -> None:
        self._items.append(item)
        if self._writer is not None:
            try:
                self._writer.persist(item)
            except Exception:
                pass

    def recent(self) -> list[ScreenObservation]:
        return list(self._items)
