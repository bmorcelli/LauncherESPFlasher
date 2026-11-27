import os

SCREEN_W = 320
SCREEN_H = 170
FB_DEVICE = os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE", "/dev/fb0")
KB_DEVICE = "/dev/input/by-path/platform-3f804000.i2c-event"

API_BASE = "https://api.launcherhub.net"

COLOR_BG     = (0,   0,   0)
COLOR_GREEN  = (0, 255,   0)
COLOR_DIM    = (0, 140,   0)
COLOR_DARK   = (0,  30,   0)
COLOR_GRAY   = (80,  80,  80)
COLOR_WHITE  = (255, 255, 255)
COLOR_ORANGE = (220, 120,   0)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

TARGET_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
DEV_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "fonts",
    "DejaVuSansMono-Bold.ttf",
)
FONT_PATH = (
    DEV_FONT_PATH
    if os.environ.get("ESPFLASHER_DEV") == "1" and os.path.exists(DEV_FONT_PATH)
    else TARGET_FONT_PATH
)
FONT_SIZE_LG = 20
FONT_SIZE_MD = 14
FONT_SIZE_SM = 11

NAVBAR_H = 14   # height of the bottom navigation hint bar

# Linux input key codes (evdev scancode values)
KEY_ESC   = 1
KEY_TAB   = 15
KEY_ENTER = 28
KEY_UP    = 103
KEY_LEFT  = 105
KEY_RIGHT = 106
KEY_DOWN  = 108

# next_char() values. Backspace is '\x08'; Ctrl+H would naturally be the same
# ASCII code, so input backends emit this distinct (non-printable) char for it.
CHAR_CTRL_H    = "\x1f"
