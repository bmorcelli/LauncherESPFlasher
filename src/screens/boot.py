import random
import time
import os

from PIL import Image, ImageDraw, ImageFont
from config import SCREEN_W, SCREEN_H, COLOR_BG, FONT_PATH
from display import blit

# Rain grid dimensions
CHAR_W = 8
CHAR_H = 13
COLS = SCREEN_W // CHAR_W   # 40 columns
ROWS = SCREEN_H // CHAR_H   # 13 rows

TRAIL_LEN = 8
TARGET_FPS = 15
MIN_DURATION = 1.5  # minimum seconds to show boot screen

# Trail colors: index 0 = head (brightest), index -1 = tail (darkest)
TRAIL_COLORS = [
    (180, 255, 180),  # head — near white-green
    (0,   255,   0),
    (0,   210,   0),
    (0,   160,   0),
    (0,   110,   0),
    (0,    70,   0),
    (0,    35,   0),
    (0,    15,   0),
]


def _rand_char():
    return chr(random.randint(33, 126))


class _Drop:
    def __init__(self, col):
        self.col = col
        self.row = random.randint(-ROWS, 0)
        self.speed = random.uniform(0.4, 1.2)   # rows per second × FPS
        self.chars = [_rand_char() for _ in range(TRAIL_LEN)]
        self._frac = 0.0

    def update(self, dt):
        self._frac += self.speed * dt * TARGET_FPS
        steps = int(self._frac)
        if steps:
            self.row += steps
            self._frac -= steps
            for _ in range(steps):
                self.chars.pop(0)
                self.chars.append(_rand_char())

    def done(self):
        return self.row - TRAIL_LEN > ROWS


def run(input_handler=None):
    import cache
    prefetch_thread = cache.start_prefetch()

    font_rain = (
        ImageFont.truetype(FONT_PATH, 10)
        if os.path.exists(FONT_PATH)
        else ImageFont.load_default()
    )
    font_title = (
        ImageFont.truetype(FONT_PATH, 32)
        if os.path.exists(FONT_PATH)
        else ImageFont.load_default()
    )
    font_sub = (
        ImageFont.truetype(FONT_PATH, 18)
        if os.path.exists(FONT_PATH)
        else ImageFont.load_default()
    )

    drops = [_Drop(c) for c in range(COLS)]
    start = time.time()
    last  = start

    while True:
        now     = time.time()
        elapsed = now - start
        dt      = now - last
        last    = now

        # Advance only when fetch is done AND minimum display time has passed
        if elapsed >= MIN_DURATION and not prefetch_thread.is_alive():
            break

        img = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
        draw = ImageDraw.Draw(img)

        for drop in drops:
            drop.update(dt)
            for i, ch in enumerate(drop.chars):
                row = drop.row - (TRAIL_LEN - 1 - i)
                if 0 <= row < ROWS:
                    draw.text(
                        (drop.col * CHAR_W, row * CHAR_H),
                        ch,
                        fill=TRAIL_COLORS[i],
                        font=font_rain,
                    )

        for i, drop in enumerate(drops):
            if drop.done():
                drops[i] = _Drop(drop.col)

        # "LAUNCHER" title with glow
        title = "LAUNCHER"
        sub = "ESP FLASHER"
        tbbox = draw.textbbox((0, 0), title, font=font_title)
        sbbox = draw.textbbox((0, 0), sub, font=font_sub)
        tw, th = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
        sw, sh = sbbox[2] - sbbox[0], sbbox[3] - sbbox[1]
        gap = 6
        block_h = th + gap + sh
        tx = (SCREEN_W - tw) // 2
        ty = (SCREEN_H - block_h) // 2
        sx = (SCREEN_W - sw) // 2
        sy = ty + th + gap

        for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, -2), (0, 2)):
            draw.text((tx + ox, ty + oy), title, fill=(0, 60, 0), font=font_title)
        draw.text((tx, ty), title, fill=(0, 255, 0), font=font_title)

        for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            draw.text((sx + ox, sy + oy), sub, fill=(0, 40, 0), font=font_sub)
        draw.text((sx, sy), sub, fill=(0, 180, 0), font=font_sub)

        blit(img)

        frame_time = time.time() - now
        sleep = (1.0 / TARGET_FPS) - frame_time
        if sleep > 0:
            time.sleep(sleep)
