"""Filesystem browser that returns the path of a selected .bin file, or None."""
import os
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_ENTER, KEY_ESC,
)
import icons
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap, ListScroll

HEADER_H  = 22
PATH_H    = 15
LIST_TOP  = HEADER_H + PATH_H
ROW_H     = 16
LIST_BOT  = SCREEN_H - NAVBAR_H
LIST_W    = SCREEN_W  # rows span full width; scroll touch-zone overlaps the right edge
VISIBLE   = (LIST_BOT - LIST_TOP) // ROW_H   # typically 7
SCROLL_W  = 4

FOCUS_UP = "__UP_DIR__"  # header "up one directory" button


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _list_dir(path):
    """Return (folders, bin_files) sorted lists for directory path."""
    try:
        entries = os.listdir(path)
    except OSError:
        return [], []
    folders = sorted(
        e for e in entries
        if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")
    )
    files = sorted(
        e for e in entries
        if e.lower().endswith(".bin") and os.path.isfile(os.path.join(path, e))
    )
    return folders, files


def _build_items(cwd):
    """Return list of (label, is_dir, full_path) for current directory."""
    items = []
    parent = os.path.dirname(cwd)
    if parent != cwd:
        items.append(("../", True, parent))
    folders, files = _list_dir(cwd)
    items += [(f + "/", True,  os.path.join(cwd, f)) for f in folders]
    items += [(f,        False, os.path.join(cwd, f)) for f in files]
    return items


def _trunc_left(draw, font, text, max_w):
    """Shorten a path by removing leading segments until it fits."""
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    sep = os.sep
    parts = text.split(sep)
    while len(parts) > 2:
        parts.pop(1)
        candidate = sep.join(["~"] + parts[1:])
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_w:
            return candidate
    return ("~" + sep + parts[-1])[:30]


def _trunc_right(draw, font, text, max_w):
    """Truncate label on the right with ~."""
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    while len(text) > 3 and draw.textbbox((0, 0), text[:-1] + "~", font=font)[2] > max_w:
        text = text[:-1]
    return text[:-1] + "~"


