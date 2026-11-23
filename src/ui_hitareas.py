"""Touch/pointer hit-testing and list-scrolling for screens.

Screens already compute pixel rectangles for every button/row they draw
(passed straight to draw.rectangle(...)). This module lets a screen also
register those same rectangles as tappable areas, so a tap maps to exactly
the same action a keyboard focus+Enter would trigger — no separate touch
logic, no risk of the two input paths drifting apart.

Usage pattern, once per _draw() call:

    registry = HitAreaRegistry()
    ...
    registry.add(FOCUS_SOME_BUTTON, (bx, by, bx + w, by + h))
    ...

Then once per main-loop iteration — pointer events must be drained exactly
ONCE per iteration and fanned out to every consumer (handle_tap,
ListScroll, ...); each has its own poll_pointer_events() would otherwise
race to drain the same queue and steal each other's events:

    events = drain_pointer_events(input_handler)
    tapped = handle_tap(events, registry)
    if tapped is not None:
        _activate(tapped)   # same function the KEY_ENTER branch calls
    scroll_delta = list_scroll.poll(events, list_area_rect)
"""
import os
from dataclasses import dataclass
from typing import Any

from hal.pointer_event import KIND_DOWN, KIND_MOVE, KIND_UP, KIND_TAP, KIND_SCROLL

_DEBUG = os.environ.get("ESPFLASHER_DEBUG_INPUT") == "1"


@dataclass
class HitArea:
    rect: tuple  # (x0, y0, x1, y1) — same coordinates passed to draw.rectangle
    id: Any


class HitAreaRegistry:
    def __init__(self):
        self._areas = []

    def clear(self):
        self._areas = []

    def add(self, id, rect):
        """Registers a tappable rectangle. When rectangles overlap, the one
        added last wins (mirrors on-screen stacking: whatever was drawn last
        is on top)."""
        self._areas.append(HitArea(rect=rect, id=id))


def hit_test(registry, x, y):
    """Returns the id of the top-most area containing (x, y), or None."""
    if registry is None:
        return None
    for area in reversed(registry._areas):
        x0, y0, x1, y1 = area.rect
        if x0 <= x <= x1 and y0 <= y <= y1:
            return area.id
    return None


def drain_pointer_events(input_handler):
    """Drains and returns pending pointer events from input_handler. Always
    returns a list (empty when there's no pointer support, e.g.
    NullPointerBackend, or no input_handler at all) — call this exactly
    once per loop iteration and pass the result to handle_tap/ListScroll,
    rather than letting each of them poll independently."""
    if input_handler is None:
        return []
    poll = getattr(input_handler, "poll_pointer_events", None)
    if poll is None:
        return []
    events = poll()
    if _DEBUG and events:
        print(f"[ui_hitareas] {len(events)} pointer event(s): {events}")
    return events


def handle_tap(events, registry):
    """Hit-tests any 'tap' events (from a list already drained via
    drain_pointer_events) against registry. Returns the id of the last
    tapped area, or None if no tap landed on a registered area."""
    if registry is None:
        return None
    tapped_id = None
    for ev in events:
        if ev.kind == KIND_TAP:
            hit = hit_test(registry, ev.x, ev.y)
            if _DEBUG:
                areas = [(a.id, a.rect) for a in registry._areas]
                print(f"[ui_hitareas] tap at ({ev.x}, {ev.y}) -> hit={hit!r}  registered areas={areas}")
            if hit is not None:
                tapped_id = hit
    return tapped_id


def _point_in_rect(x, y, rect):
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


class ListScroll:
    """Touch-drag / mouse-wheel scrolling for a list area.

    Wraps both input styles behind one poll() call so screens don't need to
    know which one produced the delta: real touchscreens have no wheel, so
    dragging a finger up/down over the list is the equivalent gesture;
    desktop dev mode additionally supports the mouse wheel.

    `row_h` is the pixel height of one list row (screens already know this
    — it's the same value used to lay out rows in _draw()). One row of
    drag distance, or one wheel notch, both yield a delta of 1.
    """

    def __init__(self, row_h):
        self.row_h = max(1, row_h)
        self._dragging = False
        self._last_y = None
        self._accum_px = 0

    def poll(self, events, area_rect):
        """events: pointer events already drained this tick (see
        drain_pointer_events). area_rect: (x0, y0, x1, y1) the drag must
        start inside for a drag-scroll to engage (wheel scrolling is not
        positional and always applies). Returns an integer row delta —
        positive means "scroll further down" (increase list offset),
        negative means "scroll up" — or 0 if nothing happened this tick."""
        delta_rows = 0
        for ev in events:
            if ev.kind == KIND_SCROLL:
                # Wheel "up" (dy > 0) moves the view toward the start of
                # the list, matching most desktop app conventions.
                delta_rows -= ev.dy
            elif ev.kind == KIND_DOWN:
                if _point_in_rect(ev.x, ev.y, area_rect):
                    self._dragging = True
                    self._last_y = ev.y
                    self._accum_px = 0
                else:
                    self._dragging = False
            elif ev.kind == KIND_MOVE and self._dragging:
                dy = ev.y - self._last_y
                self._last_y = ev.y
                # Content follows the finger: dragging up (dy < 0) reveals
                # items further down the list (offset increases).
                self._accum_px -= dy
                while self._accum_px >= self.row_h:
                    self._accum_px -= self.row_h
                    delta_rows += 1
                while self._accum_px <= -self.row_h:
                    self._accum_px += self.row_h
                    delta_rows -= 1
            elif ev.kind == KIND_UP:
                self._dragging = False
        if _DEBUG and delta_rows:
            print(f"[ui_hitareas] ListScroll delta_rows={delta_rows}")
        return delta_rows
