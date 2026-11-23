"""PIL-drawn header icons. All functions return RGBA images (transparent background)."""
import math
from PIL import Image, ImageDraw

_DEFAULT_SIZE = 14


def _new(size):
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def refresh_icon(color=(0, 255, 0), size=_DEFAULT_SIZE):
    """Clockwise circular arrow (↻ style). 280° arc with arrowhead."""
    img  = _new(size)
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2.0
    r  = size / 2.0 - 2.0

    # 280° arc: 30° → 310° clockwise (gap stays on the right side of the icon)
    a_start, a_end = 30, 310
    steps = 26
    pts = [
        (cx + r * math.cos(math.radians(a_start + (a_end - a_start) * i / steps)),
         cy + r * math.sin(math.radians(a_start + (a_end - a_start) * i / steps)))
        for i in range(steps + 1)
    ]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=1)

    # Arrowhead at end (310°) pointing in direction of clockwise travel
    a    = math.radians(310)
    tip  = (cx + r * math.cos(a), cy + r * math.sin(a))
    tang = (-math.sin(a), math.cos(a))   # tangent: d/da(cos,sin)
    norm = (-tang[1], tang[0])            # perpendicular
    ah   = 2.2
    p1 = (tip[0] - tang[0]*ah + norm[0]*ah, tip[1] - tang[1]*ah + norm[1]*ah)
    p2 = (tip[0] - tang[0]*ah - norm[0]*ah, tip[1] - tang[1]*ah - norm[1]*ah)
    draw.polygon([tip, p1, p2], fill=color)
    return img


def info_icon(color=(0, 255, 0), size=_DEFAULT_SIZE):
    """Circle with 'i' inside (ⓘ style)."""
    img  = _new(size)
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    r  = size // 2 - 1
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=1)
    dot_y = cy - 2
    draw.ellipse([cx - 1, dot_y - 1, cx + 1, dot_y + 1], fill=color)
    draw.line([(cx, dot_y + 3), (cx, cy + r - 2)], fill=color, width=1)
    return img


def folder_icon(color=(0, 255, 0), size=_DEFAULT_SIZE):
    """Folder outline with tab."""
    img  = _new(size)
    draw = ImageDraw.Draw(img)
    body_top = size * 4 // 10
    tab_w    = size * 4 // 10
    tab_top  = body_top - max(2, size // 6)
    draw.rectangle([0, body_top, size - 1, size - 1], outline=color, width=1)
    draw.rectangle([0, tab_top,  tab_w,   body_top],  outline=color, width=1)
    return img


def wifi_icon(color=(0, 255, 0), connected=True, size=_DEFAULT_SIZE):
    """WiFi symbol (3 arcs + center dot). Diagonal strikethrough when disconnected."""
    img  = _new(size)
    draw = ImageDraw.Draw(img)
    cx    = size // 2
    dot_y = size - 3
    # 3 arcs opening upward, all centered at the dot position
    for r in (2, 4, 6):
        draw.arc(
            [cx - r, dot_y - r, cx + r, dot_y + r],
            start=210, end=330, fill=color, width=1,
        )
    draw.ellipse([cx - 1, dot_y - 1, cx + 1, dot_y + 1], fill=color)
    if not connected:
        draw.line([(2, 2), (size - 3, size - 3)], fill=color, width=1)
    return img


def up_icon(color=(0, 255, 0), size=_DEFAULT_SIZE):
    """Folder-up arrow: an upward chevron over a short baseline, used as a
    visible "go to parent directory" touch button."""
    img  = _new(size)
    draw = ImageDraw.Draw(img)
    cx = size / 2.0
    top    = 1
    bottom = size - 3
    half_w = size / 2.0 - 2.0
    draw.line([(cx, top), (cx - half_w, top + half_w)], fill=color, width=1)
    draw.line([(cx, top), (cx + half_w, top + half_w)], fill=color, width=1)
    draw.line([(cx, top), (cx, bottom)], fill=color, width=1)
    draw.line([(2, size - 2), (size - 3, size - 2)], fill=color, width=1)
    return img


def paste_icon(img, icon_rgba, x, y):
    """Composite an RGBA icon onto an RGB (or RGBA) image using alpha as mask."""
    alpha   = icon_rgba.split()[3]
    rgb_ico = icon_rgba.convert("RGB")
    img.paste(rgb_ico, (x, y), mask=alpha)
