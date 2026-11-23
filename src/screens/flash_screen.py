import os
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, COLOR_ORANGE, FONT_PATH, FONT_SIZE_SM, NAVBAR_H,
    KEY_ENTER, KEY_ESC,
)
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap
import api
import cache
import flasher

HEADER_H = 22
BAR_W    = SCREEN_W - 40
BAR_X    = 20
BAR_H    = 12
CONTENT_TOP = HEADER_H
CONTENT_BOT = SCREEN_H - NAVBAR_H


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _draw_header(draw, font, name):
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=COLOR_DARK)
    label = name
    while draw.textbbox((0, 0), label, font=font)[2] > SCREEN_W - 12 and len(label) > 4:
        label = label[:-1]
    draw.text((6, 4), label, fill=COLOR_GREEN, font=font)


def _draw_progress(name, stage, pct):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4

    _draw_header(draw, font, name)

    content_h = CONTENT_BOT - CONTENT_TOP
    cy = CONTENT_TOP + content_h // 2 - lh - BAR_H // 2

    draw.text((BAR_X, cy), stage, fill=COLOR_DIM, font=font)
    cy += lh + 6

    # Bar track
    draw.rectangle([BAR_X, cy, BAR_X + BAR_W, cy + BAR_H],
                   fill=(0, 25, 0), outline=(0, 80, 0))
    # Bar fill
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


def _draw_result(name, message, success):
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4

    _draw_header(draw, font, name)

    color = COLOR_GREEN if success else COLOR_GRAY
    lines = message.split("\n")
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