def _draw(cwd, items, selected, offset, chip_label=None, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    # Header
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 4), "FIND FIRMWARE BINARY", fill=COLOR_GREEN, font=font)
    if chip_label:
        lw = draw.textbbox((0, 0), chip_label, font=font)[2]
        chip_x = SCREEN_W - lw - 5
        draw.text((chip_x, 4), chip_label, fill=COLOR_DIM, font=font)
    else:
        chip_x = SCREEN_W

    # "Up one directory" button — the only touch affordance this screen
    # doesn't already show as a plain text row, so it needs a visible icon
    # (mirrors what ESC already does: go to parent dir, or exit at root).
    _IS = 14
    _IG = 4
    _IY = (HEADER_H - _IS) // 2
    up_x = chip_x - _IG - _IS
    icons.paste_icon(img, icons.up_icon(COLOR_GREEN, _IS), up_x, _IY)
    if registry is not None:
        registry.add(FOCUS_UP, (up_x, _IY, up_x + _IS, _IY + _IS))

    # Path bar
    draw.rectangle([0, HEADER_H, SCREEN_W, HEADER_H + PATH_H], fill=(0, 10, 0))
    path_text = _trunc_left(draw, font, cwd, SCREEN_W - 8)
    draw.text((4, HEADER_H + 2), path_text, fill=(0, 80, 0), font=font)

    # List rows
    for i in range(VISIBLE):
        idx = offset + i
        if idx >= len(items):
            break
        label, is_dir, _ = items[idx]
        y   = LIST_TOP + i * ROW_H
        sel = (idx == selected)

        if sel:
            draw.rectangle([0, y, SCREEN_W - SCROLL_W - 2, y + ROW_H - 1],
                           fill=(0, 50, 0), outline=COLOR_GREEN)
            color  = COLOR_GREEN
            prefix = "> "
        else:
            color  = COLOR_DIM if is_dir else COLOR_GREEN
            prefix = "  "

        max_label_w = SCREEN_W - SCROLL_W - 16
        display = _trunc_right(draw, font, prefix + label, max_label_w)
        draw.text((6, y + 2), display, fill=color, font=font)

        if registry is not None:
            registry.add(("row", idx), (0, y, SCREEN_W - SCROLL_W - 2, y + ROW_H - 1))

    # Empty state
    if not items:
        msg = "No .bin files here"
        mw  = draw.textbbox((0, 0), msg, font=font)[2]
        draw.text(((SCREEN_W - mw) // 2, LIST_TOP + 20), msg, fill=COLOR_GRAY, font=font)

    # Scrollbar
    if len(items) > VISIBLE:
        track_h = LIST_BOT - LIST_TOP
        thumb_h = max(8, track_h * VISIBLE // len(items))
        thumb_y = LIST_TOP + track_h * offset // len(items)
        sx = SCREEN_W - SCROLL_W - 1
        draw.rectangle([sx, LIST_TOP, sx + SCROLL_W, LIST_BOT], fill=(0, 20, 0))
        draw.rectangle([sx, thumb_y, sx + SCROLL_W, thumb_y + thumb_h], fill=COLOR_DIM)

        if registry is not None:
            # Touch target wider than the thin visual bar (SCROLL_W) so
            # it's actually hittable. Top half scrolls up one row, bottom
            # half scrolls down one row.
            mid = LIST_TOP + track_h // 2
            registry.add(("scroll", -1), (SCREEN_W - 16, LIST_TOP, SCREEN_W, mid))
            registry.add(("scroll", 1),  (SCREEN_W - 16, mid, SCREEN_W, LIST_BOT))

    draw_navbar(draw, font, registry)
    blit(img)


def run(start_dir=None, input_handler=None, chip_label=None):
    """Browse the filesystem for a .bin file.
    Returns the absolute path of the selected file, or None if cancelled."""
    cwd = start_dir or os.path.expanduser("~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")

    items    = _build_items(cwd)
    selected = 0
    offset   = 0

    registry    = HitAreaRegistry()
    list_scroll = ListScroll(ROW_H)

    def _refresh():
        registry.clear()
        _draw(cwd, items, selected, offset, chip_label, registry)

    def _go_up():
        """Same logic as the KEY_ESC handler — shared with tapping the
        header's up-arrow icon and the navbar's back area. Returns True if
        run() should return None (at filesystem root), False if it just
        navigated to the parent directory."""
        nonlocal cwd, items, selected, offset
        parent = os.path.dirname(cwd)
        if parent == cwd:
            return True  # at filesystem root
        cwd      = parent
        items    = _build_items(cwd)
        selected = 0
        offset   = 0
        _refresh()
        return False

    def _activate(idx):
        """Enters a directory or returns a file path — shared by KEY_ENTER
        and by tapping a list row."""
        nonlocal cwd, items, selected, offset
        if idx is None or not items or idx >= len(items):
            return None
        label, is_dir, full_path = items[idx]
        if is_dir:
            cwd      = full_path
            items    = _build_items(cwd)
            selected = 0
            offset   = 0
            _refresh()
            return None
        return full_path

    def _scroll(delta):
        """Moves the list selection by `delta` rows — shared by the
        Up/Down keys, the scrollbar's touch zones, and ListScroll
        (wheel/drag)."""
        nonlocal selected, offset
        if not items or delta == 0:
            return
        new_selected = max(0, min(len(items) - 1, selected + delta))
        if new_selected == selected:
            return
        selected = new_selected
        if selected < offset:
            offset = selected
        elif selected >= offset + VISIBLE:
            offset = selected - VISIBLE + 1
        _refresh()

    _refresh()

    while True:
        time.sleep(0.05)

        if not input_handler:
            continue
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        # Touch/mouse: drain pointer events once, feed both tap hit-testing
        # and list scrolling (drag on real touch, wheel on desktop dev).
        events = drain_pointer_events(input_handler)

        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped in (NAV_BACK, FOCUS_UP):
                if _go_up():
                    return None
            elif isinstance(tapped, tuple) and tapped[0] == "row":
                result = _activate(tapped[1])
                if result is not None:
                    return result
            elif isinstance(tapped, tuple) and tapped[0] == "scroll":
                _scroll(tapped[1])
            continue

        scroll_delta = list_scroll.poll(events, (0, LIST_TOP, LIST_W, LIST_BOT))
        if scroll_delta:
            _scroll(scroll_delta)
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            if _go_up():
                return None

        elif key == KEY_UP:
            _scroll(-1)

        elif key == KEY_DOWN:
            _scroll(1)

        elif key == KEY_ENTER:
            if not items:
                continue
            result = _activate(selected)
            if result is not None:
                return result
