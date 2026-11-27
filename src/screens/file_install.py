"""File Install flow: detect device → pick .bin → analyse → confirm → flash."""
import os
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, COLOR_ORANGE, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_TAB,
)
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap
import flasher

HEADER_H    = 22
CONTENT_TOP = HEADER_H
CONTENT_BOT = SCREEN_H - NAVBAR_H
BAR_W       = SCREEN_W - 40
BAR_X       = 20
BAR_H       = 12

# Custom-table layout constants
_COL_ADDR_X = 6
_COL_ADDR_W = 68
_COL_FILE_X = 78
_COL_FILE_W = SCREEN_W - 78 - 4

_ROW_HDR_Y = HEADER_H + 4
_ROW_HDR_H = 13
_ROW_1_Y   = _ROW_HDR_Y + _ROW_HDR_H + 2
_ROW_2_Y   = _ROW_1_Y + 20
_ROW_3_Y   = _ROW_2_Y + 20
_BTN_Y     = _ROW_3_Y + 30
_BTN_H     = 14

_FC_BL    = 0
_FC_PT    = 1
_FC_ADDR  = 2
_FC_FLASH = 3
_N_FC     = 4

_CHECK_INTERVAL = 0.8   # seconds between port-detection attempts


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _chip_label(chip):
    """'32' → 'ESP32',  's3' → 'ESP32-S3', etc."""
    return "ESP32" if chip == "32" else f"ESP32-{chip.upper()}"


def _draw_header(draw, font, subtitle=""):
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    title = "FILE INSTALL"
    if subtitle:
        title += "  " + subtitle
    draw.text((6, 4), title, fill=COLOR_GREEN, font=font)


def _draw_status(message, subtitle="", color=COLOR_DIM):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    _draw_header(draw, font, subtitle)
    bbox = draw.textbbox((0, 0), message, font=font)
    tx = (SCREEN_W - (bbox[2] - bbox[0])) // 2
    ty = CONTENT_TOP + (CONTENT_BOT - CONTENT_TOP - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), message, fill=color, font=font)
    draw_navbar(draw, font)
    blit(img)


def _draw_progress(stage, pct):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4
    _draw_header(draw, font)
    content_h = CONTENT_BOT - CONTENT_TOP
    cy = CONTENT_TOP + content_h // 2 - lh - BAR_H // 2
    draw.text((BAR_X, cy), stage, fill=COLOR_DIM, font=font)
    cy += lh + 6
    draw.rectangle([BAR_X, cy, BAR_X + BAR_W, cy + BAR_H],
                   fill=(0, 25, 0), outline=(0, 80, 0))
    filled = int(BAR_W * pct / 100)
    if filled > 0:
        draw.rectangle([BAR_X + 1, cy + 1, BAR_X + filled, cy + BAR_H - 1],
                       fill=COLOR_GREEN)
    cy += BAR_H + 4
    pct_text = f"{pct}%"
    pw = draw.textbbox((0, 0), pct_text, font=font)[2]
    draw.text((BAR_X + BAR_W - pw, cy), pct_text, fill=COLOR_GREEN, font=font)
    draw_navbar(draw, font)
    blit(img)


