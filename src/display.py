"""Thin compatibility shim: `from display import blit` keeps working
unchanged for every screen. The real logic lives in hal/display_backend.py,
picked per the active DeviceProfile.
"""
import os

from hal.device_profile import get_active_profile
from hal.display_backend import FramebufferDisplayBackend, PygameDisplayBackend

_DEV = os.environ.get("ESPFLASHER_DEV") == "1"
_profile = get_active_profile()

if _DEV:
    _backend = PygameDisplayBackend(_profile.screen_w, _profile.screen_h, rotation=_profile.rotation)
else:
    _backend = FramebufferDisplayBackend(
        _profile.fb_device, _profile.screen_w, _profile.screen_h, rotation=_profile.rotation
    )


def blit(img):
    _backend.blit(img)
