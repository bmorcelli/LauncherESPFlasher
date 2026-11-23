import os
import time

from PIL import Image, ImageDraw, ImageFont
import api
import state
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, COLOR_WHITE, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_TAB,
)
import icons
from display import blit
from ui import draw_connection_status, draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap, ListScroll
import ui_keyboard

HEADER_H    = 22
TOOLBAR_H   = 18
LIST_TOP    = HEADER_H + TOOLBAR_H
ROW_H       = 18
SCROLLBAR_W = 4
LIST_W      = SCREEN_W - SCROLLBAR_W - 2
LIST_BOT    = SCREEN_H - NAVBAR_H
VISIBLE     = (LIST_BOT - LIST_TOP) // ROW_H

SORT_MODES  = ["downloads", "published_at", "name"]
# Maps sort mode → (actual API field, reverse, default value for missing)
_SORT_CFG = {
    "downloads":    ("download",     True,  0),
    "published_at": ("published_at", True,  ""),
    "name":         ("name",         False, ""),
}
FOCUS_LIST    = 0
FOCUS_SORT    = 1
FOCUS_FILTER  = 2
FOCUS_REFRESH = 3   # ↻ refresh icon
FOCUS_INFO    = 4   # ℹ info/about
FOCUS_FILE    = 5   # file install
FOCUS_CONN    = 6   # wifi/online toggle
_N_FOCUS      = 7

COLOR_TOOLBAR_BG  = (0, 18, 0)
COLOR_BTN_ACTIVE  = (0, 60, 0)
COLOR_BTN_FOCUSED = COLOR_GREEN

_RELOAD = "__RELOAD__"


def _next_focus(f):
    f = (f + 1) % _N_FOCUS
    import state as _state
    if f == FOCUS_REFRESH and _state.offline_mode:
        f = FOCUS_INFO
    return f

# Marquee settings
_SCROLL_SPEED   = 40    # pixels per second
_SCROLL_PAUSE_0 = 1.5   # pause before scrolling starts
_SCROLL_PAUSE_1 = 0.8   # pause at end before reset


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _sort_label(mode):
    return {"downloads": "DL", "published_at": "DATE", "name": "NAME"}[mode]


def _truncate(draw, text, font, max_w):
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    while len(text) > 1 and draw.textbbox((0, 0), text + "~", font=font)[2] > max_w:
        text = text[:-1]
    return text + "~"


def _fw_label(fw):
    name   = fw.get("name", "")
    author = fw.get("author", "")
    return f"{name} ({author})" if author else name


def _measure_scroll_max(fw, font=None):
    """Return how many pixels the selected row label overflows (0 if it fits)."""
    full = _fw_label(fw)
    tmp  = Image.new("RGB", (1, 1))
    d    = ImageDraw.Draw(tmp)
    f    = font or _font()
    pw   = d.textbbox((0, 0), "> ", font=f)[2]
    tw   = d.textbbox((0, 0), full, font=f)[2]
    avail = LIST_W - (8 + pw) - 4
    return max(0, tw - avail)