def _draw_result(message, success):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4
    _draw_header(draw, font)
    color   = COLOR_GREEN if success else COLOR_GRAY
    lines   = message.split("\n")
    total_h = len(lines) * lh + lh + 4
    content_h = CONTENT_BOT - CONTENT_TOP
    y = CONTENT_TOP + (content_h - total_h) // 2
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        draw.text(((SCREEN_W - w) // 2, y), line, fill=color, font=font)
        y += lh
    y += 6
    hint = "Press any key"
    hw = draw.textbbox((0, 0), hint, font=font)[2]
    draw.text(((SCREEN_W - hw) // 2, y), hint, fill=COLOR_DIM, font=font)
    draw_navbar(draw, font)
    blit(img)


def _wait_key(input_handler):
    """Waits for any keypress OR any tap — these screens have no discrete
    button, so a tap anywhere (no hit-testing needed) is the touch
    equivalent of "press any key"."""
    if not input_handler:
        time.sleep(2)
        return
    while True:
        time.sleep(0.05)
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)
        if input_handler.last_key() is not None:
            return
        poll = getattr(input_handler, "poll_pointer_events", None)
        if poll is not None and any(ev.kind == "tap" for ev in poll()):
            return


# ─────────────────────────────────────────────────────────────
# Screen 0: Wait for device connection (auto-polls)
# ─────────────────────────────────────────────────────────────

def _draw_connecting(font, dots, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    lh   = FONT_SIZE_SM + 4
    _draw_header(draw, font)

    content_h = CONTENT_BOT - CONTENT_TOP
    msg1 = "Connect ESP32 via USB"
    msg2 = "Checking" + "." * dots
    hint = "ESC to cancel"
    total_h = lh * 2 + lh
    y = CONTENT_TOP + (content_h - total_h) // 2

    w = draw.textbbox((0, 0), msg1, font=font)[2]
    draw.text(((SCREEN_W - w) // 2, y), msg1, fill=COLOR_GREEN, font=font)
    y += lh + 4

    w = draw.textbbox((0, 0), msg2, font=font)[2]
    draw.text(((SCREEN_W - w) // 2, y), msg2, fill=COLOR_DIM, font=font)

    w = draw.textbbox((0, 0), hint, font=font)[2]
    draw.text(((SCREEN_W - w) // 2, CONTENT_BOT - lh - 2), hint, fill=(0, 35, 0), font=font)

    draw_navbar(draw, font, registry)
    blit(img)


def _draw_detected(font, label):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    lh   = FONT_SIZE_SM + 4
    _draw_header(draw, font)

    msg = f"{label} detected!"
    content_h = CONTENT_BOT - CONTENT_TOP
    w = draw.textbbox((0, 0), msg, font=font)[2]
    draw.text(((SCREEN_W - w) // 2,
               CONTENT_TOP + (content_h - lh) // 2), msg, fill=COLOR_GREEN, font=font)

    draw_navbar(draw, font)
    blit(img)


def _wait_for_device(input_handler):
    """Auto-poll for an ESP32. Returns (port, extra_flags, chip, chip_label) or None on ESC."""
    font       = _font()
    dots       = 0
    last_check = 0.0
    registry   = HitAreaRegistry()

    while True:
        now = time.time()

        if now - last_check >= _CHECK_INTERVAL:
            last_check = now
            registry.clear()
            _draw_connecting(font, dots, registry)
            dots = (dots % 3) + 1

            port, extra_flags = flasher.detect_port()
            if port:
                chip  = flasher.detect_chip_type(port, extra_flags) or "32"
                label = _chip_label(chip)
                _draw_detected(font, label)
                time.sleep(0.7)
                return port, extra_flags, chip, label

        time.sleep(0.05)

        if not input_handler:
            continue
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        events = drain_pointer_events(input_handler)
        if handle_tap(events, registry) == NAV_BACK:
            return None

        key = input_handler.last_key()
        if key == KEY_ESC:
            return None


# ─────────────────────────────────────────────────────────────
# Flash helper (port already known)
# ─────────────────────────────────────────────────────────────

def _flash_parts(parts, input_handler, port, extra_flags):
    """Flash (path, addr) pairs using a pre-detected port. Shows progress + result."""
    try:
        _draw_progress("Flashing...", 0)
        flasher.flash(
            port, parts,
            progress_cb=lambda p: _draw_progress("Flashing...", p),
            extra_flags=extra_flags,
        )
    except Exception as e:
        _draw_result(f"Flash failed:\n{str(e)[:36]}", success=False)
        _wait_key(input_handler)
        return False
    _draw_result("Flash complete!", success=True)
    _wait_key(input_handler)
    return True


# ─────────────────────────────────────────────────────────────
# Screen A: Merged binary confirmation  (Yes / No)
# ─────────────────────────────────────────────────────────────

def _confirm_merged(bin_path, input_handler):
    font     = _font()
    filename = os.path.basename(bin_path)
    option   = 0  # 0=Yes (default), 1=No
    registry = HitAreaRegistry()

    def _draw(opt):
        registry.clear()
        img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
        draw = ImageDraw.Draw(img)
        lh   = FONT_SIZE_SM + 4
        _draw_header(draw, font)

        content_h = CONTENT_BOT - CONTENT_TOP
        lines     = ["Want to install:", filename + " ?"]
        total_h   = len(lines) * lh + 14 + lh
        y = CONTENT_TOP + (content_h - total_h) // 2

        for line in lines:
            w = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((SCREEN_W - w) // 2, y), line, fill=COLOR_GREEN, font=font)
            y += lh

        y += 12
        btn_yes, btn_no = "  Yes  ", "  No  "
        by_w = draw.textbbox((0, 0), btn_yes, font=font)[2] + 4
        bn_w = draw.textbbox((0, 0), btn_no,  font=font)[2] + 4
        gap  = 24
        bx_yes = (SCREEN_W - by_w - gap - bn_w) // 2
        bx_no  = bx_yes + by_w + gap

        for i, (bx, bw, btxt) in enumerate([
            (bx_yes, by_w, btn_yes),
            (bx_no,  bn_w, btn_no),
        ]):
            sel = (i == opt)
            draw.rectangle([bx, y, bx + bw, y + lh],
                           fill=(0, 50, 0) if sel else (0, 10, 0),
                           outline=COLOR_GREEN if sel else (0, 40, 0))
            draw.text((bx + 2, y + 1), btxt,
                      fill=COLOR_GREEN if sel else COLOR_DIM, font=font)
            registry.add(i, (bx, y, bx + bw, y + lh))

        draw_navbar(draw, font, registry)
        blit(img)

    _draw(option)

    while True:
        time.sleep(0.05)
        if not input_handler:
            continue
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        # Touch: tapping Yes/No decides immediately (no separate confirm
        # step); tapping the navbar cancels, same as Esc.
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return False
            return tapped == 0

        key = input_handler.last_key()
        if key is None:
            continue
        if key == KEY_LEFT and option != 0:
            option = 0
            _draw(option)
        elif key == KEY_RIGHT and option != 1:
            option = 1
            _draw(option)
        elif key == KEY_ENTER:
            return option == 0
        elif key == KEY_ESC:
            return False


# ─────────────────────────────────────────────────────────────
# Screen B: Multi-part — choose Bundled vs Custom
# ─────────────────────────────────────────────────────────────

def _choose_mode(input_handler):
    """Returns 0=Bundled, 1=Custom, None=ESC."""
    font     = _font()
    option   = 0
    registry = HitAreaRegistry()

    info_lines = [
        "This is a partial (app) firmware.",
        "Bootloader and partition table",
        "are required to flash it.",
    ]
    btn_labels = [
        "Use Launcher bundled files",
        "Use custom files",
    ]

    def _draw(opt):
        registry.clear()
        img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
        draw = ImageDraw.Draw(img)
        lh   = FONT_SIZE_SM + 4
        _draw_header(draw, font)

        content_h = CONTENT_BOT - CONTENT_TOP
        total_h   = (len(info_lines) + 1 + len(btn_labels)) * lh
        y = CONTENT_TOP + (content_h - total_h) // 2

        for line in info_lines:
            draw.text((8, y), line, fill=COLOR_DIM, font=font)
            y += lh
        y += lh

        for i, lbl in enumerate(btn_labels):
            sel = (i == opt)
            bw  = draw.textbbox((0, 0), "  " + lbl + "  ", font=font)[2]
            bx  = 10
            draw.rectangle([bx, y, bx + bw, y + lh - 1],
                           fill=(0, 50, 0) if sel else (0, 10, 0),
                           outline=COLOR_GREEN if sel else (0, 40, 0))
            draw.text((bx + 4, y + 1), lbl,
                      fill=COLOR_GREEN if sel else COLOR_DIM, font=font)
            registry.add(i, (bx, y, bx + bw, y + lh - 1))
            y += lh + 3

        draw_navbar(draw, font, registry)
        blit(img)

    _draw(option)

    while True:
        time.sleep(0.05)
        if not input_handler:
            continue
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        # Touch: tapping a mode selects and confirms it immediately;
        # tapping the navbar cancels, same as Esc.
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return None
            return tapped

        key = input_handler.last_key()
        if key is None:
            continue
        if key in (KEY_UP, KEY_DOWN):
            option = 1 - option
            _draw(option)
        elif key == KEY_ENTER:
            return option
        elif key == KEY_ESC:
            return None


# ─────────────────────────────────────────────────────────────
# Bundled mode
# ─────────────────────────────────────────────────────────────

def _bundled_flash(bin_path, input_handler, port, extra_flags, chip):
    from config import ASSETS_DIR

    env    = flasher.ESP_ENV_NAME.get(chip, "esp32")
    offset = flasher.BOOTLOADER_OFFSET.get(chip, 0x1000)

    bl_path = os.path.join(ASSETS_DIR, env, "bootloader.bin")
    pt_path = os.path.join(ASSETS_DIR, env, "partitions.bin")

    missing = []
    if not os.path.exists(bl_path):
        missing.append(f"bootloader ({env})")
    if not os.path.exists(pt_path):
        missing.append(f"partitions ({env})")
    if missing:
        _draw_result("Missing bundled asset:\n" + ", ".join(missing), success=False)
        _wait_key(input_handler)
        return

    parts = [
        (bl_path,  hex(offset)),
        (pt_path,  "0x8000"),
        (bin_path, "0x10000"),
    ]
    _flash_parts(parts, input_handler, port, extra_flags)


# ─────────────────────────────────────────────────────────────
# Screen C: Custom files table
# ─────────────────────────────────────────────────────────────

def _draw_custom_table(bl_addr, bl_file, pt_file, fw_addr, fw_file, focus, cursor_on, registry=None):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()

    _draw_header(draw, font, "- CUSTOM")

    draw.text((_COL_ADDR_X + 2, _ROW_HDR_Y), "ADDRESS", fill=(0, 70, 0), font=font)
    draw.text((_COL_FILE_X + 2, _ROW_HDR_Y), "FILE",    fill=(0, 70, 0), font=font)
    draw.line([0, _ROW_HDR_Y + _ROW_HDR_H, SCREEN_W, _ROW_HDR_Y + _ROW_HDR_H],
              fill=(0, 25, 0))

    def _cell_addr(y, text, focused, editable):
        bg  = (0, 45, 0) if focused else (0, 12, 0)
        fg  = COLOR_GREEN if focused else ((0, 60, 0) if not editable else COLOR_DIM)
        out = COLOR_GREEN if focused else (0, 30, 0)
        draw.rectangle([_COL_ADDR_X, y, _COL_ADDR_X + _COL_ADDR_W, y + 17],
                       fill=bg, outline=out)
        display = text + ("_" if focused and editable and cursor_on else "")
        max_w = _COL_ADDR_W - 6
        while draw.textbbox((0, 0), display, font=font)[2] > max_w and len(display) > 2:
            display = display[:-1]
        draw.text((_COL_ADDR_X + 3, y + 3), display, fill=fg, font=font)

    def _cell_file(y, filename, focused):
        bg  = (0, 45, 0) if focused else (0, 12, 0)
        out = COLOR_GREEN if focused else (0, 30, 0)
        draw.rectangle([_COL_FILE_X, y, _COL_FILE_X + _COL_FILE_W, y + 17],
                       fill=bg, outline=out)
        max_w = _COL_FILE_W - 6
        if filename:
            label = filename
            while draw.textbbox((0, 0), label, font=font)[2] > max_w and len(label) > 4:
                label = label[1:]
            if label != filename:
                label = "~" + label[1:]
            draw.text((_COL_FILE_X + 3, y + 3), label,
                      fill=COLOR_GREEN if focused else COLOR_DIM, font=font)
        else:
            draw.text((_COL_FILE_X + 3, y + 3), "[ Select file ]",
                      fill=COLOR_ORANGE if focused else (0, 40, 0), font=font)

    _cell_addr(_ROW_1_Y, bl_addr, focused=False, editable=False)
    _cell_file(_ROW_1_Y, os.path.basename(bl_file) if bl_file else None,
               focused=(focus == _FC_BL))

    _cell_addr(_ROW_2_Y, "0x8000", focused=False, editable=False)
    _cell_file(_ROW_2_Y, os.path.basename(pt_file) if pt_file else None,
               focused=(focus == _FC_PT))

    _cell_addr(_ROW_3_Y, fw_addr, focused=(focus == _FC_ADDR), editable=True)
    _cell_file(_ROW_3_Y, os.path.basename(fw_file) if fw_file else None,
               focused=False)

    if registry is not None:
        registry.add(_FC_BL,   (_COL_FILE_X, _ROW_1_Y, _COL_FILE_X + _COL_FILE_W, _ROW_1_Y + 17))
        registry.add(_FC_PT,   (_COL_FILE_X, _ROW_2_Y, _COL_FILE_X + _COL_FILE_W, _ROW_2_Y + 17))
        # Tapping the address cell only focuses it for typing (matches Tab)
        # — Enter on it opens a file picker for the firmware file too, which
        # would be surprising as the *first* touch response to tapping a
        # text field, so that stays keyboard/Enter-only.
        registry.add(_FC_ADDR, (_COL_ADDR_X, _ROW_3_Y, _COL_ADDR_X + _COL_ADDR_W, _ROW_3_Y + 17))

    btn_text = "FLASH FIRMWARE"
    bw = draw.textbbox((0, 0), btn_text, font=font)[2] + 16
    bx = (SCREEN_W - bw) // 2
    sel = (focus == _FC_FLASH)
    draw.rectangle([bx, _BTN_Y, bx + bw, _BTN_Y + _BTN_H],
                   fill=(0, 60, 0) if sel else (0, 20, 0),
                   outline=COLOR_GREEN if sel else (0, 50, 0))
    draw.text((bx + 8, _BTN_Y + 1), btn_text,
              fill=COLOR_GREEN if sel else COLOR_DIM, font=font)
    if registry is not None:
        registry.add(_FC_FLASH, (bx, _BTN_Y, bx + bw, _BTN_Y + _BTN_H))

    draw_navbar(draw, font, registry)
    blit(img)


def _custom_parts_screen(bin_path, input_handler, port, extra_flags, chip):
    bl_offset  = flasher.BOOTLOADER_OFFSET.get(chip, 0x1000)
    bl_addr    = hex(bl_offset)
    bl_file    = ""
    pt_file    = ""
    fw_addr    = "0x10000"
    fw_file    = bin_path
    picker_dir = os.path.dirname(bin_path) or os.path.expanduser("~")

    focus      = _FC_BL
    cursor_on  = True
    last_blink = time.time()
    registry   = HitAreaRegistry()

    def _refresh():
        registry.clear()
        _draw_custom_table(bl_addr, bl_file, pt_file, fw_addr, fw_file, focus, cursor_on, registry)

    def _activate_enter():
        """Runs whatever the currently-focused control does when
        activated — shared by the KEY_ENTER handler and by tapping the
        BL/PT/FLASH cells (tapping ADDR only focuses it for typing —
        handled separately in the tap dispatch below, not through here).
        Returns True if _custom_parts_screen should return now."""
        nonlocal bl_file, pt_file, fw_addr, fw_file, picker_dir, focus
        if focus == _FC_BL:
            from screens import file_picker as _fp
            chosen = _fp.run(start_dir=picker_dir, input_handler=input_handler)
            if chosen:
                bl_file = chosen
            _refresh()
        elif focus == _FC_PT:
            from screens import file_picker as _fp
            chosen = _fp.run(start_dir=picker_dir, input_handler=input_handler)
            if chosen:
                pt_file = chosen
                focus   = _FC_FLASH
            _refresh()
        elif focus == _FC_ADDR:
            from screens import file_picker as _fp
            chosen = _fp.run(start_dir=picker_dir, input_handler=input_handler)
            if chosen:
                fw_file    = chosen
                picker_dir = os.path.dirname(chosen)
            _refresh()
        elif focus == _FC_FLASH:
            if not bl_file:
                _draw_status("Select bootloader.bin first", color=COLOR_ORANGE)
                time.sleep(1.5)
                _refresh()
                return False
            if not pt_file:
                _draw_status("Select partitions.bin first", color=COLOR_ORANGE)
                time.sleep(1.5)
                _refresh()
                return False
            try:
                int(fw_addr, 16)
            except ValueError:
                _draw_status("Invalid firmware address", color=COLOR_ORANGE)
                time.sleep(1.5)
                fw_addr = "0x10000"
                _refresh()
                return False
            parts = [
                (bl_file, bl_addr),
                (pt_file, "0x8000"),
                (fw_file, fw_addr),
            ]
            _flash_parts(parts, input_handler, port, extra_flags)
            return True
        return False

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

        # Touch: BL/PT/FLASH tap reuses the exact same action as keyboard
        # focus+Enter; ADDR tap only focuses the field (matches Tab — Enter
        # on it also opens a picker for the firmware file, which stays
        # keyboard-only to avoid surprising a simple tap-to-type gesture).
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return
            elif tapped == _FC_ADDR:
                focus = _FC_ADDR
                _refresh()
            else:
                focus = tapped
                if _activate_enter():
                    return
            continue

        ch = input_handler.next_char()
        if ch is not None:
            if focus == _FC_ADDR:
                if ch == '\x08':
                    if len(fw_addr) > 1:
                        fw_addr = fw_addr[:-1]
                elif ch in '0123456789abcdefABCDEFx':
                    fw_addr += ch.lower()
                _refresh()
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            return

        elif key == KEY_TAB:
            focus = (focus + 1) % _N_FC
            _refresh()

        elif key == KEY_UP:
            if focus > 0:
                focus -= 1
                _refresh()

        elif key == KEY_DOWN:
            if focus < _N_FC - 1:
                focus += 1
                _refresh()

        elif key == KEY_ENTER:
            if _activate_enter():
                return


# ─────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────

def run(input_handler=None):
    """Full file-install flow: detect device → pick .bin → analyse → flash."""
    # Step 1: require a connected, identified ESP32 before showing anything else
    result = _wait_for_device(input_handler)
    if result is None:
        return
    port, extra_flags, chip, label = result

    # Step 2: browse filesystem for a .bin file
    from screens import file_picker as _fp
    bin_path = _fp.run(
        input_handler=input_handler,
        chip_label=label,
    )
    if not bin_path:
        return

    # Step 3: analyse and flash
    if flasher.is_merged_binary(bin_path):
        if _confirm_merged(bin_path, input_handler):
            _flash_parts([(bin_path, "0x0")], input_handler, port, extra_flags)
    else:
        mode = _choose_mode(input_handler)
        if mode is None:
            return
        if mode == 0:
            _bundled_flash(bin_path, input_handler, port, extra_flags, chip)
        else:
            _custom_parts_screen(bin_path, input_handler, port, extra_flags, chip)
