"""Display backends: turn a PIL.Image frame into pixels on an actual screen.
Screens draw onto a fixed logical canvas; fit_to_screen() scales/rotates/
letterboxes it to the device's physical resolution before writing pixels."""
import struct
from abc import ABC, abstractmethod

from PIL import Image

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def fit_to_screen(img, screen_w, screen_h, rotation=0):
    """Scale+letterbox (and optionally rotate) a logical-resolution PIL.Image
    to fit exactly within screen_w x screen_h, preserving aspect ratio.

    No-op fast path: when the image already matches screen_w x screen_h and
    rotation is 0, the original image is returned unchanged (no resize, no
    copy) — this is the CARDPUTERZERO path.
    """
    if rotation == 0 and img.width == screen_w and img.height == screen_h:
        return img

    rotated = img.rotate(rotation, expand=True) if rotation % 360 else img
    rw, rh = rotated.size

    scale = min(screen_w / rw, screen_h / rh)
    new_w = max(1, round(rw * scale))
    new_h = max(1, round(rh * scale))
    resized = rotated.resize((new_w, new_h), Image.NEAREST)

    canvas = Image.new(img.mode, (screen_w, screen_h), (0, 0, 0))
    offset_x = (screen_w - new_w) // 2
    offset_y = (screen_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas


def _rotated_dims(logical_w, logical_h, rotation):
    return (logical_h, logical_w) if rotation in (90, 270) else (logical_w, logical_h)


def _inverse_rotate(u, v, rotation, logical_w, logical_h):
    """Maps a point (u, v) in rotated-canvas space (size given by
    _rotated_dims) back to the original logical (0..logical_w, 0..logical_h)
    space. Mirrors exactly what PIL's Image.rotate(angle, expand=True) does
    for angle in {0, 90, 180, 270} (verified empirically against
    Image.transpose, which is the fast path PIL takes for these angles)."""
    if rotation == 0:
        return u, v
    if rotation == 90:
        return logical_w - 1 - v, u
    if rotation == 180:
        return logical_w - 1 - u, logical_h - 1 - v
    if rotation == 270:
        return v, logical_h - 1 - u
    raise ValueError(f"unsupported rotation {rotation}; only 0/90/180/270 are supported")


def physical_to_logical(px, py, logical_w, logical_h, screen_w, screen_h, rotation=0):
    """Inverse of fit_to_screen: maps a physical-screen point (px, py) back
    to a logical-canvas point, or returns None if the point falls in the
    letterbox border (not over any actual content).

    Only rotation values of 0/90/180/270 are supported (the same set
    DeviceProfile.rotation is documented to use) — matches fit_to_screen's
    fast-path behavior for those angles exactly.
    """
    rotation = rotation % 360
    rw, rh = _rotated_dims(logical_w, logical_h, rotation)

    scale = min(screen_w / rw, screen_h / rh)
    new_w = max(1, round(rw * scale))
    new_h = max(1, round(rh * scale))
    offset_x = (screen_w - new_w) // 2
    offset_y = (screen_h - new_h) // 2

    if not (offset_x <= px < offset_x + new_w and offset_y <= py < offset_y + new_h):
        return None

    u = int((px - offset_x) * rw / new_w)
    v = int((py - offset_y) * rh / new_h)
    u = min(max(u, 0), rw - 1)
    v = min(max(v, 0), rh - 1)

    lx, ly = _inverse_rotate(u, v, rotation, logical_w, logical_h)
    lx = min(max(lx, 0), logical_w - 1)
    ly = min(max(ly, 0), logical_h - 1)
    return lx, ly


class DisplayBackend(ABC):
    @abstractmethod
    def blit(self, img):
        """Render a logical-resolution PIL.Image frame to the physical screen."""


class FramebufferDisplayBackend(DisplayBackend):
    def __init__(self, fb_device, screen_w, screen_h, rotation=0):
        self.fb_device = fb_device
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.rotation = rotation

    def blit(self, img):
        img = fit_to_screen(img, self.screen_w, self.screen_h, self.rotation)

        if HAS_NUMPY:
            arr = np.array(img, dtype=np.uint16)
            rgb565 = (
                ((arr[:, :, 0] >> 3) << 11) |
                ((arr[:, :, 1] >> 2) << 5)  |
                 (arr[:, :, 2] >> 3)
            )
            with open(self.fb_device, "wb") as fb:
                fb.write(rgb565.astype("<u2").tobytes())
        else:
            buf = bytearray(self.screen_w * self.screen_h * 2)
            idx = 0
            for y in range(self.screen_h):
                for x in range(self.screen_w):
                    r, g, b = img.getpixel((x, y))
                    pixel = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                    struct.pack_into("<H", buf, idx, pixel)
                    idx += 2
            with open(self.fb_device, "wb") as fb:
                fb.write(buf)


class PygameDisplayBackend(DisplayBackend):
    def __init__(self, screen_w, screen_h, rotation=0, caption="ESP Flasher [DEV]"):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.rotation = rotation
        self.caption = caption
        self._pg_screen = None

    def _ensure_pg(self):
        if self._pg_screen is not None:
            return
        import pygame
        pygame.display.init()
        self._pg_screen = pygame.display.set_mode((self.screen_w, self.screen_h))
        pygame.display.set_caption(self.caption)

    def blit(self, img):
        img = fit_to_screen(img, self.screen_w, self.screen_h, self.rotation)
        self._ensure_pg()
        import pygame
        surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
        self._pg_screen.blit(surface, (0, 0))
        pygame.display.flip()
