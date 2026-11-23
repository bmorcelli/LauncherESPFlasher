"""Deterministic unit tests for ui_keyboard's layout/label logic.

blit() is monkeypatched to a no-op so _draw() can run without touching a
real framebuffer/pygame window.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ui_keyboard
from config import SCREEN_W, SCREEN_H
from ui_hitareas import HitAreaRegistry, hit_test


class KeyLabelTests(unittest.TestCase):
    def test_letter_uppercases_with_shift(self):
        self.assertEqual(ui_keyboard._key_label("q", shift=False), "q")
        self.assertEqual(ui_keyboard._key_label("q", shift=True), "Q")

    def test_shift_key_shows_arrow_regardless_of_state(self):
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_SHIFT, False), ui_keyboard._SHIFT_ARROW)
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_SHIFT, True), ui_keyboard._SHIFT_ARROW)

    def test_number_row_becomes_symbols_with_shift(self):
        expected = {
            "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
            "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
        }
        for digit, symbol in expected.items():
            self.assertEqual(ui_keyboard._key_label(digit, shift=False), digit)
            self.assertEqual(ui_keyboard._key_label(digit, shift=True), symbol)
            self.assertEqual(ui_keyboard._shifted_char(digit), symbol)

    def test_special_keys_have_stable_labels(self):
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_BACKSPACE, False), "<-")
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_DONE, False), "OK")
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_CANCEL, False), "Esc")
        self.assertEqual(ui_keyboard._key_label(ui_keyboard.KEY_SPACE, False), "space")


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self._orig_blit = ui_keyboard.blit
        ui_keyboard.blit = lambda img: None  # avoid touching a real framebuffer

    def tearDown(self):
        ui_keyboard.blit = self._orig_blit

    def _draw_and_get_registry(self, text="", shift=False):
        registry = HitAreaRegistry()
        ui_keyboard._draw(text, shift, cursor_on=True, registry=registry, placeholder="filter...")
        return registry

    def test_every_key_registers_a_hit_area_within_screen_bounds(self):
        registry = self._draw_and_get_registry()
        self.assertGreater(len(registry._areas), 0)
        for area in registry._areas:
            x0, y0, x1, y1 = area.rect
            self.assertGreaterEqual(x0, 0)
            self.assertGreaterEqual(y0, 0)
            self.assertLessEqual(x1, SCREEN_W)
            self.assertLessEqual(y1, SCREEN_H)
            self.assertLess(x0, x1)
            self.assertLess(y0, y1)

    def test_all_letters_and_controls_present_and_hittable(self):
        registry = self._draw_and_get_registry()
        ids = {area.id for area in registry._areas}
        for letter in "qwertyuiopasdfghjklzxcvbnm1234567890":
            self.assertIn(letter, ids, f"missing key {letter!r}")
        for control in (
            ui_keyboard.KEY_BACKSPACE,
            ui_keyboard.KEY_SHIFT,
            ui_keyboard.KEY_SPACE,
            ui_keyboard.KEY_DONE,
            ui_keyboard.KEY_CANCEL,
        ):
            self.assertIn(control, ids)

    def test_no_overlapping_keys_on_same_row(self):
        """A tap at the center of each key's rect must resolve back to that
        same key — catches accidental overlap/misalignment in the grid."""
        registry = self._draw_and_get_registry()
        for area in registry._areas:
            x0, y0, x1, y1 = area.rect
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            self.assertEqual(hit_test(registry, cx, cy), area.id)


if __name__ == "__main__":
    unittest.main()
