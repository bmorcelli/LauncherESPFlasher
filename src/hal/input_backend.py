"""Keyboard input backends: EvdevKeyboardBackend (real hardware) and
PygameKeyboardBackend (desktop dev mode), behind the InputBackend interface."""
import select
import threading
import time
from abc import ABC, abstractmethod

try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

# Scancode → printable character (US QWERTY, no shift)
_SCANCODE_TO_CHAR = {
    2: '1',  3: '2',  4: '3',  5: '4',  6: '5',
    7: '6',  8: '7',  9: '8', 10: '9', 11: '0',
    16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't',
    21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',
    30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g',
    35: 'h', 36: 'j', 37: 'k', 38: 'l',
    44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b',
    49: 'n', 50: 'm',
    57: ' ',
    12: '-', 13: '=', 26: '[', 27: ']',
    39: ';', 40: "'", 51: ',', 52: '.', 53: '/',
}

_KEY_BACKSPACE = 14
_KEY_CTRL_L    = 29
_KEY_CTRL_R    = 97


class InputBackend(ABC):
    @abstractmethod
    def start(self):
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def flush(self):
        ...

    @abstractmethod
    def any_key_pressed(self):
        ...

    @abstractmethod
    def last_key(self):
        ...

    @abstractmethod
    def next_char(self):
        ...

    @abstractmethod
    def esc_held_seconds(self):
        ...


class EvdevKeyboardBackend(InputBackend):
    def __init__(self, kb_device=None):
        if kb_device is None:
            from hal.device_profile import get_active_profile
            kb_device = get_active_profile().kb_device
        self.kb_device = kb_device
        self._any_pressed = False
        self._last_key = None
        self._last_char = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._device = None
        self._ctrl_held = False  # not locked; GIL makes bool reads safe on CPython
        self._esc_down_time = None

    def start(self):
        if not HAS_EVDEV:
            return

        device_path = self.kb_device
        if device_path is not None:
            try:
                self._device = evdev.InputDevice(device_path)
            except (FileNotFoundError, PermissionError, OSError):
                self._device = None

        if self._device is None:
            # Fixed path missing/stale — fall back to discovering the
            # keyboard by name (event-node numbers aren't stable across
            # boots, and on some devices the keyboard is an optional
            # expansion module with no fixed path at all).
            from hal.device_discovery import find_input_device
            fallback_path = find_input_device("tca8418")
            if fallback_path is None or fallback_path == device_path:
                return
            try:
                self._device = evdev.InputDevice(fallback_path)
            except (FileNotFoundError, PermissionError, OSError):
                return

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._device:
            try:
                self._device.close()
            except OSError:
                pass

    def _read_loop(self):
        while self._running:
            try:
                r, _, _ = select.select([self._device.fd], [], [], 0.05)
                if r:
                    for event in self._device.read():
                        if event.type == evdev.ecodes.EV_KEY:
                            key = evdev.categorize(event)
                            sc = key.scancode
                            if key.keystate in (key.key_down, key.key_hold):
                                if key.keystate == key.key_down and sc == 1:  # ESC first press
                                    if self._esc_down_time is None:
                                        self._esc_down_time = time.time()
                                if sc in (_KEY_CTRL_L, _KEY_CTRL_R):
                                    self._ctrl_held = True
                                    continue
                                with self._lock:
                                    self._any_pressed = True
                                    self._last_key = sc
                                    ch = _SCANCODE_TO_CHAR.get(sc)
                                    if sc == _KEY_BACKSPACE:
                                        self._last_char = '\x08'
                                    elif ch:
                                        # Ctrl+letter → control character (e.g. Ctrl+O = \x0f)
                                        self._last_char = chr(ord(ch) & 0x1f) if self._ctrl_held else ch
                            elif key.keystate == key.key_up:
                                if sc == 1:  # ESC released
                                    self._esc_down_time = None
                                if sc in (_KEY_CTRL_L, _KEY_CTRL_R):
                                    self._ctrl_held = False
            except (OSError, IOError):
                break

    def any_key_pressed(self):
        """Returns True once if any key was pressed since last call."""
        with self._lock:
            pressed = self._any_pressed
            self._any_pressed = False
        return pressed

    def last_key(self):
        """Returns the scancode of the last key pressed, then clears it."""
        with self._lock:
            k = self._last_key
            self._last_key = None
        return k

    def next_char(self):
        """Returns the next typed character (or '\\x08' for backspace), then clears it."""
        with self._lock:
            c = self._last_char
            self._last_char = None
        return c

    def flush(self):
        """Clear pending key state."""
        with self._lock:
            self._any_pressed = False
            self._last_key = None
            self._last_char = None
        self._ctrl_held = False
        self._esc_down_time = None

    def esc_held_seconds(self):
        """Returns how long ESC has been held (0.0 if not held)."""
        t = self._esc_down_time
        return time.time() - t if t is not None else 0.0


