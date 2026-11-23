"""Deterministic unit tests for ui_hitareas — no screens, no GUI, no network.

Uses a fake input_handler exposing only poll_pointer_events(), mirroring
what hal.input_facade.InputHandler / a NullPointerBackend-backed one
provides.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hal.pointer_event import PointerEvent
from ui_hitareas import HitAreaRegistry, hit_test, drain_pointer_events, handle_tap, ListScroll


class FakeInputHandler:
    def __init__(self, events):
        self._events = events

    def poll_pointer_events(self):
        events = self._events
        self._events = []
        return events


class NoPointerInputHandler:
    """Mirrors a NullPointerBackend-backed facade: no poll_pointer_events."""


class HitAreasTests(unittest.TestCase):
    def test_hit_test_basic(self):
        reg = HitAreaRegistry()
        reg.add("a", (0, 0, 10, 10))
        reg.add("b", (20, 20, 30, 30))
        self.assertEqual(hit_test(reg, 5, 5), "a")
        self.assertEqual(hit_test(reg, 25, 25), "b")
        self.assertIsNone(hit_test(reg, 15, 15))

    def test_hit_test_overlap_last_wins(self):
        reg = HitAreaRegistry()
        reg.add("under", (0, 0, 20, 20))
        reg.add("over", (5, 5, 15, 15))
        self.assertEqual(hit_test(reg, 10, 10), "over")
        self.assertEqual(hit_test(reg, 1, 1), "under")

    def test_clear_removes_all_areas(self):
        reg = HitAreaRegistry()
        reg.add("a", (0, 0, 10, 10))
        reg.clear()
        self.assertIsNone(hit_test(reg, 5, 5))

    def test_handle_tap_hits_area(self):
        reg = HitAreaRegistry()
        reg.add(("row", 2), (0, 40, 316, 57))
        events = [PointerEvent(x=10, y=45, kind="tap")]
        self.assertEqual(handle_tap(events, reg), ("row", 2))

    def test_handle_tap_ignores_down_move_up(self):
        reg = HitAreaRegistry()
        reg.add("btn", (0, 0, 10, 10))
        events = [
            PointerEvent(x=5, y=5, kind="down"),
            PointerEvent(x=5, y=5, kind="move"),
            PointerEvent(x=5, y=5, kind="up"),
        ]
        self.assertIsNone(handle_tap(events, reg))

    def test_handle_tap_miss_returns_none(self):
        reg = HitAreaRegistry()
        reg.add("btn", (0, 0, 10, 10))
        events = [PointerEvent(x=500, y=500, kind="tap")]
        self.assertIsNone(handle_tap(events, reg))

    def test_handle_tap_no_registry_is_noop(self):
        self.assertIsNone(handle_tap([PointerEvent(x=5, y=5, kind="tap")], None))


class DrainPointerEventsTests(unittest.TestCase):
    def test_drains_from_handler(self):
        handler = FakeInputHandler([PointerEvent(x=1, y=2, kind="tap")])
        events = drain_pointer_events(handler)
        self.assertEqual(len(events), 1)
        # Second call returns nothing left — mirrors poll-and-clear semantics.
        self.assertEqual(drain_pointer_events(handler), [])

    def test_no_pointer_support_returns_empty_list(self):
        self.assertEqual(drain_pointer_events(NoPointerInputHandler()), [])
        self.assertEqual(drain_pointer_events(None), [])


class ListScrollTests(unittest.TestCase):
    AREA = (0, 40, 316, 156)  # matches a typical LIST_TOP..LIST_BOT rect

    def test_wheel_up_scrolls_negative(self):
        scroller = ListScroll(row_h=18)
        events = [PointerEvent(x=0, y=0, kind="scroll", dy=1)]
        self.assertEqual(scroller.poll(events, self.AREA), -1)

    def test_wheel_down_scrolls_positive(self):
        scroller = ListScroll(row_h=18)
        events = [PointerEvent(x=0, y=0, kind="scroll", dy=-1)]
        self.assertEqual(scroller.poll(events, self.AREA), 1)

    def test_drag_outside_area_is_ignored(self):
        scroller = ListScroll(row_h=18)
        events = [
            PointerEvent(x=500, y=500, kind="down"),
            PointerEvent(x=500, y=400, kind="move"),  # 100px up, outside area
        ]
        self.assertEqual(scroller.poll(events, self.AREA), 0)

    def test_drag_up_scrolls_list_down_by_rows(self):
        scroller = ListScroll(row_h=18)
        events = [
            PointerEvent(x=100, y=100, kind="down"),
            PointerEvent(x=100, y=100 - 40, kind="move"),  # dragged finger up 40px
        ]
        # 40px / 18px-per-row = 2 whole rows; content follows the finger so
        # dragging up reveals items further down (positive delta).
        self.assertEqual(scroller.poll(events, self.AREA), 2)

    def test_drag_down_scrolls_list_up_by_rows(self):
        scroller = ListScroll(row_h=18)
        events = [
            PointerEvent(x=100, y=100, kind="down"),
            PointerEvent(x=100, y=100 + 36, kind="move"),  # dragged finger down 36px
        ]
        self.assertEqual(scroller.poll(events, self.AREA), -2)

    def test_partial_drag_accumulates_across_polls(self):
        scroller = ListScroll(row_h=18)
        # First move: 10px — not a full row yet.
        self.assertEqual(
            scroller.poll(
                [PointerEvent(x=100, y=100, kind="down"), PointerEvent(x=100, y=90, kind="move")],
                self.AREA,
            ),
            0,
        )
        # Second move: another 10px — now 20px total, crosses one row (18px).
        self.assertEqual(scroller.poll([PointerEvent(x=100, y=80, kind="move")], self.AREA), 1)

    def test_up_ends_drag(self):
        scroller = ListScroll(row_h=18)
        scroller.poll([PointerEvent(x=100, y=100, kind="down")], self.AREA)
        scroller.poll([PointerEvent(x=100, y=100, kind="up")], self.AREA)
        # Move after "up" (drag ended) must not scroll anything.
        result = scroller.poll([PointerEvent(x=100, y=50, kind="move")], self.AREA)
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
