import os
import time

from PIL import Image, ImageDraw, ImageFont
from config import (
    SCREEN_W, SCREEN_H, COLOR_BG, COLOR_GREEN, COLOR_DIM, COLOR_DARK,
    COLOR_GRAY, FONT_PATH, FONT_SIZE_SM,
    KEY_UP, KEY_DOWN, KEY_ENTER, KEY_ESC,
)
from display import blit
from ui import draw_navbar, NAV_BACK
from ui_hitareas import HitAreaRegistry, drain_pointer_events, handle_tap, ListScroll

OVERLAY_W = 220
ROW_H     = 18
MAX_ROWS  = 7
PAD       = 10


def _font():
    if os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, FONT_SIZE_SM)
    return ImageFont.load_default()


def _extract_versions(fw):
    """
    Return a list of version dicts: [{"version": "...", "file": "..."}, ...]
    Handles both a `versions` list and the single-version shape.
    """
    if "versions" in fw and isinstance(fw["versions"], list) and fw["versions"]:
        return fw["versions"]
    ver  = fw.get("version") or fw.get("tag") or "?"
    file = fw.get("file", "")
    return [{"version": ver, "file": file}]


def _draw(background, versions, selected, offset, registry=None):
    img  = background.copy()
    draw = ImageDraw.Draw(img)
    font = _font()

    visible = min(MAX_ROWS, len(versions))
    # PAD + title row + version rows + PAD
    box_h   = PAD + ROW_H + ROW_H * visible + PAD
    bx      = (SCREEN_W - OVERLAY_W) // 2
    by      = (SCREEN_H - box_h) // 2

    # Dim background
    overlay = Image.new("RGBA", (SCREEN_W, SCREEN_H), (0, 0, 0, 180))
    img     = img.convert("RGBA")
    img     = Image.alpha_composite(img, overlay)
    img     = img.convert("RGB")
    draw    = ImageDraw.Draw(img)

    # Box
    draw.rectangle([bx - 1, by - 1, bx + OVERLAY_W + 1, by + box_h + 1], fill=(0, 30, 0))
    draw.rectangle([bx - 1, by - 1, bx + OVERLAY_W + 1, by + box_h + 1], outline=COLOR_GREEN)

    # Title
    draw.text((bx + PAD, by + 2), "SELECT VERSION", fill=COLOR_GREEN, font=font)

    # Rows
    for i in range(visible):
        idx = offset + i
        if idx >= len(versions):
            break
        label = (versions[idx].get("version") or "?")[:9]
        y     = by + PAD + ROW_H + i * ROW_H
        if idx == selected:
            draw.rectangle([bx + 2, y - 1, bx + OVERLAY_W - 2, y + ROW_H - 2], fill=(0, 50, 0))
            draw.text((bx + PAD, y + 1), f"> {label}", fill=COLOR_GREEN, font=font)
        else:
            draw.text((bx + PAD, y + 1), f"  {label}", fill=COLOR_DIM, font=font)

        if registry is not None:
            registry.add(("row", idx), (bx + 2, y - 1, bx + OVERLAY_W - 2, y + ROW_H - 2))

    if registry is not None and len(versions) > visible:
        list_top = by + PAD + ROW_H
        list_bot = list_top + ROW_H * visible
        mid = list_top + (list_bot - list_top) // 2
        registry.add(("scroll", -1), (bx + OVERLAY_W - 16, list_top, bx + OVERLAY_W, mid))
        registry.add(("scroll", 1),  (bx + OVERLAY_W - 16, mid, bx + OVERLAY_W, list_bot))

    draw_navbar(draw, font, registry)
    blit(img)


def run(firmware, input_handler=None):
    """
    Shows a version-selection overlay on top of whatever is on screen.
    Returns the selected version dict, or None if ESC.
    """
    import io
    from PIL import ImageGrab
    # Capture current framebuffer content as background
    try:
        from config import FB_DEVICE, SCREEN_W as W, SCREEN_H as H
        with open(FB_DEVICE, "rb") as fb:
            raw = fb.read(W * H * 2)
        import numpy as np
        arr = np.frombuffer(raw, dtype="<u2").reshape(H, W)
        r = ((arr >> 11) & 0x1F) << 3
        g = ((arr >> 5)  & 0x3F) << 2
        b = (arr & 0x1F) << 3
        background = Image.fromarray(
            np.stack([r, g, b], axis=2).astype("uint8"), "RGB"
        )
    except Exception:
        background = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_BG)

    versions = sorted(
        _extract_versions(firmware),
        key=lambda v: v.get("published_at", ""),
        reverse=True,
    )
    selected = 0
    offset   = 0

    registry    = HitAreaRegistry()
    list_scroll = ListScroll(ROW_H)

    def _refresh():
        registry.clear()
        _draw(background, versions, selected, offset, registry)

    def _scroll(delta):
        nonlocal selected, offset
        if not versions or delta == 0:
            return
        new_selected = max(0, min(len(versions) - 1, selected + delta))
        if new_selected == selected:
            return
        selected = new_selected
        if selected < offset:
            offset = selected
        elif selected >= offset + MAX_ROWS:
            offset = selected - MAX_ROWS + 1
        _refresh()

    _refresh()

    # Box geometry is fixed for the lifetime of this call (versions/MAX_ROWS
    # don't change), so the drag-scroll hit area only needs computing once.
    _visible  = min(MAX_ROWS, len(versions))
    _box_h    = PAD + ROW_H + ROW_H * _visible + PAD
    _by       = (SCREEN_H - _box_h) // 2
    _bx       = (SCREEN_W - OVERLAY_W) // 2
    _list_top = _by + PAD + ROW_H
    list_area = (_bx + 2, _list_top, _bx + OVERLAY_W - 2, _list_top + ROW_H * _visible)

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
            if tapped == NAV_BACK:
                return None
            elif isinstance(tapped, tuple) and tapped[0] == "row":
                return versions[tapped[1]]
            elif isinstance(tapped, tuple) and tapped[0] == "scroll":
                _scroll(tapped[1])
            continue

        scroll_delta = list_scroll.poll(events, list_area)
        if scroll_delta:
            _scroll(scroll_delta)
            continue

        key = input_handler.last_key()
        if key is None:
            continue

        if key == KEY_ESC:
            return None

        elif key == KEY_UP:
            _scroll(-1)

        elif key == KEY_DOWN:
            _scroll(1)

        elif key == KEY_ENTER:
            return versions[selected]
