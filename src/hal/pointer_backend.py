"""Pointer/touch input backends.

Mirrors the shape of hal/input_backend.py's keyboard backends: one
interface (PointerBackend), a "no device" implementation, an evdev
implementation for real touch hardware, and a pygame mouse-as-touch
implementation for desktop dev mode.

Only single-touch (first finger/slot) is handled — enough for UI navigation.
Raw device coordinates are converted to logical coordinates via a
`transform_fn(x_raw, y_raw) -> (x, y) | None` supplied by the caller
(typically hal.display_backend.physical_to_logical, bound to the active
DeviceProfile). A None result means the touch landed outside the visible
content area (inside the letterbox border) and is discarded.
"""
import os
import select
import threading
import time
from abc import ABC, abstractmethod

from hal.pointer_event import PointerEvent, KIND_DOWN, KIND_MOVE, KIND_UP, KIND_TAP, KIND_SCROLL

try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

_TAP_MAX_SECONDS = 0.3
_TAP_MAX_MOVE_PX = 12  # physical-pixel tolerance before a down→up is no longer a "tap"

_DEBUG = os.environ.get("ESPFLASHER_DEBUG_INPUT") == "1"


class PointerBackend(ABC):
    @abstractmethod
    def start(self):
        ...

    @abstractmethod
    def stop(self):
        ...

    @abstractmethod
    def poll_events(self):
        """Returns and clears the list of PointerEvent queued since the last call."""


class NullPointerBackend(PointerBackend):
    """Used by profiles with has_touch=False. Zero overhead, zero events."""

    def start(self):
        pass

    def stop(self):
        pass

    def poll_events(self):
        return []


class EvdevTouchBackend(PointerBackend):
    def __init__(self, device_path, transform_fn):
        self.device_path = device_path
        self.transform_fn = transform_fn
        self._queue = []
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._device = None
        self._raw_x = None
        self._raw_y = None
        self._touching = False
        self._down_time = None
        self._down_raw = None

    def start(self):
        if not HAS_EVDEV or not self.device_path:
            return
        try:
            self._device = evdev.InputDevice(self.device_path)
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

    def _emit(self, kind, logical):
        if logical is None:
            return
        x, y = logical
        with self._lock:
            self._queue.append(PointerEvent(x=x, y=y, kind=kind))

    def _current_logical(self):
        if self._raw_x is None or self._raw_y is None:
            return None
        return self.transform_fn(self._raw_x, self._raw_y)

    def _read_loop(self):
        while self._running:
            try:
                r, _, _ = select.select([self._device.fd], [], [], 0.05)
                if not r:
                    continue
                for event in self._device.read():
                    if event.type == evdev.ecodes.EV_ABS:
                        if event.code in (evdev.ecodes.ABS_MT_POSITION_X, evdev.ecodes.ABS_X):
                            self._raw_x = event.value
                        elif event.code in (evdev.ecodes.ABS_MT_POSITION_Y, evdev.ecodes.ABS_Y):
                            self._raw_y = event.value
                    elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                        if event.value == 1:
                            self._touching = True
                            self._down_time = time.time()
                            self._down_raw = (self._raw_x, self._raw_y)
                            self._emit(KIND_DOWN, self._current_logical())
                        elif event.value == 0:
                            self._touching = False
                            logical = self._current_logical()
                            self._emit(KIND_UP, logical)
                            if (
                                logical is not None
                                and self._down_time is not None
                                and self._down_raw is not None
                                and (time.time() - self._down_time) < _TAP_MAX_SECONDS
                            ):
                                dx = abs((self._raw_x or 0) - (self._down_raw[0] or 0))
                                dy = abs((self._raw_y or 0) - (self._down_raw[1] or 0))
                                if dx <= _TAP_MAX_MOVE_PX and dy <= _TAP_MAX_MOVE_PX:
                                    self._emit(KIND_TAP, logical)
                    elif event.type == evdev.ecodes.EV_SYN and self._touching:
                        self._emit(KIND_MOVE, self._current_logical())
            except (OSError, IOError):
                break

    def poll_events(self):
        with self._lock:
            events = self._queue
            self._queue = []
        return events


class PygamePointerBackend(PointerBackend):
    """Mouse-as-touch stand-in for desktop dev mode. Coordinates arrive from
    pygame in the dev window's physical pixel space (the window is sized to
    the active profile's screen_w x screen_h — see PygameDisplayBackend), so
    they go through the same transform_fn as real touch hardware."""

    def __init__(self, transform_fn):
        self.transform_fn = transform_fn
        self._queue = []
        self._pressed = False
        self._down_time = None
        self._down_pos = None

    def start(self):
        import pygame
        from hal import pygame_event_bus
        if not pygame.get_init():
            pygame.init()
        pygame_event_bus.register(self._on_event)

    def stop(self):
        from hal import pygame_event_bus
        pygame_event_bus.unregister(self._on_event)

    def _emit(self, kind, physical_pos):
        logical = self.transform_fn(*physical_pos)
        if _DEBUG:
            print(f"[PygamePointerBackend] {kind} physical={physical_pos} -> logical={logical}")
        if logical is None:
            return
        x, y = logical
        self._queue.append(PointerEvent(x=x, y=y, kind=kind))

    def _on_event(self, event):
        import pygame
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._pressed = True
            self._down_time = time.time()
            self._down_pos = event.pos
            self._emit(KIND_DOWN, event.pos)
        elif event.type == pygame.MOUSEMOTION and self._pressed:
            self._emit(KIND_MOVE, event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._pressed = False
            self._emit(KIND_UP, event.pos)
            if self._down_time is not None and (time.time() - self._down_time) < _TAP_MAX_SECONDS:
                dx = abs(event.pos[0] - self._down_pos[0])
                dy = abs(event.pos[1] - self._down_pos[1])
                if dx <= _TAP_MAX_MOVE_PX and dy <= _TAP_MAX_MOVE_PX:
                    self._emit(KIND_TAP, event.pos)
        elif event.type == pygame.MOUSEWHEEL:
            # Not positional (pygame doesn't attach a screen position to
            # wheel events) — x/y are unused by scroll-kind consumers.
            if _DEBUG:
                print(f"[PygamePointerBackend] scroll dy={event.y}")
            self._queue.append(PointerEvent(x=0, y=0, kind=KIND_SCROLL, dy=event.y))

    def poll_events(self):
        from hal import pygame_event_bus
        pygame_event_bus.pump()
        events = self._queue
        self._queue = []
        return events
