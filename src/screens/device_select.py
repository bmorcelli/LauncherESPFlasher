import os
import time

from PIL import Image, ImageDraw, ImageFont
import api
import state
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_TAB,
)
import icons
from display import blit
from ui import draw_connection_status, draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap, ListScroll
import ui_keyboard

HEADER_H    = 22
TOOLBAR_H   = 18
ROW_H       = 18
SCROLLBAR_W = 4
LIST_W      = SCREEN_W - SCROLLBAR_W - 2
LIST_TOP    = HEADER_H + TOOLBAR_H        # 40
LIST_BOT    = SCREEN_H - NAVBAR_H         # 156
VISIBLE     = (LIST_BOT - LIST_TOP) // ROW_H  # 6

SORT_MODES = ["name", "count"]

FOCUS_LIST    = 0
FOCUS_SORT    = 1
FOCUS_SOURCE  = 2
FOCUS_FILTER  = 3
FOCUS_REFRESH = 4   # ↻ refresh icon
FOCUS_INFO    = 5   # ℹ info/about
FOCUS_FILE    = 6   # file install
FOCUS_CONN    = 7   # wifi/online toggle
_N_FOCUS      = 8

COLOR_TOOLBAR_BG  = (0, 18, 0)
COLOR_BTN_FOCUSED = COLOR_GREEN

_RELOAD = "__RELOAD__"


def _next_focus(f):
    f = (f + 1) % _N_FOCUS
    import state as _state
    if f == FOCUS_REFRESH and _state.offline_mode:
        f = FOCUS_INFO
    return f


def _confirm_exit(input_handler):
    """Show exit confirmation dialog. Returns True if user confirms exit."""
    from config import COLOR_WHITE
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=COLOR_BG)
    cx, cy = SCREEN_W // 2, SCREEN_H // 2

    box_w, box_h = 200, 70
    bx = cx - box_w // 2
    by = cy - box_h // 2
    draw.rectangle([bx, by, bx + box_w, by + box_h], fill=(0, 20, 0), outline=COLOR_GREEN)
    draw.text((bx + 10, by + 8), "Exit application?", fill=COLOR_WHITE, font=font)

    btn0, btn1 = "  Yes  ", "  No  "
    b0_w = draw.textbbox((0, 0), btn0, font=font)[2] + 4
    b1_w = draw.textbbox((0, 0), btn1, font=font)[2] + 4
    btn_y = by + box_h - 22
    b0_x  = bx + 14
    b1_x  = bx + box_w - b1_w - 14

    option = 0  # default: Yes
    registry = HitAreaRegistry()

    def _draw_dialog(opt):
        registry.clear()
        img2  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
        d2    = ImageDraw.Draw(img2)
        d2.rectangle([bx, by, bx + box_w, by + box_h], fill=(0, 20, 0), outline=COLOR_GREEN)
        d2.text((bx + 10, by + 8), "Exit application?", fill=COLOR_WHITE, font=font)
        for i, (bxb, bwb, btxt) in enumerate([(b0_x, b0_w, btn0), (b1_x, b1_w, btn1)]):
            sel = (i == opt)
            d2.rectangle([bxb, btn_y, bxb + bwb, btn_y + 14],
                fill=(0, 50, 0) if sel else (0, 10, 0),
                outline=COLOR_GREEN if sel else (0, 40, 0))
            d2.text((bxb + 2, btn_y + 1), btxt,
                fill=COLOR_GREEN if sel else COLOR_DIM, font=font)
            registry.add(i, (bxb, btn_y, bxb + bwb, btn_y + 14))
        from display import blit as _blit
        _blit(img2)

    _draw_dialog(option)

    while True:
        time.sleep(0.05)
        if not input_handler:
            continue

        # Touch: tapping Yes/No decides immediately (no separate confirm step).
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            return tapped == 0

        key = input_handler.last_key()
        if key is None:
            continue
        if key == KEY_LEFT:
            if option != 0:
                option = 0
                _draw_dialog(option)
        elif key == KEY_RIGHT:
            if option != 1:
                option = 1
                _draw_dialog(option)
        elif key == KEY_ENTER:
            return option == 0
        elif key == KEY_ESC:
            return False


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _sort_label(mode):
    return {"name": "NAME", "count": "CNT"}[mode]


def _truncate(draw, text, font, max_w):
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    while len(text) > 1 and draw.textbbox((0, 0), text + "~", font=font)[2] > max_w:
        text = text[:-1]
    return text + "~"


def _apply_filters(all_devices, active_source, filter_text):
    result = []
    for d in all_devices:
        if active_source and active_source not in d.get("sources", ["m5stack"]):
            continue
        if filter_text and filter_text.lower() not in d["name"].lower():
            continue
        result.append(d)
    return result


def _apply_sort(devices, sort_idx):
    if SORT_MODES[sort_idx] == "count":
        return sorted(devices, key=lambda d: d.get("firmware_count", 0), reverse=True)
    return sorted(devices, key=lambda d: d["name"].lower())