def _draw(devices, selected, offset, sort_idx, filter_text, focus, cursor_visible,
          scroll_px=0, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    # Header bar
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 4), "SELECT FIRMWARE", fill=COLOR_GREEN, font=font)

    # Header icons — right-aligned in the header bar: ↻ ℹ 📁 wifi
    _IS   = 14
    _IG   = 4
    _IY   = (HEADER_H - _IS) // 2
    offline   = state.offline_mode
    wifi_x    = SCREEN_W - _IG - _IS
    folder_x  = wifi_x   - _IG - _IS
    info_x    = folder_x - _IG - _IS
    refresh_x = info_x   - _IG - _IS

    wifi_c    = (COLOR_BTN_FOCUSED if focus == FOCUS_CONN
                 else (160, 75, 0) if offline else COLOR_DIM)
    folder_c  = COLOR_BTN_FOCUSED if focus == FOCUS_FILE    else COLOR_DIM
    info_c    = COLOR_BTN_FOCUSED if focus == FOCUS_INFO    else COLOR_DIM
    refresh_c = (COLOR_BTN_FOCUSED if focus == FOCUS_REFRESH
                 else (40, 40, 40) if offline else COLOR_DIM)

    icons.paste_icon(img, icons.wifi_icon(wifi_c,    not offline, _IS), wifi_x,    _IY)
    icons.paste_icon(img, icons.folder_icon(folder_c,             _IS), folder_x,  _IY)
    icons.paste_icon(img, icons.info_icon(info_c,                 _IS), info_x,    _IY)
    icons.paste_icon(img, icons.refresh_icon(refresh_c,           _IS), refresh_x, _IY)

    if registry is not None:
        registry.add(FOCUS_CONN,    (wifi_x,    _IY, wifi_x    + _IS, _IY + _IS))
        registry.add(FOCUS_FILE,    (folder_x,  _IY, folder_x  + _IS, _IY + _IS))
        registry.add(FOCUS_INFO,    (info_x,    _IY, info_x    + _IS, _IY + _IS))
        registry.add(FOCUS_REFRESH, (refresh_x, _IY, refresh_x + _IS, _IY + _IS))

    # Toolbar: sort + filter (filter fills remaining width)
    draw.rectangle([0, HEADER_H, SCREEN_W, HEADER_H + TOOLBAR_H], fill=COLOR_TOOLBAR_BG)
    ty = HEADER_H + 2

    sort_label = f"[{_sort_label(SORT_MODES[sort_idx])}]"
    btn_color  = COLOR_BTN_FOCUSED if focus == FOCUS_SORT else COLOR_DIM
    draw.text((4, ty), sort_label, fill=btn_color, font=font)
    sort_btn_w  = draw.textbbox((0, 0), sort_label, font=font)[2]
    if registry is not None:
        registry.add(FOCUS_SORT, (4, HEADER_H, 4 + sort_btn_w, HEADER_H + TOOLBAR_H))
    filter_left = 4 + sort_btn_w + 4

    filt_color   = COLOR_BTN_FOCUSED if focus == FOCUS_FILTER else COLOR_DIM
    display_text = filter_text + ("_" if focus == FOCUS_FILTER and cursor_visible else "")
    draw.text((filter_left, ty), display_text if display_text else "filter...", fill=filt_color, font=font)
    if registry is not None:
        registry.add(FOCUS_FILTER, (filter_left, HEADER_H, SCREEN_W, HEADER_H + TOOLBAR_H))

    # Geometry for the selected row's scrollable text area
    prefix      = "> "
    prefix_w    = draw.textbbox((0, 0), prefix, font=font)[2]
    text_x      = 8 + prefix_w          # left edge of label (after "> ")
    avail_w     = LIST_W - text_x - 4   # pixels available for the label

    # List rows
    for i in range(VISIBLE):
        idx = offset + i
        if idx >= len(devices):
            break
        y    = LIST_TOP + i * ROW_H
        fw   = devices[idx]
        full = _fw_label(fw)

        if idx == selected and focus == FOCUS_LIST:
            draw.rectangle([0, y, LIST_W, y + ROW_H - 1], fill=(0, 50, 0))
            draw.rectangle([0, y, LIST_W, y + ROW_H - 1], outline=COLOR_GREEN)
            draw.text((8, y + 2), prefix, fill=COLOR_GREEN, font=font)

            text_w = draw.textbbox((0, 0), full, font=font)[2]
            if text_w <= avail_w or scroll_px <= 0:
                label = _truncate(draw, full, font, avail_w) if text_w > avail_w else full
                draw.text((text_x, y + 2), label, fill=COLOR_GREEN, font=font)
            else:
                # Render full text onto a strip, paste the visible window
                strip_w = text_w + 4
                strip   = Image.new("RGB", (strip_w, ROW_H - 1), (0, 50, 0))
                sdraw   = ImageDraw.Draw(strip)
                sdraw.text((0, 2), full, fill=COLOR_GREEN, font=font)
                crop_x  = min(scroll_px, text_w - avail_w)
                crop    = strip.crop((crop_x, 0, crop_x + avail_w, ROW_H - 1))
                img.paste(crop, (text_x, y))
        else:
            color = COLOR_DIM if idx != selected else (0, 100, 0)
            label = _truncate(draw, full, font, LIST_W - 20)
            draw.text((8, y + 2), f"  {label}", fill=color, font=font)

        if registry is not None:
            registry.add(("row", idx), (0, y, LIST_W, y + ROW_H - 1))

    # Scrollbar
    if len(devices) > VISIBLE:
        track_h = LIST_BOT - LIST_TOP
        thumb_h = max(10, track_h * VISIBLE // len(devices))
        thumb_y = LIST_TOP + track_h * offset // len(devices)
        sx = SCREEN_W - SCROLLBAR_W - 1
        draw.rectangle([sx, LIST_TOP, sx + SCROLLBAR_W, LIST_BOT], fill=(0, 20, 0))
        draw.rectangle([sx, thumb_y, sx + SCROLLBAR_W, thumb_y + thumb_h], fill=COLOR_DIM)

        if registry is not None:
            # Touch target is wider than the thin visual bar (SCROLLBAR_W)
            # so it's actually hittable with a finger/mouse. Top half of
            # the track scrolls up one row, bottom half scrolls down one
            # row — same step the Up/Down keys already take.
            mid = LIST_TOP + track_h // 2
            registry.add(("scroll", -1), (SCREEN_W - 16, LIST_TOP, SCREEN_W, mid))
            registry.add(("scroll", 1),  (SCREEN_W - 16, mid, SCREEN_W, LIST_BOT))

    draw_navbar(draw, font, registry)
    blit(img)


def _draw_status(message, color=COLOR_DIM):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 4), "SELECT FIRMWARE", fill=COLOR_GREEN, font=font)
    draw_connection_status(draw, font)
    bbox = draw.textbbox((0, 0), message, font=font)
    tx   = (SCREEN_W - (bbox[2] - bbox[0])) // 2
    ty   = HEADER_H + (LIST_BOT - HEADER_H - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), message, fill=color, font=font)
    draw_navbar(draw, font)
    blit(img)


