import os
import time

from PIL import Image, ImageDraw, ImageFont
import cache
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC,
)
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap

HEADER_H  = 22
LINE_H    = 14
CONTENT_Y = 26

_PAGES = [
    ("NAVIGATION", "1/3", [
        (COLOR_GREEN, "ARROW KEYS"),
        (None,        ""),
        (COLOR_DIM,   "FN + F    Move up in list"),
        (COLOR_DIM,   "FN + X    Move down in list"),
        (COLOR_DIM,   "FN + Z    Previous page / back"),
        (COLOR_DIM,   "FN + C    Next page / forward"),
    ]),
    ("ACTIONS", "2/3", [
        (COLOR_GREEN, "CONTROLS"),
        (None,        ""),
        (COLOR_DIM,   "Tab / Next    Switch focus"),
        (COLOR_DIM,   "Enter / OK    Select / change sort"),
        (COLOR_DIM,   "ESC           Back / clear filter"),
        (COLOR_DIM,   "Type text     Open filter field"),
    ]),
    ("SHORTCUTS", "3/3", [
        (COLOR_GREEN, "KEYBOARD SHORTCUTS"),
        (None,        ""),
        (COLOR_DIM,   "Ctrl + O   Toggle offline mode"),
        (COLOR_DIM,   "Ctrl + R   Refresh lists (online)"),
        (COLOR_DIM,   "Ctrl + H   Show this guide"),
    ]),
]

_N_PAGES = len(_PAGES)


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _draw(page_idx, option, registry=None):
    title, num, lines = _PAGES[page_idx]

    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    # Header
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 5), f"GUIDE {num}  -  {title}", fill=COLOR_GREEN, font=font)

    # Content lines
    y = CONTENT_Y
    for color, text in lines:
        if color is not None and text:
            draw.text((10, y), text, fill=color, font=font)
        y += LINE_H

    is_last = (page_idx == _N_PAGES - 1)
    hint_y  = SCREEN_H - NAVBAR_H - LINE_H - 4   # 138

    if is_last:
        # Buttons row (above hint)
        btn_y = hint_y - LINE_H - 8               # 116

        btn0 = "  Close  "
        btn1 = "  Don't show again  "
        b0_w = draw.textbbox((0, 0), btn0, font=font)[2] + 2
        b1_w = draw.textbbox((0, 0), btn1, font=font)[2] + 2
        b0_x = 10
        b1_x = b0_x + b0_w + 10

        for i, (bx, bw, btxt) in enumerate([(b0_x, b0_w, btn0), (b1_x, b1_w, btn1)]):
            sel = (i == option)
            draw.rectangle(
                [bx, btn_y, bx + bw, btn_y + LINE_H + 4],
                fill=(0, 50, 0) if sel else (0, 10, 0),
                outline=COLOR_GREEN if sel else (0, 40, 0),
            )
            draw.text((bx + 1, btn_y + 2), btxt,
                      fill=COLOR_GREEN if sel else COLOR_DIM, font=font)
            if registry is not None:
                registry.add(("option", i), (bx, btn_y, bx + bw, btn_y + LINE_H + 4))

        # Selection hint
        hint = "Left/Right: select   Enter: confirm"
        draw.text((10, hint_y), hint, fill=(0, 45, 0), font=font)
    else:
        # Page navigation arrows — real tap targets, not just hint text
        if page_idx > 0:
            back_label = "< Back"
            bw = draw.textbbox((0, 0), back_label, font=font)[2]
            draw.text((10, hint_y), back_label, fill=(0, 45, 0), font=font)
            if registry is not None:
                registry.add("prev_page", (6, hint_y - 2, 10 + bw + 4, hint_y + LINE_H))

        next_label = "Next >"
        fw = draw.textbbox((0, 0), next_label, font=font)[2]
        nx = SCREEN_W - fw - 10
        draw.text((nx, hint_y), next_label, fill=(0, 45, 0), font=font)
        if registry is not None:
            registry.add("next_page", (nx - 4, hint_y - 2, SCREEN_W - 4, hint_y + LINE_H))

    draw_navbar(draw, font, registry)
    blit(img)


def run(input_handler=None):
    """Display the tutorial. Blocks until user closes it."""
    page   = 0
    option = 0   # 0 = Close, 1 = Don't show again

    registry = HitAreaRegistry()

    def _refresh():
        registry.clear()
        _draw(page, option, registry)

    def _go_back():
        """Same behavior as pressing ESC — shared with tapping the navbar's
        back area. Returns True if run() should return (close the guide)."""
        nonlocal page
        if page == _N_PAGES - 1:
            return True
        if page > 0:
            page -= 1
            _refresh()
            return False
        return True

    def _go_next():
        nonlocal page
        page += 1
        _refresh()

    def _activate_option(opt):
        """Selects and immediately confirms a last-page button — shared by
        tapping it directly (one tap = decide, like other Yes/No dialogs)."""
        if opt == 1:
            cache.dismiss_tutorial()
        return True

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
                if _go_back():
                    return
            elif tapped == "next_page":
                _go_next()
            elif tapped == "prev_page":
                _go_back()
            elif isinstance(tapped, tuple) and tapped[0] == "option":
                option = tapped[1]
                if _activate_option(option):
                    return
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        is_last = (page == _N_PAGES - 1)

        if is_last:
            if key == KEY_LEFT:
                if option == 1:
                    option = 0
                    _refresh()
                else:
                    page -= 1
                    _refresh()
            elif key == KEY_RIGHT:
                if option < 1:
                    option += 1
                    _refresh()
            elif key == KEY_ESC:
                return
            elif key == KEY_ENTER:
                if _activate_option(option):
                    return
        else:
            if key in (KEY_RIGHT, KEY_ENTER):
                _go_next()
            elif key in (KEY_LEFT, KEY_ESC):
                if _go_back():
                    return
