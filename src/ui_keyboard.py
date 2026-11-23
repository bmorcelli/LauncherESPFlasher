"""Modal on-screen QWERTY keyboard for touch text entry.

Used when a text field (e.g. a list filter) is tapped on a touch-capable
device — a physical keyboard, if present, keeps working exactly as before
(typed characters and Enter/Esc are still read via the same InputHandler
methods every other screen uses); this widget is a purely additive touch
input path for devices where the only way to type is by tapping keys.
"""
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    FONT_PATH, FONT_SIZE_SM, KEY_ENTER, KEY_ESC,
)
from display import blit
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap

KEY_BACKSPACE = "\x08"
KEY_DONE      = "__KB_DONE__"
KEY_CANCEL    = "__KB_CANCEL__"
KEY_SHIFT     = "__KB_SHIFT__"
KEY_SPACE     = " "

_KB_TOP  = 20                 # header height (text preview)
_COLS    = 10
_KEY_W   = SCREEN_W // _COLS  # 32
_ROW_H   = 27

_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl") + [KEY_BACKSPACE],
    [KEY_SHIFT] + list("zxcvbnm") + [".", "-"],
]
_BOTTOM_ROW = [(KEY_CANCEL, 2), (KEY_SPACE, 6), (KEY_DONE, 2)]

# Shifted number row → symbols, like a real keyboard (1! 2@ 3# ...).
_NUM_SYMBOLS = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
}

_SHIFT_ARROW = "↑"  # ↑


def _font():
    import os
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _shifted_char(k):
    """What a regular key produces (or displays) while Shift is active."""
    if k in _NUM_SYMBOLS:
        return _NUM_SYMBOLS[k]
    return k.upper()


def _key_label(k, shift):
    if k == KEY_BACKSPACE:
        return "<-"
    if k == KEY_SHIFT:
        return _SHIFT_ARROW
    if k == KEY_DONE:
        return "OK"
    if k == KEY_CANCEL:
        return "Esc"
    if k == KEY_SPACE:
        return "space"
    return _shifted_char(k) if shift else k


def _draw(text, shift, cursor_on, registry, placeholder):
    registry.clear()
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    draw.rectangle([0, 0, SCREEN_W, _KB_TOP], fill=COLOR_DARK)
    display = text + ("_" if cursor_on else "")
    draw.text((6, 3), display if text else placeholder,
               fill=COLOR_GREEN if text else COLOR_DIM, font=font)

    y = _KB_TOP
    for row in _ROWS:
        n = len(row)
        x = (_COLS - n) * _KEY_W // 2 if n < _COLS else 0
        for k in row:
            w   = _KEY_W
            sel = (k == KEY_SHIFT and shift)
            draw.rectangle([x, y, x + w - 1, y + _ROW_H - 1],
                           outline=(0, 60, 0), fill=(0, 40, 0) if sel else (0, 15, 0))
            label = _key_label(k, shift)
            lw = draw.textbbox((0, 0), label, font=font)[2]
            draw.text((x + (w - lw) // 2, y + (_ROW_H - FONT_SIZE_SM) // 2),
                      label, fill=COLOR_GREEN, font=font)
            registry.add(k, (x, y, x + w - 1, y + _ROW_H - 1))
            x += w
        y += _ROW_H

    x = 0
    for kid, span in _BOTTOM_ROW:
        w = _KEY_W * span
        draw.rectangle([x, y, x + w - 1, y + _ROW_H - 1],
                       outline=(0, 60, 0), fill=(0, 15, 0))
        label = _key_label(kid, shift)
        lw = draw.textbbox((0, 0), label, font=font)[2]
        draw.text((x + (w - lw) // 2, y + (_ROW_H - FONT_SIZE_SM) // 2),
                  label, fill=COLOR_GREEN, font=font)
        registry.add(kid, (x, y, x + w - 1, y + _ROW_H - 1))
        x += w

    blit(img)


def run(input_handler, initial_text="", placeholder="Type to filter..."):
    """Shows the on-screen keyboard. Returns the entered text on
    OK/Enter, or None if cancelled (Esc/Cancel button) — same convention
    as every other modal screen.run() in this app."""
    text       = initial_text
    shift      = False
    cursor_on  = True
    last_blink = time.time()
    registry   = HitAreaRegistry()

    def _refresh():
        _draw(text, shift, cursor_on, registry, placeholder)

    _refresh()

    while True:
        now = time.time()
        if now - last_blink > 0.5:
            cursor_on  = not cursor_on
            last_blink = now
            _refresh()

        time.sleep(0.05)

        if not input_handler:
            continue

        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == KEY_CANCEL:
                return None
            elif tapped == KEY_DONE:
                return text
            elif tapped == KEY_BACKSPACE:
                text = text[:-1]
                _refresh()
            elif tapped == KEY_SHIFT:
                shift = not shift
                _refresh()
            elif tapped == KEY_SPACE:
                text += " "
                _refresh()
            else:
                text += _shifted_char(tapped) if shift else tapped
                shift = False  # one-shot shift, like most mobile keyboards
                _refresh()
            continue

        # Physical keyboard keeps working too — same next_char()/last_key()
        # convention every other screen uses.
        ch = input_handler.next_char()
        if ch is not None:
            if ch == '\x08':
                text = text[:-1]
            elif ch.isprintable():
                text += ch
            _refresh()
            continue

        key = input_handler.last_key()
        if key == KEY_ESC:
            return None
        if key == KEY_ENTER:
            return text