def _apply_filter(all_fw, text):
    if not text:
        return list(all_fw)
    low = text.lower()
    return [fw for fw in all_fw if low in fw.get("name", "").lower()]


def _run_once(category, input_handler):
    """Single pass of the firmware-list screen. Returns firmware dict, None, or _RELOAD."""
    if state.checking_online:
        _draw_status("Checking connection...")
    offline, show_warning = api.sync_offline_state()
    if show_warning:
        _draw_status("No connection  -  showing downloaded content only", color=COLOR_GRAY)
        time.sleep(1.5)
    elif not offline:
        _draw_status("Fetching firmware...")

    try:
        all_firmware = api.get_firmware_list(category)
    except Exception as e:
        _draw_status(f"Error: {str(e)[:30]}", color=COLOR_GRAY)
        time.sleep(2)
        return None

    if not all_firmware:
        if state.offline_mode:
            _draw_status("No downloaded firmware for this device.", color=COLOR_GRAY)
        else:
            _draw_status("No firmware found.", color=COLOR_GRAY)
        time.sleep(2)
        return None

    sort_idx    = 0  # downloads
    filter_text = ""
    focus       = FOCUS_LIST
    selected    = 0
    offset      = 0
    cursor_on   = True
    last_blink  = time.time()

    # Apply initial sort
    field, reverse, default = _SORT_CFG[SORT_MODES[sort_idx]]
    all_firmware.sort(
        key=lambda fw: fw.get(field, 0) or fw.get("downloads", 0),
        reverse=reverse,
    )

    devices = _apply_filter(all_firmware, filter_text)

    # Marquee scroll state
    scroll_px    = 0
    scroll_phase = 0          # 0=initial pause  1=scrolling  2=end pause
    scroll_t     = time.time()
    scroll_max   = _measure_scroll_max(devices[selected]) if devices else 0

    def _reset_scroll():
        nonlocal scroll_px, scroll_phase, scroll_t, scroll_max
        scroll_px    = 0
        scroll_phase = 0
        scroll_t     = time.time()
        scroll_max   = _measure_scroll_max(devices[selected]) if devices else 0

    registry    = HitAreaRegistry()
    list_scroll = ListScroll(ROW_H)

    def _refresh():
        registry.clear()
        _draw(devices, selected, offset, sort_idx, filter_text, focus, cursor_on, scroll_px, registry)

    def _activate_enter():
        """Runs whatever the currently-focused control does when
        activated — shared by the KEY_ENTER handler and by tapping the
        equivalent on-screen control. Returns _RELOAD / the selected
        firmware dict to have _run_once return it, or None if handled in
        place."""
        nonlocal focus, sort_idx, devices, selected, offset
        if focus == FOCUS_CONN:
            if state.offline_mode:
                state.checking_online = True
            state.offline_mode = not state.offline_mode
            return _RELOAD
        elif focus == FOCUS_REFRESH and not state.offline_mode:
            _draw_status("Refreshing...")
            import api as _api
            _api.refresh_all()
            return _RELOAD
        elif focus == FOCUS_INFO:
            from screens import info as _info
            _info.run(input_handler=input_handler)
            _refresh()
        elif focus == FOCUS_FILE:
            from screens import file_install as _fi
            _fi.run(input_handler=input_handler)
            _refresh()
        elif focus == FOCUS_SORT:
            sort_idx = (sort_idx + 1) % len(SORT_MODES)
            mode = SORT_MODES[sort_idx]
            if mode == "published_at":
                all_firmware.sort(
                    key=lambda fw: max(
                        (v.get("published_at", "") for v in fw.get("versions", []) if v.get("published_at")),
                        default="",
                    ),
                    reverse=True,
                )
            else:
                field, reverse, default = _SORT_CFG[mode]
                all_firmware.sort(
                    key=lambda fw: fw.get(field, 0) or fw.get("downloads", 0)
                    if field == "download" else fw.get(field, default),
                    reverse=reverse,
                )
            devices  = _apply_filter(all_firmware, filter_text)
            selected = 0
            offset   = 0
            _reset_scroll()
            _refresh()
        elif focus == FOCUS_FILTER:
            focus = FOCUS_LIST
            _refresh()
        else:
            if devices:
                return devices[selected]
        return None

    def _activate_esc():
        """Same logic as the KEY_ESC handler. Returns True if _run_once
        should return None (back to device select), False if handled in
        place (filter cleared) — shared with tapping the navbar's back
        area."""
        nonlocal filter_text, devices, selected, offset, focus
        if filter_text:
            filter_text = ""
            devices     = _apply_filter(all_firmware, filter_text)
            selected    = 0
            offset      = 0
            focus       = FOCUS_LIST
            _reset_scroll()
            _refresh()
            return False
        return True

    def _open_filter_keyboard():
        """Tapping the filter field opens the on-screen keyboard (touch
        devices have no physical keyboard to type on) — feeds the result
        through the exact same filter-refresh sequence typing already uses."""
        nonlocal filter_text, devices, selected, offset, focus
        focus  = FOCUS_FILTER
        result = ui_keyboard.run(input_handler, initial_text=filter_text, placeholder="filter...")
        if result is not None:
            filter_text = result
            devices      = _apply_filter(all_firmware, filter_text)
            selected     = 0
            offset       = 0
            _reset_scroll()
        _refresh()

    def _scroll(delta):
        """Moves the list selection by `delta` rows (may be more than one —
        mouse wheel notches and touch-drag distance both funnel through
        here) — shared by the Up/Down keys, the scrollbar's touch zones,
        and ListScroll (wheel/drag)."""
        nonlocal focus, selected, offset
        if focus != FOCUS_LIST:
            if delta != 0:
                focus = FOCUS_LIST
                _refresh()
            return
        if not devices or delta == 0:
            return
        new_selected = max(0, min(len(devices) - 1, selected + delta))
        if new_selected == selected:
            return
        selected = new_selected
        if selected < offset:
            offset = selected
        elif selected >= offset + VISIBLE:
            offset = selected - VISIBLE + 1
        _reset_scroll()
        _refresh()

    _refresh()

    while True:
        now = time.time()
        needs_redraw = False

        # Cursor blink
        if now - last_blink > 0.5:
            cursor_on  = not cursor_on
            last_blink = now
            needs_redraw = True

        # Marquee update
        if focus == FOCUS_LIST and scroll_max > 0:
            if scroll_phase == 0:
                if now - scroll_t >= _SCROLL_PAUSE_0:
                    scroll_phase = 1
                    scroll_t     = now
                    needs_redraw = True
            elif scroll_phase == 1:
                new_px = int((now - scroll_t) * _SCROLL_SPEED)
                if new_px != scroll_px:
                    scroll_px    = min(new_px, scroll_max)
                    needs_redraw = True
                if scroll_px >= scroll_max:
                    scroll_phase = 2
                    scroll_t     = now
            elif scroll_phase == 2:
                if now - scroll_t >= _SCROLL_PAUSE_1:
                    scroll_px    = 0
                    scroll_phase = 0
                    scroll_t     = now
                    needs_redraw = True

        if needs_redraw:
            _refresh()

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
            if tapped == NAV_BACK:
                if _activate_esc():
                    return None
            elif isinstance(tapped, tuple) and tapped[0] == "row":
                idx = tapped[1]
                if idx < len(devices):
                    selected = idx
                    focus    = FOCUS_LIST
                    outcome  = _activate_enter()
                    if outcome is not None:
                        return outcome
            elif isinstance(tapped, tuple) and tapped[0] == "scroll":
                _scroll(tapped[1])
            elif tapped == FOCUS_FILTER:
                _open_filter_keyboard()
            else:
                focus   = tapped
                outcome = _activate_enter()
                if outcome is not None:
                    return outcome
            continue

        scroll_delta = list_scroll.poll(events, (0, LIST_TOP, LIST_W, LIST_BOT))
        if scroll_delta:
            _scroll(scroll_delta)
            continue

        # Character input — check Ctrl+O first
        ch = input_handler.next_char()
        if ch is not None:
            if ch == '\x0f':  # Ctrl+O — toggle offline mode and reload
                if state.offline_mode:
                    state.checking_online = True
                state.offline_mode = not state.offline_mode
                return _RELOAD
            if ch == '\x12' and not state.offline_mode:  # Ctrl+R — refresh
                _draw_status("Refreshing...")
                import api as _api
                _api.refresh_all()
                return _RELOAD
            if ch == '\x08' and focus != FOCUS_FILTER:  # Ctrl+H — open guide
                from screens import tutorial as _tutorial
                _tutorial.run(input_handler=input_handler)
                _refresh()
                continue
            if focus == FOCUS_FILTER:
                if ch == '\x08':
                    filter_text = filter_text[:-1]
                else:
                    filter_text += ch
                devices  = _apply_filter(all_firmware, filter_text)
                selected = 0
                offset   = 0
                _reset_scroll()
                _refresh()
                continue
            elif focus == FOCUS_LIST and ch != '\x08' and ch.isprintable() and ch.strip():
                focus       = FOCUS_FILTER
                filter_text = ch
                devices     = _apply_filter(all_firmware, filter_text)
                selected    = 0
                offset      = 0
                _reset_scroll()
                _refresh()
                continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            if _activate_esc():
                return None

        elif key == KEY_TAB:
            focus = _next_focus(focus)
            _refresh()

        elif key == KEY_ENTER:
            outcome = _activate_enter()
            if outcome is not None:
                return outcome

        elif key == KEY_UP:
            _scroll(-1)

        elif key == KEY_DOWN:
            _scroll(1)

        elif key == KEY_RIGHT and focus == FOCUS_LIST:
            if devices:
                selected = min(selected + VISIBLE, len(devices) - 1)
                offset   = max(0, min(selected - VISIBLE + 1, len(devices) - VISIBLE))
                _reset_scroll()
                _refresh()

        elif key == KEY_LEFT and focus == FOCUS_LIST:
            if devices:
                selected = max(selected - VISIBLE, 0)
                offset   = max(0, min(selected, len(devices) - VISIBLE))
                _reset_scroll()
                _refresh()


def run(category, input_handler=None):
    """Shows the firmware list screen for the given category.
    Returns the selected firmware dict, or None if ESC back to device select."""
    while True:
        result = _run_once(category, input_handler)
        if result != _RELOAD:
            return result
