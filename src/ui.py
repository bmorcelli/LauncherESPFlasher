import state
from config import SCREEN_W, SCREEN_H, NAVBAR_H, COLOR_DIM, COLOR_GREEN

_NAVBAR_TEXT = "Nav ↑→↓←  Sel:[OK]  Back:[Esc]  Tab:[NEXT]"

NAV_BACK = "__NAV_BACK__"


def draw_navbar(draw, font, registry=None):
    """Draw the bottom navigation hint bar onto an existing ImageDraw context.
    Background turns orange-tinted when offline mode is active.

    When `registry` (a ui_hitareas.HitAreaRegistry) is passed, the whole bar
    is also registered as a tappable "back" area (id: NAV_BACK) — the touch
    equivalent of pressing Esc. Screens not yet migrated to touch can keep
    passing no registry; behavior is unchanged."""
    y      = SCREEN_H - NAVBAR_H
    bg     = (22, 8, 0)  if state.offline_mode else (0, 12, 0)
    border = (70, 35, 0) if state.offline_mode else (0, 50, 0)
    draw.rectangle([0, y, SCREEN_W, SCREEN_H], fill=bg)
    draw.line([0, y, SCREEN_W, y], fill=border)
    draw.text((4, y + 2), _NAVBAR_TEXT, fill=COLOR_DIM, font=font)
    if registry is not None:
        registry.add(NAV_BACK, (0, y, SCREEN_W, SCREEN_H))


COLOR_OFFLINE_STATUS = (160, 75, 0)


def draw_connection_status(draw, font):
    label = "[OFFLINE]" if state.offline_mode else "[ONLINE]"
    color = COLOR_OFFLINE_STATUS if state.offline_mode else COLOR_GREEN
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text((SCREEN_W - text_w - 6, 4), label, fill=color, font=font)
