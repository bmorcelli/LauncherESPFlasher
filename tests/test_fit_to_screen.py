"""Deterministic unit tests for hal.display_backend.fit_to_screen.

No pygame/evdev/framebuffer involved — pure PIL.Image transforms.
Run with:  python -m unittest tests.test_fit_to_screen  (from repo root,
with src/ on sys.path — see sys.path bootstrap below).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image

from hal.display_backend import fit_to_screen

LOGICAL_W, LOGICAL_H = 320, 170
CENTER = (LOGICAL_W // 2, LOGICAL_H // 2)  # (160, 85) — exact center pixel


def _make_logical_image():
    """Black 320x170 image with a single red marker pixel at the exact
    center, and small corner markers to sanity-check orientation."""
    img = Image.new("RGB", (LOGICAL_W, LOGICAL_H), (0, 0, 0))
    img.putpixel(CENTER, (255, 0, 0))
    img.putpixel((0, 0), (0, 255, 0))                       # top-left: green
    img.putpixel((LOGICAL_W - 1, LOGICAL_H - 1), (0, 0, 255))  # bottom-right: blue
    return img


def _find_pixel(img, color):
    """Returns the (x, y) of the first pixel matching `color`, or None."""
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y] == color:
                return (x, y)
    return None


class FitToScreenTests(unittest.TestCase):
    def test_identity_is_noop(self):
        img = _make_logical_image()
        out = fit_to_screen(img, LOGICAL_W, LOGICAL_H, rotation=0)
        # Must be the exact same object (no resize/copy) — CARDPUTERZERO path.
        self.assertIs(out, img)

    def test_same_aspect_upscale_no_letterbox(self):
        img = _make_logical_image()
        screen_w, screen_h = LOGICAL_W * 2, LOGICAL_H * 2  # exact 2x, same aspect
        out = fit_to_screen(img, screen_w, screen_h, rotation=0)

        self.assertEqual(out.size, (screen_w, screen_h))
        # No letterbox expected: corners of the canvas must not be black.
        self.assertNotEqual(out.getpixel((0, 0)), (0, 0, 0))
        self.assertNotEqual(out.getpixel((screen_w - 1, screen_h - 1)), (0, 0, 0))

        red = _find_pixel(out, (255, 0, 0))
        self.assertIsNotNone(red, "center marker missing after upscale")
        self.assertAlmostEqual(red[0], screen_w // 2, delta=2)
        self.assertAlmostEqual(red[1], screen_h // 2, delta=2)

    def test_different_aspect_letterboxes_and_centers(self):
        img = _make_logical_image()
        screen_w, screen_h = 400, 300  # wider+taller ratio than 320x170
        out = fit_to_screen(img, screen_w, screen_h, rotation=0)

        self.assertEqual(out.size, (screen_w, screen_h))

        red = _find_pixel(out, (255, 0, 0))
        self.assertIsNotNone(red, "center marker missing after letterbox")
        self.assertAlmostEqual(red[0], screen_w // 2, delta=3)
        self.assertAlmostEqual(red[1], screen_h // 2, delta=3)

        green = _find_pixel(out, (0, 255, 0))
        blue = _find_pixel(out, (0, 0, 255))
        self.assertIsNotNone(green)
        self.assertIsNotNone(blue)
        # Orientation preserved: top-left marker stays left-of/above the
        # bottom-right marker even after uniform scale + centering.
        self.assertLess(green[0], blue[0])
        self.assertLess(green[1], blue[1])

        # Letterbox bars (top/bottom, since content is wider than 4:3-ish
        # screen relative to its own aspect) must be pure black.
        self.assertEqual(out.getpixel((screen_w // 2, 0)), (0, 0, 0))
        self.assertEqual(out.getpixel((screen_w // 2, screen_h - 1)), (0, 0, 0))

    def test_rotation_90_fits_and_centers(self):
        img = _make_logical_image()
        screen_w, screen_h = 568, 1232  # T-Display-CM0 preview: portrait
        out = fit_to_screen(img, screen_w, screen_h, rotation=90)

        self.assertEqual(out.size, (screen_w, screen_h))

        red = _find_pixel(out, (255, 0, 0))
        self.assertIsNotNone(red, "center marker missing after rotate+scale")
        # Rotation is about the image center, so the center marker must still
        # land near the canvas center regardless of rotation angle. A wider
        # tolerance is used here because expand=True rotation plus rounding
        # of non-square scale factors compounds slightly more than the
        # unrotated cases above.
        self.assertAlmostEqual(red[0], screen_w // 2, delta=6)
        self.assertAlmostEqual(red[1], screen_h // 2, delta=6)

    def test_no_crash_on_tiny_screen(self):
        img = _make_logical_image()
        out = fit_to_screen(img, 8, 8, rotation=0)
        self.assertEqual(out.size, (8, 8))


if __name__ == "__main__":
    unittest.main()