def _draw_status(message, color=COLOR_DIM):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 4), "SELECT DEVICE", fill=COLOR_GREEN, font=font)
    draw_connection_status(draw, font)
    bbox = draw.textbbox((0, 0), message, font=font)
    tx = (SCREEN_W - (bbox[2] - bbox[0])) // 2
    ty = HEADER_H + (LIST_BOT - HEADER_H - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), message, fill=color, font=font)
    draw_navbar(draw, font)
    blit(img)


def _draw(devices, selected, offset, sort_idx, source_idx, sources_all,
          filter_text, focus, cursor_visible, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    # Header bar
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    draw.text((6, 4), "SELECT DEVICE", fill=COLOR_GREEN, font=font)

    # Header icons — right-aligned in the header bar: ↻ ℹ 📁 wifi
    _IS   = 14   # icon size
    _IG   = 4    # gap between icons / from right edge
    _IY   = (HEADER_H - _IS) // 2   # = 4 (centered vertically)
    offline   = state.offline_mode
    wifi_x    = SCREEN_W - _IG - _IS          # 302
    folder_x  = wifi_x   - _IG - _IS          # 284
    info_x    = folder_x - _IG - _IS          # 266
    refresh_x = info_x   - _IG - _IS          # 248

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

    # Toolbar: sort + source + filter (filter fills remaining width)
    draw.rectangle([0, HEADER_H, SCREEN_W, HEADER_H + TOOLBAR_H], fill=COLOR_TOOLBAR_BG)
    ty = HEADER_H + 2
    x  = 4

    sort_lbl   = f"[{_sort_label(SORT_MODES[sort_idx])}]"
    sort_color = COLOR_BTN_FOCUSED if focus == FOCUS_SORT else COLOR_DIM
    draw.text((x, ty), sort_lbl, fill=sort_color, font=font)
    sort_w = draw.textbbox((0, 0), sort_lbl, font=font)[2]
    if registry is not None:
        registry.add(FOCUS_SORT, (x, HEADER_H, x + sort_w, HEADER_H + TOOLBAR_H))
    x += sort_w + 4

    src_lbl   = f"[{sources_all[source_idx]}]" if sources_all else "[---]"
    src_color = COLOR_BTN_FOCUSED if focus == FOCUS_SOURCE else COLOR_DIM
    draw.text((x, ty), src_lbl, fill=src_color, font=font)
    src_w = draw.textbbox((0, 0), src_lbl, font=font)[2]
    if registry is not None and sources_all:
        registry.add(FOCUS_SOURCE, (x, HEADER_H, x + src_w, HEADER_H + TOOLBAR_H))
    x += src_w + 4

    filt_color = COLOR_BTN_FOCUSED if focus == FOCUS_FILTER else COLOR_DIM
    filt_text  = filter_text + ("_" if focus == FOCUS_FILTER and cursor_visible else "")
    draw.text((x, ty), filt_text if filt_text else "filter...", fill=filt_color, font=font)
    if registry is not None:
        registry.add(FOCUS_FILTER, (x, HEADER_H, SCREEN_W, HEADER_H + TOOLBAR_H))

    # List rows
    for i in range(VISIBLE):
        idx = offset + i
        if idx >= len(devices):
            break
        d   = devices[idx]
        y   = LIST_TOP + i * ROW_H
        cnt = d.get("firmware_count", 0)
        row = f"{d['name']} ({cnt})" if cnt else d["name"]

        if idx == selected and focus == FOCUS_LIST:
            draw.rectangle([0, y, LIST_W, y + ROW_H - 1], fill=(0, 50, 0))
            draw.rectangle([0, y, LIST_W, y + ROW_H - 1], outline=COLOR_GREEN)
            label = _truncate(draw, row, font, LIST_W - 20)
            draw.text((8, y + 2), f"> {label}", fill=COLOR_GREEN, font=font)
        else:
            color = COLOR_DIM if idx != selected else (0, 100, 0)
            label = _truncate(draw, row, font, LIST_W - 20)
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


def _run_once(input_handler):
    """Single pass of the device-select screen. Returns category string, None, or _RELOAD."""
    if state.checking_online:
        _draw_status("Checking connection...")
    offline, show_warning = api.sync_offline_state()
    if show_warning:
        _draw_status("No connection  -  showing downloaded content only", color=COLOR_GRAY)
        time.sleep(1.5)
    elif not offline:
        _draw_status("Fetching devices...")

    try:
        all_devices = api.get_devices_full()
    except Exception as e:
        _draw_status(f"Error: {str(e)[:30]}", color=COLOR_GRAY)
        time.sleep(2)
        return _RELOAD

    if not all_devices:
        if state.offline_mode:
            _draw_status("No downloaded content. Connect to the internet and press any key.", color=COLOR_GRAY)
            if input_handler:
                input_handler.flush()
                while input_handler.last_key() is None:
                    time.sleep(0.05)
            else:
                time.sleep(3)
        else:
            _draw_status("No devices found.", color=COLOR_GRAY)
            time.sleep(2)
        return _RELOAD

    # Build sources list with m5stack first
    sources_set = set()
    for d in all_devices:
        sources_set.update(d.get("sources", ["m5stack"]))
    sources_all = sorted(sources_set - {"m5stack"})
    if "m5stack" in sources_set:
        sources_all.insert(0, "m5stack")

    sort_idx    = 0
    source_idx  = 0
    filter_text = ""
    focus       = FOCUS_LIST
    selected    = 0
    offset      = 0
    cursor_on   = True
    last_blink  = time.time()

    active_source = sources_all[source_idx] if sources_all else ""
    devices = _apply_sort(_apply_filters(all_devices, active_source, filter_text), sort_idx)

    registry    = HitAreaRegistry()
    list_scroll = ListScroll(ROW_H)

    def _refresh():
        registry.clear()
        _draw(devices, selected, offset, sort_idx, source_idx, sources_all,
              filter_text, focus, cursor_on, registry)

    def _refilter():
        nonlocal devices, selected, offset, active_source
        active_source = sources_all[source_idx] if sources_all else ""
        devices  = _apply_sort(_apply_filters(all_devices, active_source, filter_text), sort_idx)
        selected = 0
        offset   = 0

    def _activate_enter():
        """Runs whatever the currently-focused control does when
        activated — shared by the KEY_ENTER handler and by tapping the
        equivalent on-screen control. Returns _RELOAD / a device name to
        have _run_once return it, or None if handled in place."""
        nonlocal focus, sort_idx, source_idx
        if focus == FOCUS_CONN:
            if state.offline_mode:      # offline → online: trigger a live probe
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
            _refilter()
            _refresh()
        elif focus == FOCUS_SOURCE:
            source_idx = (source_idx + 1) % len(sources_all) if sources_all else 0
            _refilter()
            _refresh()
        elif focus == FOCUS_FILTER:
            focus = FOCUS_LIST
            _refresh()
        else:
            if devices:
                return devices[selected]["name"]
        return None

    def _activate_esc():
        """Same logic as the KEY_ESC handler — shared with tapping the
        navbar's back area."""
        nonlocal filter_text, focus
        if filter_text:
            filter_text = ""
            focus       = FOCUS_LIST
            _refilter()
            _refresh()
        else:
            if _confirm_exit(input_handler):
                import sys
                sys.exit(0)
            _refresh()

    def _open_filter_keyboard():
        """Tapping the filter field opens the on-screen keyboard (touch
        devices have no physical keyboard to type on) — feeds the result
        through the exact same _refilter() path typing already uses."""
        nonlocal filter_text, focus
        focus  = FOCUS_FILTER
        result = ui_keyboard.run(input_handler, initial_text=filter_text, placeholder="filter...")
        if result is not None:
            filter_text = result
            _refilter()
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
        _refresh()

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

        # Touch/mouse: drain pointer events once, feed both tap hit-testing
        # and list scrolling (drag on real touch, wheel on desktop dev).
        events = drain_pointer_events(input_handler)

        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                _activate_esc()
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

        # Character input — check Ctrl+O / Ctrl+R first, then filter
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
                filter_text = filter_text[:-1] if ch == '\x08' else filter_text + ch
                _refilter()
                _refresh()
                continue
            elif focus == FOCUS_LIST and ch != '\x08' and ch.isprintable() and ch.strip():
                focus       = FOCUS_FILTER
                filter_text = ch
                _refilter()
                _refresh()
                continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            _activate_esc()

        elif key == KEY_TAB:
            focus = _next_focus(focus)
            _refresh()

        elif key == KEY_ENTER:
            outcome = _activate_enter()
            if outcome is not None:
                return outcome

        elif key == KEY_LEFT:
            if focus == FOCUS_LIST:
                if devices:
                    selected = max(selected - VISIBLE, 0)
                    offset   = max(0, min(selected, len(devices) - VISIBLE))
                    _refresh()
            elif focus == FOCUS_SORT:
                sort_idx = (sort_idx - 1) % len(SORT_MODES)
                _refilter()
                _refresh()
            elif focus == FOCUS_SOURCE and sources_all:
                source_idx = (source_idx - 1) % len(sources_all)
                _refilter()
                _refresh()

        elif key == KEY_RIGHT:
            if focus == FOCUS_LIST:
                if devices:
                    selected = min(selected + VISIBLE, len(devices) - 1)
                    offset   = max(0, min(selected - VISIBLE + 1, len(devices) - VISIBLE))
                    _refresh()
            elif focus == FOCUS_SORT:
                sort_idx = (sort_idx + 1) % len(SORT_MODES)
                _refilter()
                _refresh()
            elif focus == FOCUS_SOURCE and sources_all:
                source_idx = (source_idx + 1) % len(sources_all)
                _refilter()
                _refresh()

        elif key == KEY_UP:
            _scroll(-1)

        elif key == KEY_DOWN:
            _scroll(1)


def run(input_handler=None):
    """Shows the device/category selection screen.
    Returns the selected category string, or None if ESC was pressed."""
    while True:
        result = _run_once(input_handler)
        if result != _RELOAD:
            return result
