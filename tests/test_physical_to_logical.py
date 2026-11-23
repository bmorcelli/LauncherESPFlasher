"""Deterministic unit tests for hal.display_backend.physical_to_logical —
the inverse of fit_to_screen. No pygame/evdev involved.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hal.display_backend import fit_to_screen, physical_to_logical
from PIL import Image

LOGICAL_W, LOGICAL_H = 320, 170


class PhysicalToLogicalTests(unittest.TestCase):
    def test_identity(self):
        # CARDPUTERZERO path: screen == logical, rotation 0 → passthrough.
        result = physical_to_logical(100, 50, LOGICAL_W, LOGICAL_H, LOGICAL_W, LOGICAL_H, rotation=0)
        self.assertEqual(result, (100, 50))

    def test_upscale_2x_no_letterbox(self):
        screen_w, screen_h = LOGICAL_W * 2, LOGICAL_H * 2
        # A logical point (160, 85) should land near physical (320, 170).
        result = physical_to_logical(320, 170, LOGICAL_W, LOGICAL_H, screen_w, screen_h, rotation=0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 160, delta=1)
        self.assertAlmostEqual(result[1], 85, delta=1)

    def test_letterbox_border_returns_none(self):
        screen_w, screen_h = 400, 300  # taller aspect than 320x170 -> top/bottom bars
        # Top-left corner of the physical screen is inside the letterbox bar.
        result = physical_to_logical(0, 0, LOGICAL_W, LOGICAL_H, screen_w, screen_h, rotation=0)
        self.assertIsNone(result)

    def test_center_roundtrip_all_rotations(self):
        """For each supported rotation, the logical center point should map
        forward (via fit_to_screen, using a marker image) to roughly the
        physical screen center, and physical_to_logical should map that
        physical center back to roughly the logical center — consistent
        with the forward/inverse pair being mirror images of each other."""
        screen_w, screen_h = 568, 1232
        for rotation in (0, 90, 180, 270):
            img = Image.new("RGB", (LOGICAL_W, LOGICAL_H), (0, 0, 0))
            marker = (LOGICAL_W // 2, LOGICAL_H // 2)
            img.putpixel(marker, (255, 0, 0))

            forward = fit_to_screen(img, screen_w, screen_h, rotation=rotation)
            px = forward.load()
            found = None
            for y in range(forward.height):
                for x in range(forward.width):
                    if px[x, y] == (255, 0, 0):
                        found = (x, y)
                        break
                if found:
                    break
            self.assertIsNotNone(found, f"marker missing for rotation={rotation}")

            back = physical_to_logical(
                found[0], found[1], LOGICAL_W, LOGICAL_H, screen_w, screen_h, rotation=rotation
            )
            self.assertIsNotNone(back, f"round-trip returned None for rotation={rotation}")
            self.assertAlmostEqual(back[0], marker[0], delta=3, msg=f"rotation={rotation}")
            self.assertAlmostEqual(back[1], marker[1], delta=3, msg=f"rotation={rotation}")

    def test_known_corner_rotation_90(self):
        """Cross-check _inverse_rotate against the empirically observed
        PIL rotate(90, expand=True) mapping for a 320x170 image: the
        original top-right corner (319, 0) ends up at rotated-space (0, 0)."""
        screen_w, screen_h = LOGICAL_H, LOGICAL_W  # exact rotated size, no scaling
        result = physical_to_logical(0, 0, LOGICAL_W, LOGICAL_H, screen_w, screen_h, rotation=90)
        self.assertEqual(result, (LOGICAL_W - 1, 0))


if __name__ == "__main__":
    unittest.main()
