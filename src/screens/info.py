import os
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_TAB,
)
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap

HEADER_H = 22
LOCAL_BUILD_VERSION = "dev"

try:
    from build_info import BUILD_VERSION
except ImportError:
    BUILD_VERSION = LOCAL_BUILD_VERSION

_LINKS = [
    ("Repo",    "https://github.com/bmorcelli/LauncherESPFlasher"),
    ("Hub",     "https://launcherhub.net/"),
    ("Support", "https://buymeacoffee.com/bmorcelliz"),
]

_qr_cache: dict = {}


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _make_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=3,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        return qr.make_image(fill_color=(0, 200, 0), back_color=(0, 0, 0)).convert("RGB")
    except Exception:
        return None


def _get_qr(url):
    if url not in _qr_cache:
        _qr_cache[url] = _make_qr(url)
    return _qr_cache[url]


def _draw(selected, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    # Header
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 5), "ABOUT", fill=COLOR_GREEN, font=font)

    content_bot = SCREEN_H - NAVBAR_H  # 156

    # QR panel on the right
    qr_panel_x = 210
    qr_url = _LINKS[selected][1]
    qr_img = _get_qr(qr_url)
    if qr_img:
        qw, qh = qr_img.size
        # Fit into panel without upscaling, keep aspect
        max_dim = min(SCREEN_W - qr_panel_x - 4, content_bot - HEADER_H - 4)
        if qw > max_dim or qh > max_dim:
            factor = max_dim / max(qw, qh)
            qw = int(qw * factor)
            qh = int(qh * factor)
            qr_img = qr_img.resize((qw, qh), Image.NEAREST)
        qx = qr_panel_x + (SCREEN_W - qr_panel_x - 4 - qw) // 2
        qy = HEADER_H + (content_bot - HEADER_H - qh) // 2
        img.paste(qr_img, (qx, qy))
    else:
        # Fallback: show short URL text
        short = qr_url.replace("https://", "")
        draw.rectangle([qr_panel_x, HEADER_H + 4, SCREEN_W - 2, content_bot - 2],
                       fill=(0, 10, 0), outline=COLOR_GRAY)
        ty = HEADER_H + 10
        max_w = SCREEN_W - qr_panel_x - 10
        words, line = short.split("/"), ""
        for part in [p for p in short.replace(".", " . ").split() if p]:
            candidate = (line + " " + part).strip()
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_w:
                line = candidate
            else:
                if line:
                    draw.text((qr_panel_x + 4, ty), line, fill=COLOR_GRAY, font=font)
                    ty += 13
                line = part
        if line:
            draw.text((qr_panel_x + 4, ty), line, fill=COLOR_GRAY, font=font)

    # Left column: app info
    y = HEADER_H + 6
    draw.text((6, y), "Launcher ESP Flasher", fill=COLOR_GREEN, font=font)
    y += 14
    draw.text((6, y), "An ESP flasher for", fill=COLOR_DIM, font=font)
    y += 13
    draw.text((6, y), "Cardputer Zero", fill=COLOR_DIM, font=font)
    y += 13
    draw.text((6, y), "by bmorcelli", fill=(0, 160, 0), font=font)
    y += 13
    draw.text((6, y), f"version {BUILD_VERSION}", fill=COLOR_DIM, font=font)
    y += 18

    # Separator
    draw.line([4, y, qr_panel_x - 8, y], fill=(0, 40, 0))
    y += 6

    # Link buttons
    for i, (label, url) in enumerate(_LINKS):
        sel = (i == selected)
        bg  = (0, 45, 0) if sel else (0, 12, 0)
        fg  = COLOR_GREEN if sel else COLOR_DIM
        bw  = draw.textbbox((0, 0), label, font=font)[2] + 10
        draw.rectangle([6, y, 6 + bw, y + 14],
                       fill=bg, outline=COLOR_GREEN if sel else (0, 35, 0))
        draw.text((11, y + 2), label, fill=fg, font=font)
        if registry is not None:
            registry.add(("link", i), (6, y, 6 + bw, y + 14))
        y += 18

    draw_navbar(draw, font, registry)
    blit(img)


def run(input_handler=None):
    """Info / About screen. ESC, Enter or tapping the navbar closes;
    tapping a link button previews its QR code (same as arrow-key focus)."""
    selected = 0
    registry = HitAreaRegistry()

    def _refresh():
        registry.clear()
        _draw(selected, registry)

    _refresh()

    while True:
        time.sleep(0.05)
        if not input_handler:
            continue

        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return
            elif isinstance(tapped, tuple) and tapped[0] == "link":
                selected = tapped[1]
                _refresh()
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key in (KEY_ESC, KEY_ENTER):
            return
        elif key in (KEY_UP, KEY_LEFT):
            if selected > 0:
                selected -= 1
                _refresh()
        elif key in (KEY_DOWN, KEY_RIGHT, KEY_TAB):
            if selected < len(_LINKS) - 1:
                selected += 1
                _refresh()