def _draw_multipart_warning(name, registry=None):
    """Draw the multi-part flash warning / confirmation screen."""
    img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    font = _font()
    lh   = FONT_SIZE_SM + 4

    _draw_header(draw, font, name)

    warning_lines = [
        "WARNING: Multi-Part Flash",
        "",
        "This firmware needs a bootloader",
        "& partition table. The files",
        "bundled here may NOT be fully",
        "compatible with this firmware.",
    ]

    content_h = CONTENT_BOT - CONTENT_TOP
    total_h   = len(warning_lines) * lh + 8 + lh
    y = CONTENT_TOP + max(2, (content_h - total_h) // 2)

    for line in warning_lines:
        color = COLOR_ORANGE if line.startswith("WARNING") else (160, 100, 0)
        if line:
            w = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((SCREEN_W - w) // 2, y), line, fill=color, font=font)
        y += lh

    y += 8
    btn_flash, btn_cancel = "  Flash anyway  ", "  Cancel  "
    bf_w = draw.textbbox((0, 0), btn_flash, font=font)[2] + 4
    bc_w = draw.textbbox((0, 0), btn_cancel, font=font)[2] + 4
    gap  = 16
    bx_flash  = (SCREEN_W - bf_w - gap - bc_w) // 2
    bx_cancel = bx_flash + bf_w + gap

    for bid, bx, bw, btxt, color in [
        ("flash",  bx_flash,  bf_w, btn_flash,  COLOR_ORANGE),
        ("cancel", bx_cancel, bc_w, btn_cancel, COLOR_DIM),
    ]:
        draw.rectangle([bx, y, bx + bw, y + lh],
                       fill=(0, 20, 0), outline=color)
        draw.text((bx + 2, y + 2), btxt, fill=color, font=font)
        if registry is not None:
            registry.add(bid, (bx, y, bx + bw, y + lh))

    draw_navbar(draw, font, registry)
    blit(img)


def _wait_key(input_handler):
    """Waits for any keypress OR any tap — this screen shows a "Press any
    key" prompt with no discrete button, so a tap anywhere (no hit-testing
    needed) is the touch equivalent."""
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


def _confirm_multipart(name, input_handler):
    """Show multi-part flash warning. Returns True to proceed, False to cancel."""
    registry = HitAreaRegistry()
    _draw_multipart_warning(name, registry)

    if not input_handler:
        time.sleep(3)
        return True

    while True:
        time.sleep(0.05)
        if input_handler.esc_held_seconds() >= 5.0:
            import sys
            sys.exit(0)

        # Touch: tapping Flash/Cancel decides immediately; tapping the
        # navbar cancels, same as Esc.
        events = drain_pointer_events(input_handler)
        tapped = handle_tap(events, registry)
        if tapped is not None:
            if tapped == NAV_BACK:
                return False
            return tapped == "flash"

        key = input_handler.last_key()
        if key is None:
            continue
        if key == KEY_ENTER:
            return True
        if key == KEY_ESC:
            return False


def _resolve_version(firmware):
    sel = firmware.get("_selected_version")
    if sel:
        return sel
    versions = firmware.get("versions", [])
    if not versions:
        return {}
    return sorted(versions, key=lambda v: v.get("published_at", ""), reverse=True)[0]


def _resolve_file(version):
    return version.get("file", "")


def _safe(s):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def _resolve_split_files(version):
    """Return (bootloader_url, partitions_url, app_url) if this version carries all
    three split-flash components, else None."""
    bootloader = version.get("bootloader")
    partitions = version.get("partitions")
    file_name  = version.get("file")
    if not (bootloader and partitions and file_name):
        return None
    return (
        api.firmware_file_url(bootloader),
        api.firmware_file_url(partitions),
        api.firmware_file_url(file_name),
    )


def _download_and_merge_split(firmware, version, dest, progress_cb):
    """Download bootloader/partitions/app files to a temp dir and merge them into
    dest as a single flashable binary (via esptool merge-bin)."""
    bl_url, pt_url, app_url = _resolve_split_files(version)
    esp = firmware.get("esp", "32")

    with tempfile.TemporaryDirectory() as tmp_dir:
        bl_path  = os.path.join(tmp_dir, "bootloader.bin")
        pt_path  = os.path.join(tmp_dir, "partitions.bin")
        app_path = os.path.join(tmp_dir, "app.bin")

        steps = [(bl_url, bl_path), (pt_url, pt_path), (app_url, app_path)]
        for i, (url, path) in enumerate(steps):
            base = i * 100 // len(steps)
            span = 100 // len(steps)
            flasher.download(
                url, path,
                progress_cb=lambda p, base=base, span=span: progress_cb(base + p * span // 100),
            )

        flasher.merge_split_binary(esp, bl_path, pt_path, app_path, dest)


def run_download(firmware, input_handler=None):
    """Download a firmware binary to persistent cache without flashing.
    Updates the downloaded.json registry so firmware_detail shows FLASH next visit."""
    name    = firmware.get("name", "firmware")
    version = _resolve_version(firmware)

    is_split = flasher.is_split_format(version) and _resolve_split_files(version) is not None
    if not is_split and not _resolve_file(version):
        _draw_result(name, "No file for\nthis version.", success=False)
        _wait_key(input_handler)
        return

    dest = cache.download_path(name, version.get("version", "?"))

    try:
        _draw_progress(name, "Downloading...", 0)
        if is_split:
            _download_and_merge_split(
                firmware, version, dest,
                progress_cb=lambda p: _draw_progress(name, "Downloading...", p),
            )
        else:
            url = api.firmware_file_url(_resolve_file(version))
            flasher.download(
                url, dest,
                progress_cb=lambda p: _draw_progress(name, "Downloading...", p),
            )
        cache.mark_downloaded(firmware, version, dest)
    except Exception as e:
        _draw_result(name, f"Download failed:\n{str(e)[:36]}", success=False)
        _wait_key(input_handler)
        try:
            os.remove(dest)
        except OSError:
            pass
        return

    _draw_result(name, "Downloaded!\nReady to flash.", success=True)
    _wait_key(input_handler)


def run(firmware, input_handler=None):
    """
    Runs the full flash flow: detect port → download (or use cache) → flash → result.
    Returns after the user acknowledges the result screen.
    """
    name      = firmware.get("name", "firmware")
    version   = _resolve_version(firmware)
    file_name = _resolve_file(version)

    is_split = flasher.is_split_format(version) and _resolve_split_files(version) is not None
    if not is_split and not file_name:
        _draw_result(name, "No file for\nthis version.", success=False)
        _wait_key(input_handler)
        return

    url    = api.firmware_file_url(file_name) if file_name else ""
    is_app = flasher.is_app_format(version) and not is_split

    # Use locally cached binary if available; otherwise download to /tmp
    local_path = cache.get_download_path(name, version.get("version", "?"))
    if local_path and os.path.exists(local_path):
        tmp           = local_path
        needs_cleanup = False
    else:
        tmp           = f"/tmp/espflash_{_safe(name)}.bin"
        needs_cleanup = True

    # 1. If multi-part, warn the user first
    if is_app:
        if not _confirm_multipart(name, input_handler):
            return

    # 2. Detect port
    _draw_progress(name, "Detecting ESP32...", 0)
    port, conn_flags = flasher.detect_port()
    if not port:
        _draw_result(name, "No ESP32 detected.\nConnect via USB.", success=False)
        _wait_key(input_handler)
        return

    # 2b. Verify chip model matches firmware target
    expected_esp = firmware.get("esp", "32")
    detected_esp = flasher.detect_chip_type(port, conn_flags)
    if detected_esp and detected_esp != expected_esp:
        expected_label = "ESP32" if expected_esp == "32" else f"ESP32-{expected_esp.upper()}"
        detected_label = "ESP32" if detected_esp == "32" else f"ESP32-{detected_esp.upper()}"
        _draw_result(name, f"Wrong device!\nFirmware: {expected_label}\nDetected: {detected_label}", success=False)
        _wait_key(input_handler)
        return

    # 3. Download if not already cached
    if needs_cleanup:
        try:
            _draw_progress(name, "Downloading...", 0)
            if is_split:
                _download_and_merge_split(
                    firmware, version, tmp,
                    progress_cb=lambda p: _draw_progress(name, "Downloading...", p),
                )
            else:
                flasher.download(
                    url, tmp,
                    progress_cb=lambda p: _draw_progress(name, "Downloading...", p),
                )
        except Exception as e:
            _draw_result(name, f"Download failed:\n{str(e)[:36]}", success=False)
            _wait_key(input_handler)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return

    # 4. If no_reset strategy was used, chip is no longer in download mode — ask user
    if "--before" in conn_flags and "no_reset" in conn_flags:
        _draw_result(name, "Hold BOOT + press RST\nthen press any key", success=True)
        _wait_key(input_handler)

    # 5. Flash
    try:
        _draw_progress(name, "Flashing...", 0)
        if is_app:
            parts = flasher.resolve_parts(firmware, tmp)
        else:
            parts = [(tmp, "0x0")]

        flasher.flash(
            port, parts,
            progress_cb=lambda p: _draw_progress(name, "Flashing...", p),
            extra_flags=conn_flags,
        )
    except Exception as e:
        _draw_result(name, f"Flash failed:\n{str(e)[:36]}", success=False)
        _wait_key(input_handler)
        return
    finally:
        if needs_cleanup:
            try:
                os.remove(tmp)
            except OSError:
                pass

    _draw_result(name, "Flash complete!", success=True)
    _wait_key(input_handler)
