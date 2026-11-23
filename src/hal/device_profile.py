"""Device profiles: centralize per-device hardware knobs (screen size,
framebuffer/input device paths, logical canvas, rotation). See
docs/architecture.md for the full design and how to add a new device."""
import os
from dataclasses import dataclass
from typing import Optional

from hal import device_discovery


@dataclass
class DeviceProfile:
    name: str
    screen_w: int
    screen_h: int
    fb_device: str
    kb_device: Optional[str]
    has_keyboard: bool
    has_touch: bool = False
    touch_device: Optional[str] = None
    logical_w: int = 320
    logical_h: int = 170
    rotation: int = 0


CARDPUTERZERO = DeviceProfile(
    name="cardputerzero",
    screen_w=320,
    screen_h=170,
    fb_device=os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE", "/dev/fb0"),
    kb_device="/dev/input/by-path/platform-3f804000.i2c-event",
    has_keyboard=True,
    has_touch=False,
    logical_w=320,
    logical_h=170,
    rotation=0,
)

# Lilygo T-Display-CM0: 568x1232 AMOLED (portrait). Keyboard/touch are
# discovered by name since the keyboard is an optional module. rotation=90
# lets the landscape logical canvas fill the portrait panel with minimal
# letterbox when the device is held in landscape.
_TDISPLAY_CM0_TOUCH_DEVICE = device_discovery.find_input_device("goodix")
_TDISPLAY_CM0_KB_DEVICE    = device_discovery.find_input_device("tca8418")

TDISPLAY_CM0 = DeviceProfile(
    name="tdisplay_cm0",
    screen_w=568,
    screen_h=1232,
    fb_device=os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE", "/dev/fb0"),
    kb_device=_TDISPLAY_CM0_KB_DEVICE,
    has_keyboard=_TDISPLAY_CM0_KB_DEVICE is not None,
    has_touch=True,
    touch_device=_TDISPLAY_CM0_TOUCH_DEVICE,
    logical_w=320,
    logical_h=170,
    rotation=90,
)

# Dev-only preview profile (desktop, no real hardware) for visually testing
# scaling/rotation/touch. Kept separate from TDISPLAY_CM0 so local tweaks
# for a desktop monitor don't leak into the real device profile.
_TDISPLAY_CM0_PREVIEW = DeviceProfile(
    name="tdisplay_cm0_preview",
    screen_w=1232, # 568
    screen_h=568, # 1232
    fb_device=os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE", "/dev/fb0"),
    kb_device=CARDPUTERZERO.kb_device,
    has_keyboard=True,
    has_touch=True,   # lets PygamePointerBackend be exercised via mouse clicks
    touch_device=None,  # not used in dev mode (PygamePointerBackend ignores it)
    logical_w=320,
    logical_h=170,
    rotation=0, # 90
)

_KNOWN_PROFILES = {
    CARDPUTERZERO.name: CARDPUTERZERO,
    TDISPLAY_CM0.name: TDISPLAY_CM0,
    _TDISPLAY_CM0_PREVIEW.name: _TDISPLAY_CM0_PREVIEW,
}


def _read_device_tree_model():
    try:
        with open("/proc/device-tree/model", "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip("\x00").strip()
    except OSError:
        return None


def _detect_profile():
    """Best-effort hardware auto-detection for production (no
    ESPFLASHER_DEV_PROFILE override). Never raises — falls back to
    CARDPUTERZERO whenever detection is inconclusive (including when not
    running on real hardware at all, e.g. Windows/dev)."""
    model = _read_device_tree_model()
    if model and "compute module" in model.lower():
        if device_discovery.find_input_device("goodix") is not None:
            return TDISPLAY_CM0
    return CARDPUTERZERO


def get_active_profile() -> DeviceProfile:
    """Returns the DeviceProfile for the currently running device.

    ESPFLASHER_DEV_PROFILE can override the selection (dev-only convenience,
    e.g. "tdisplay_cm0" or "tdisplay_cm0_preview") to preview a different
    physical resolution/orientation without needing the real hardware.
    Otherwise, production auto-detection is attempted (see _detect_profile);
    CARDPUTERZERO is the default/fallback.
    """
    override = os.environ.get("ESPFLASHER_DEV_PROFILE")
    if override in _KNOWN_PROFILES:
        return _KNOWN_PROFILES[override]
    return _detect_profile()
