"""Combined keyboard + pointer facade used by main.py. Backend selection is
driven entirely by the active DeviceProfile — callers don't need to know
whether the device has touch, a keyboard, both, or neither."""
import os

from hal.device_profile import get_active_profile
from hal.display_backend import physical_to_logical
from hal.input_backend import EvdevKeyboardBackend, PygameKeyboardBackend
from hal.pointer_backend import EvdevTouchBackend, NullPointerBackend, PygamePointerBackend


class InputHandler:
    def __init__(self, keyboard_backend, pointer_backend):
        self._keyboard = keyboard_backend
        self._pointer = pointer_backend

    def start(self):
        self._keyboard.start()
        self._pointer.start()

    def stop(self):
        self._keyboard.stop()
        self._pointer.stop()

    def flush(self):
        self._keyboard.flush()
        # Drain and discard any queued pointer events too — otherwise a tap
        # made just before a screen transition could be replayed as a stale
        # tap against the next screen's (differently laid out) hit areas.
        self._pointer.poll_events()

    def any_key_pressed(self):
        return self._keyboard.any_key_pressed()

    def last_key(self):
        return self._keyboard.last_key()

    def next_char(self):
        return self._keyboard.next_char()

    def esc_held_seconds(self):
        return self._keyboard.esc_held_seconds()

    def poll_pointer_events(self):
        return self._pointer.poll_events()


def build_input_handler(profile=None):
    """Constructs an InputHandler wired up for the given DeviceProfile
    (defaults to the active one), picking evdev vs. pygame backends
    depending on dev mode, and a NullPointerBackend when the profile has no
    touch hardware."""
    if profile is None:
        profile = get_active_profile()
    dev = os.environ.get("ESPFLASHER_DEV") == "1"

    def _transform(px, py):
        return physical_to_logical(
            px, py, profile.logical_w, profile.logical_h, profile.screen_w, profile.screen_h, profile.rotation
        )

    if dev:
        keyboard_backend = PygameKeyboardBackend()
        pointer_backend = PygamePointerBackend(_transform) if profile.has_touch else NullPointerBackend()
    else:
        keyboard_backend = EvdevKeyboardBackend(profile.kb_device)
        pointer_backend = (
            EvdevTouchBackend(profile.touch_device, _transform) if profile.has_touch else NullPointerBackend()
        )

    if os.environ.get("ESPFLASHER_DEBUG_INPUT") == "1":
        print(
            f"[input_facade] profile={profile.name!r} has_touch={profile.has_touch} "
            f"dev={dev} keyboard={type(keyboard_backend).__name__} pointer={type(pointer_backend).__name__}"
        )

    return InputHandler(keyboard_backend, pointer_backend)
