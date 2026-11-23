"""Unified pointer/touch event model.

Coordinates are always in *logical* space (the same coordinate system
screens draw in, e.g. 0..320 x 0..170) — never physical screen pixels. Each
PointerBackend is responsible for converting raw physical coordinates into
logical ones before emitting an event (see
hal.display_backend.physical_to_logical, used as the conversion function).
"""
from dataclasses import dataclass

KIND_DOWN   = "down"
KIND_MOVE   = "move"
KIND_UP     = "up"
KIND_TAP    = "tap"
KIND_SCROLL = "scroll"  # desktop mouse wheel; not positional, see `dy`


@dataclass
class PointerEvent:
    x: int
    y: int
    kind: str  # one of KIND_DOWN, KIND_MOVE, KIND_UP, KIND_TAP, KIND_SCROLL
    dy: int = 0  # KIND_SCROLL only: wheel notches, positive = scrolled up (toward content start)
