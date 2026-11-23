import os
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, COLOR_ORANGE, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_TAB,
)
import cache
import flasher
import state
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap, ListScroll

HEADER_H = 22
BTN_H    = 20
BTN_Y    = SCREEN_H - BTN_H - NAVBAR_H - 2
CONTENT_H = BTN_Y - HEADER_H - 4
LINE_H   = FONT_SIZE_SM + 4
DESC_Y   = HEADER_H + 6

FOCUS_COVER   = 0
FOCUS_VERSION = 1
FOCUS_FLASH   = 2
FOCUS_DESC    = 3

MAX_DESC_LINES = 6
DESC_MAX_W     = SCREEN_W - 22   # narrower to leave room for scroll indicators
DESC_H         = MAX_DESC_LINES * LINE_H

COLOR_BY_AUTHOR = (0, 160, 0)


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words  = (text or "").split()
    lines  = []
    cur    = ""
    for word in words:
        test = (cur + " " + word).strip()
        w    = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _sorted_versions(fw):
    versions = fw.get("versions", [])
    if not versions:
        return []
    return sorted(versions, key=lambda v: v.get("published_at", ""), reverse=True)


def _current_version(fw):
    sel = fw.get("_selected_version")
    if sel:
        return sel
    versions = _sorted_versions(fw)
    return versions[0] if versions else {}