class PygameKeyboardBackend(InputBackend):
    """Pygame-backed InputBackend for desktop dev mode (ESPFLASHER_DEV=1).
    Exposes the same interface as EvdevKeyboardBackend — screens need no changes."""

    _KEY_MAP = None  # built once after first pygame import

    def __init__(self):
        self._last_scancode  = None
        self._last_char      = None
        self._any_pressed    = False
        self._esc_down_time  = None

    @classmethod
    def _keymap(cls):
        if cls._KEY_MAP is None:
            import pygame
            cls._KEY_MAP = {
                pygame.K_UP:       103,  # KEY_UP
                pygame.K_DOWN:     108,  # KEY_DOWN
                pygame.K_LEFT:     105,  # KEY_LEFT
                pygame.K_RIGHT:    106,  # KEY_RIGHT
                pygame.K_RETURN:    28,  # KEY_ENTER
                pygame.K_KP_ENTER:  28,
                pygame.K_ESCAPE:     1,  # KEY_ESC
                pygame.K_TAB:       15,  # KEY_TAB
            }
        return cls._KEY_MAP

    def start(self):
        import pygame
        from hal import pygame_event_bus
        if not pygame.get_init():
            pygame.init()
        pygame_event_bus.register(self._on_event)

    def stop(self):
        from hal import pygame_event_bus
        pygame_event_bus.unregister(self._on_event)

    def flush(self):
        self._last_scancode = None
        self._last_char     = None
        self._any_pressed   = False
        self._esc_down_time = None

    def esc_held_seconds(self):
        """Returns how long ESC has been held (0.0 if not held)."""
        t = self._esc_down_time
        return time.time() - t if t is not None else 0.0

    def _on_event(self, event):
        import pygame
        km = self._keymap()
        if event.type == pygame.KEYDOWN:
            ctrl = bool(event.mod & (pygame.KMOD_LCTRL | pygame.KMOD_RCTRL))

            if event.key == pygame.K_BACKSPACE:
                self._last_char   = '\x08'
                self._any_pressed = True
            elif event.key in km:
                self._last_scancode = km[event.key]
                self._any_pressed   = True
                if event.key == pygame.K_ESCAPE and self._esc_down_time is None:
                    self._esc_down_time = time.time()
            elif ctrl and pygame.K_a <= event.key <= pygame.K_z:
                # Ctrl+letter → control char: K_a=97, chr(97-96)=chr(1)=Ctrl+A
                # K_o=111, chr(111-96)=chr(15)='\x0f'=Ctrl+O
                self._last_char   = chr(event.key - 96)
                self._any_pressed = True
            elif event.unicode:
                self._last_char   = event.unicode
                self._any_pressed = True
        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_ESCAPE:
                self._esc_down_time = None

    def _pump(self):
        from hal import pygame_event_bus
        pygame_event_bus.pump()

    def any_key_pressed(self):
        self._pump()
        p = self._any_pressed
        self._any_pressed = False
        return p

    def last_key(self):
        self._pump()
        k = self._last_scancode
        self._last_scancode = None
        return k

    def next_char(self):
        self._pump()
        c = self._last_char
        self._last_char = None
        return c
