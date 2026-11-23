import io
import os
import time

from PIL import Image, ImageDraw, ImageFont
import api
import cache
import state
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, FONT_PATH, FONT_SIZE_SM,
    KEY_ESC, KEY_ENTER,
)
from display import blit


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _draw_status(message, color=COLOR_DIM):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    bbox = draw.textbbox((0, 0), message, font=font)
    tx   = (SCREEN_W - (bbox[2] - bbox[0])) // 2
    ty   = (SCREEN_H - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), message, fill=color, font=font)
    blit(img)


def _fit_image(img):
    """Resize image to fill 320×170, maintaining aspect ratio with black bars."""
    src_w, src_h = img.size
    scale = min(SCREEN_W / src_w, SCREEN_H / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img   = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    x = (SCREEN_W - new_w) // 2
    y = (SCREEN_H - new_h) // 2
    canvas.paste(img, (x, y))
    return canvas


def run(firmware, input_handler=None):
    """
    Displays the firmware cover image full-screen.
    Loads from disk cache when available; downloads and caches otherwise.
    Any key returns.
    """
    cover = firmware.get("cover", "")
    name  = firmware.get("name", "")
    if not cover:
        return

    cached = cache.cover_path(name)

    if os.path.exists(cached):
        try:
            img = Image.open(cached).convert("RGB")
            blit(_fit_image(img))
        except Exception:
            pass
        else:
            _wait_key(input_handler)
            return

    if state.offline_mode:
        _draw_status("No cover (offline)", color=COLOR_GRAY)
        time.sleep(2)
        return

    _draw_status("Loading cover...")

    try:
        import requests
        url  = api.cover_image_url(cover)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.content
        # Persist for offline use
        try:
            with open(cached, "wb") as f:
                f.write(data)
        except OSError:
            pass
        img = Image.open(io.BytesIO(data)).convert("RGB")
        blit(_fit_image(img))
    except Exception as e:
        _draw_status(f"Error: {str(e)[:36]}", color=COLOR_GRAY)
        time.sleep(2)
        return

    _wait_key(input_handler)


def _wait_key(input_handler):
    """Waits for any keypress OR any tap — this screen has no discrete
    button, so a tap anywhere (no hit-testing needed) is the touch
    equivalent of "press any key"."""
    if not input_handler:
        time.sleep(2)
        return
    while True:
        time.sleep(0.05)
        if input_handler.last_key() is not None:
            return
        poll = getattr(input_handler, "poll_pointer_events", None)
        if poll is not None and any(ev.kind == "tap" for ev in poll()):
            return