def _all_desc_lines(fw):
    img  = Image.new("RGB", (1, 1), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font()
    return _wrap(draw, fw.get("description", ""), font, DESC_MAX_W)


def _draw(fw, focus, desc_offset=0, all_lines=None, app_format=False, dl=False, registry=None):
    """dl=True means the current version is already downloaded (show FLASH); False → show DOWNLOAD."""
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4

    # Header
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    author = fw.get("author", "")
    by_text = f"by {author}" if author else ""

    by_w  = draw.textbbox((0, 0), by_text, font=font)[2] if by_text else 0
    gap   = 8
    name_max_w = SCREEN_W - 12 - (by_w + gap if by_text else 0)
    name = fw.get("name", "Unknown")
    while draw.textbbox((0, 0), name, font=font)[2] > name_max_w and len(name) > 4:
        name = name[:-1]

    draw.text((6, 4), name, fill=COLOR_GREEN, font=font)
    if by_text:
        draw.text((SCREEN_W - by_w - 6, 4), by_text, fill=COLOR_BY_AUTHOR, font=font)

    y = HEADER_H + 6

    # Description
    if all_lines is None:
        all_lines = _all_desc_lines(fw)

    has_overflow     = len(all_lines) > MAX_DESC_LINES
    can_scroll_up    = desc_offset > 0
    can_scroll_down  = desc_offset + MAX_DESC_LINES < len(all_lines)
    visible_lines    = all_lines[desc_offset : desc_offset + MAX_DESC_LINES]

    desc_y  = y
    desc_h  = MAX_DESC_LINES * lh
    ind_x   = SCREEN_W - 10
    ind_col = COLOR_GREEN if focus == FOCUS_DESC else COLOR_DIM

    if has_overflow:
        border_col = COLOR_GREEN if focus == FOCUS_DESC else (0, 40, 0)
        draw.rectangle(
            [3, desc_y - 2, SCREEN_W - 4, desc_y + desc_h + 1],
            outline=border_col,
        )
        if registry is not None:
            registry.add(FOCUS_DESC, (3, desc_y - 2, SCREEN_W - 4, desc_y + desc_h + 1))

    if can_scroll_up:
        mx = ind_x
        ty = desc_y + 1
        draw.polygon([(mx, ty), (mx - 4, ty + 6), (mx + 4, ty + 6)], fill=ind_col)

    if can_scroll_down:
        mx = ind_x
        by_ = desc_y + desc_h - 1
        draw.polygon([(mx - 4, by_ - 6), (mx + 4, by_ - 6), (mx, by_)], fill=ind_col)

    for line in visible_lines:
        draw.text((8, y), line, fill=COLOR_DIM, font=font)
        y += lh

    # Downloads count
    dl_count = fw.get("download", fw.get("downloads", 0))
    if dl_count:
        dl_y = max(desc_y + desc_h + 3, BTN_Y - FONT_SIZE_SM - 5)
        draw.text((6, dl_y), f"{dl_count:,} downloads", fill=(0, 80, 0), font=font)

    # Buttons
    has_cover = bool(fw.get("cover", ""))
    _sel_ver = fw.get("_selected_version")
    if _sel_ver:
        ver_label = (_sel_ver.get("version") or "?")[:9]
    else:
        _vlist = _sorted_versions(fw)
        if _vlist:
            ver_label = (_vlist[0].get("version") or "?")[:9]
        else:
            ver_label = (fw.get("version") or fw.get("tag") or "?")[:9]

    flash_label  = "FLASH" if dl else "DOWNLOAD"
    flash_accent = app_format and dl and focus == FOCUS_FLASH

    btns = [
        ("COVER",       has_cover,  FOCUS_COVER),
        (ver_label,     True,       FOCUS_VERSION),
        (flash_label,   True,       FOCUS_FLASH),
    ]

    btn_w = (SCREEN_W - 8 * 4) // 3
    for i, (label, enabled, foc) in enumerate(btns):
        bx = 8 + i * (btn_w + 8)
        by = BTN_Y
        if not enabled:
            border = COLOR_GRAY
            fg     = COLOR_GRAY
            bg     = COLOR_BG
        elif foc == focus:
            border = COLOR_ORANGE if flash_accent else COLOR_GREEN
            fg     = COLOR_ORANGE if flash_accent else COLOR_GREEN
            bg     = (30, 15, 0) if flash_accent else (0, 50, 0)
        else:
            border = (100, 55, 0) if flash_accent else COLOR_DIM
            fg     = (100, 55, 0) if flash_accent else COLOR_DIM
            bg     = COLOR_BG

        draw.rectangle([bx, by, bx + btn_w, by + BTN_H], fill=bg, outline=border)
        lw = draw.textbbox((0, 0), label, font=font)[2]
        lx = bx + (btn_w - lw) // 2
        ly = by + (BTN_H - FONT_SIZE_SM) // 2
        draw.text((lx, ly), label, fill=fg, font=font)

        if registry is not None and enabled:
            registry.add(foc, (bx, by, bx + btn_w, by + BTN_H))

    draw_navbar(draw, font, registry)
    blit(img)


def run(firmware, input_handler=None):
    """
    Shows the firmware detail screen.
    Returns the firmware dict with _action="flash" or _action="download",
    or None on ESC (back to firmware list).
    Ctrl+O toggles offline mode and redraws.
    """
    has_cover    = bool(firmware.get("cover", ""))
    all_lines    = _all_desc_lines(firmware)
    has_overflow = len(all_lines) > MAX_DESC_LINES
    desc_offset  = 0
    app_format   = flasher.is_app_format(_current_version(firmware))

    def _is_dl():
        ver = _current_version(firmware)
        return cache.is_downloaded(firmware.get("name", ""), ver.get("version", ""))

    def _cycle(has_cover, has_overflow):
        c = []
        if has_cover:
            c.append(FOCUS_COVER)
        c.append(FOCUS_VERSION)
        c.append(FOCUS_FLASH)
        if has_overflow:
            c.append(FOCUS_DESC)
        return c

    focus_cycle = _cycle(has_cover, has_overflow)
    focus = FOCUS_FLASH

    registry    = HitAreaRegistry()
    desc_scroll = ListScroll(LINE_H)
    desc_area   = (3, DESC_Y - 2, SCREEN_W - 4, DESC_Y + DESC_H + 1)

    def _refresh():
        registry.clear()
        _draw(firmware, focus, desc_offset, all_lines, app_format, _is_dl(), registry)

    def _scroll_desc(delta):
        """Moves the description scroll position by `delta` lines — shared
        by the Up/Down keys (while DESC is focused) and by dragging/
        wheeling over the description box (which also focuses it, so a
        drag works without a separate tap-to-focus step first)."""
        nonlocal desc_offset, focus
        if not has_overflow or delta == 0:
            return
        max_offset  = max(0, len(all_lines) - MAX_DESC_LINES)
        new_offset  = max(0, min(max_offset, desc_offset + delta))
        changed     = new_offset != desc_offset or focus != FOCUS_DESC
        desc_offset = new_offset
        focus       = FOCUS_DESC
        if changed:
            _refresh()

    def _activate_enter():
        """Runs whatever the currently-focused control does when
        activated — shared by the KEY_ENTER handler and by tapping the
        equivalent on-screen button. Returns the firmware dict (with
        _action set) to have run() return it, or None if handled in place."""
        nonlocal firmware, app_format, focus
        if focus == FOCUS_COVER and has_cover:
            from screens import cover_view
            cover_view.run(firmware, input_handler=input_handler)
            _refresh()
        elif focus == FOCUS_VERSION:
            from screens import version_select
            selected_ver = version_select.run(firmware, input_handler=input_handler)
            if selected_ver:
                firmware = dict(firmware)
                firmware["_selected_version"] = selected_ver
                app_format = flasher.is_app_format(selected_ver)
            _refresh()
        elif focus == FOCUS_FLASH:
            action = "flash" if _is_dl() else "download"
            return {**firmware, "_action": action}
        elif focus == FOCUS_DESC:
            focus = FOCUS_FLASH
            _refresh()
        return None

    _refresh()

    while True:
        time.sleep(0.05)

        if not input_handler:
            continue

        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        # Touch: hit-test any tap against the areas registered by the last
        # _refresh(). COVER/VERSION/FLASH reuse the exact same action as
        # keyboard focus+Enter; DESC just toggles scroll focus (Enter's
        # DESC branch does the same when already focused).
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return None
            elif tapped == FOCUS_DESC:
                focus = FOCUS_FLASH if focus == FOCUS_DESC else FOCUS_DESC
                _refresh()
            else:
                focus   = tapped
                outcome = _activate_enter()
                if outcome is not None:
                    return outcome
            continue

        # Drag/wheel over the description box scrolls it directly — no
        # tap-to-focus step required first.
        scroll_delta = desc_scroll.poll(events, desc_area)
        if scroll_delta:
            _scroll_desc(scroll_delta)
            continue

        # Check Ctrl+O before normal char handling
        ch = input_handler.next_char()
        if ch == '\x0f':  # Ctrl+O
            state.offline_mode = not state.offline_mode
            _refresh()
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            return None

        elif key in (KEY_TAB, KEY_RIGHT):
            idx   = focus_cycle.index(focus)
            focus = focus_cycle[(idx + 1) % len(focus_cycle)]
            _refresh()

        elif key == KEY_LEFT:
            idx   = focus_cycle.index(focus)
            focus = focus_cycle[(idx - 1) % len(focus_cycle)]
            _refresh()

        elif key == KEY_UP:
            if focus == FOCUS_DESC:
                if desc_offset > 0:
                    desc_offset -= 1
                    _refresh()
            elif has_overflow:
                focus = FOCUS_DESC
                _refresh()

        elif key == KEY_DOWN:
            if focus == FOCUS_DESC:
                if desc_offset + MAX_DESC_LINES < len(all_lines):
                    desc_offset += 1
                    _refresh()
            elif has_overflow:
                focus = FOCUS_DESC
                _refresh()

        elif key == KEY_ENTER:
            outcome = _activate_enter()
            if outcome is not None:
                return outcome
