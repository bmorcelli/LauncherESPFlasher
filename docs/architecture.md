# Architecture: multi-device hardware abstraction layer (HAL)

This document describes the current state of the code: how the display,
keyboard, and touch abstraction works, and how to add support for a new
device. If anything here disagrees with the code, trust the code — but
please send a fix to this file.

## Flow overview

```
screens/*.py (device_select, firmware_list, firmware_detail, ...)
    │
    ├─ draws onto a PIL.Image at a fixed LOGICAL resolution (320×170)
    │
    ├─ display.blit(img) ─────────────────────────────────────────────┐
    │                                                                 │
    ├─ ui_hitareas.drain_pointer_events(input_handler)                │
    │      → handle_tap(events, registry)      (discrete taps)        │
    │      → ListScroll(row_h).poll(events, area)   (drag/wheel)      │
    │                                                                 │
    └─ input_handler.last_key() / next_char() / esc_held_seconds()    │
           (keyboard — same API as before the HAL existed)            │
                                                                      │
hal.input_facade.InputHandler (built once in main.py via              │
build_input_handler(), passed down through every screen)              │
    │                                                                 │
    ├─ hal.input_backend.{EvdevKeyboardBackend,PygameKeyboardBackend} │
    │                                                                 │
    └─ hal.pointer_backend.{EvdevTouchBackend,PygamePointerBackend,   │
                             NullPointerBackend}                      │
           → emits hal.pointer_event.PointerEvent in LOGICAL          │
             coordinates (converted via display_backend.physical_to_  │
             logical, the exact inverse of fit_to_screen)             │
                                                                      │
hal.display_backend.{FramebufferDisplayBackend,PygameDisplayBackend} ◄┘
    │
    └─ fit_to_screen(img, screen_w, screen_h, rotation)
           → scale + letterbox + rotate → real framebuffer (/dev/fb0)
             or a pygame window (dev mode)

hal.device_profile.get_active_profile()
    → DeviceProfile (screen_w/h, logical_w/h, rotation, fb_device,
      kb_device, touch_device, has_keyboard, has_touch)
    → consulted by display.py (shim), input_facade.build_input_handler()
      and the backends above
```

Every `screens/*.py` file only ever touches `display.blit(img)`,
`ui_hitareas.*`, and the methods on the `input_handler` it's given as a
parameter. No screen imports `hal.*` directly or knows whether it's
running on the CardputerZero, the T-Display-CM0, or some third device.

## Logical canvas vs. physical resolution

- **Logical canvas** (`DeviceProfile.logical_w`/`logical_h`, currently
  always 320×170): the resolution `screens/*.py` draws at. It's also the
  same resolution as `config.SCREEN_W`/`SCREEN_H`, imported directly by
  every screen for layout math — **this never changes between devices**,
  which is why no screen had to be rewritten to support a physical screen
  with a completely different aspect ratio.
- **Physical resolution** (`DeviceProfile.screen_w`/`screen_h`): the
  device's actual panel size (320×170 on the CardputerZero, 568×1232 on
  the T-Display-CM0).
- The conversion happens in both directions, both in
  `hal/display_backend.py`:
  - **Logical → physical** (video output): `fit_to_screen()` scales
    (aspect-preserving, using `NEAREST` to keep bitmap text crisp),
    rotates (`DeviceProfile.rotation`, multiples of 90°), and centers with
    black letterbox bars. When physical == logical and rotation is 0 (the
    CardputerZero case), it's a no-op — pixel-identical to the pre-HAL
    behavior.
  - **Physical → logical** (touch input): `physical_to_logical()` is the
    exact inverse of `fit_to_screen()` — same scale, same centering
    offset, same rotation undone. Returns `None` when a touch lands
    outside the visible content area (inside the letterbox), and the
    pointer backend discards those before they ever become a
    `PointerEvent`.

## Profile reference table

| Field | `CARDPUTERZERO` | `TDISPLAY_CM0` |
|---|---|---|
| `name` | `"cardputerzero"` | `"tdisplay_cm0"` |
| `screen_w` × `screen_h` | 320 × 170 | 568 × 1232 (portrait) |
| `logical_w` × `logical_h` | 320 × 170 | 320 × 170 |
| `rotation` | 0 | 90 |
| `fb_device` | `/dev/fb0` (override via `APPLAUNCH_LINUX_FBDEV_DEVICE`) | same |
| `kb_device` | fixed path `/dev/input/by-path/platform-3f804000.i2c-event` | resolved via `device_discovery.find_input_device("tca8418")` (`None` if the optional keyboard module isn't present) |
| `has_keyboard` | `True` | `kb_device is not None` |
| `has_touch` | `False` | `True` |
| `touch_device` | `None` | `device_discovery.find_input_device("goodix")` |

There's also `_TDISPLAY_CM0_PREVIEW` (name `"tdisplay_cm0_preview"`) — a
**desktop-only, no-real-hardware** profile used to visually validate
scaling/rotation/touch via mouse before `TDISPLAY_CM0` existed. It isn't a
third device — it's a testing tool, kept separate so convenience tweaks
(a different resolution/rotation that's easier to see on a PC monitor)
don't leak into the real profile.

## Runtime profile selection

`hal.device_profile.get_active_profile()`:

1. If `ESPFLASHER_DEV_PROFILE` is set to a known name
   (`"cardputerzero"`, `"tdisplay_cm0"`, `"tdisplay_cm0_preview"`), that
   profile is used directly — this is the manual-testing mechanism used
   throughout development, combined with `ESPFLASHER_DEV=1` to run in
   desktop/pygame mode.
2. Otherwise, auto-detection is attempted (`_detect_profile()`): reads
   `/proc/device-tree/model`, looks for the substring `"compute module"`
   (case-insensitive), and confirms with
   `device_discovery.find_input_device("goodix") is not None`. If both
   match → `TDISPLAY_CM0`.
3. Any detection failure (file missing, substring doesn't match, no
   Goodix) falls back to `CARDPUTERZERO` — this never raises.

## Dynamic input discovery (`hal/device_discovery.py`)

`find_input_device(name_substring, case_insensitive=True, devices_path=...)`
reads `/proc/bus/input/devices`, finds the block whose `N: Name="..."`
contains the substring, and returns the `/dev/input/eventN` from its
`H: Handlers=` line. Returns `None` (never raises) if not found or if the
file doesn't exist — this matters because on devices like the
T-Display-CM0 the keyboard is an optional expansion module, and event-node
indices aren't stable across boots.

`EvdevKeyboardBackend.start()` (in `hal/input_backend.py`) uses this as a
**fallback**: it tries the profile's fixed `kb_device` first and, if that
fails, tries `find_input_device("tca8418")` — so even `CARDPUTERZERO`,
whose path is fixed, keeps working if that path ever changes.

To find the right substring on real hardware:

```sh
cat /proc/bus/input/devices | less
# find your peripheral's block and note the quoted text after N: Name=
```

## Display backends (`hal/display_backend.py`)

- `DisplayBackend` (abstract): a single `blit(img)` method.
- `FramebufferDisplayBackend(fb_device, screen_w, screen_h, rotation)`:
  production — writes raw RGB565 to `fb_device` (numpy if available, a
  pure-Python loop as fallback).
- `PygameDisplayBackend(screen_w, screen_h, rotation)`: dev mode
  (`ESPFLASHER_DEV=1`) — a pygame window sized to the profile's physical
  resolution.
- Both call `fit_to_screen()` before writing/blitting.

## Keyboard backends (`hal/input_backend.py`)

- `InputBackend` (abstract): `start()`, `stop()`, `flush()`,
  `any_key_pressed()`, `last_key()`, `next_char()`, `esc_held_seconds()`.
- `EvdevKeyboardBackend(kb_device=None)`: production, a dedicated thread
  reading scancodes via `evdev`; the path is resolved from the active
  profile when not passed explicitly.
- `PygameKeyboardBackend()`: dev mode, translates PC keyboard events.
  Consumes events through `hal/pygame_event_bus.py` — a shared pump
  needed because the keyboard and pointer backends, both in dev mode, read
  from the same pygame event queue; without the bus, whichever one called
  `pygame.event.get()` first would "steal" the other's events.

## Pointer/touch backends (`hal/pointer_backend.py`, `hal/pointer_event.py`)

- `PointerEvent(x, y, kind, dy=0)` — coordinates are always logical;
  `kind` is one of `"down" | "move" | "up" | "tap" | "scroll"`
  (`"scroll"` is the desktop mouse wheel; `dy` carries the notch count,
  x/y are unused).
- `PointerBackend` (abstract): `start()`, `stop()`, `poll_events()`.
- `NullPointerBackend`: used when `has_touch=False` — always returns an
  empty list, zero overhead.
- `EvdevTouchBackend(device_path, transform_fn)`: production,
  single-touch (first finger/slot), reads `ABS_MT_POSITION_X/Y` +
  `BTN_TOUCH`, synthesizes `"tap"` when a down→up happens quickly
  (`<0.3s`) with little movement (`<12` physical px). `transform_fn` is
  `hal.display_backend.physical_to_logical` bound to the active profile.
- `PygamePointerBackend(transform_fn)`: dev mode, mouse as a touch
  stand-in — same `transform_fn`, same tap logic, plus `MOUSEWHEEL`
  support (emits `"scroll"`).

## Combined keyboard+pointer (`hal/input_facade.py`)

`build_input_handler(profile=None)` builds the right `InputHandler` (dev
vs. production, with/without touch) from the active `DeviceProfile` — it's
the only thing `main.py` calls:

```python
from hal.input_facade import build_input_handler
kbd = build_input_handler()
kbd.start()
```

`InputHandler` exposes the same keyboard methods as always, plus
`poll_pointer_events()`. `flush()` clears the keyboard **and** drains/
discards any pending pointer events (so a tap made right before a screen
transition can't be replayed against the next screen's hit areas).

## Hit-testing and touch scrolling (`src/ui_hitareas.py`)

Used by screens (UI-level, not part of `hal/`):

- `HitAreaRegistry` — each screen creates one, `clear()`s and repopulates
  it on every `_draw()`, registering the same rectangles it already draws
  (`(x0, y0, x1, y1)`) with an arbitrary `id` (`FOCUS_*` constants, tuples
  like `("row", idx)` or `("scroll", ±1)`, etc.).
- `drain_pointer_events(input_handler)` — drains pointer events **once
  per main-loop iteration**; the result is fed to both `handle_tap()` and
  `ListScroll.poll()` in the same tick (never call
  `poll_pointer_events()` directly in more than one place per iteration —
  the second consumer would get nothing).
- `handle_tap(events, registry)` — hit-tests `"tap"` events against the
  registry, returns the tapped area's `id` (or `None`).
- `ListScroll(row_h)` — drag (real touch, or mouse-down-drag in dev) and
  mouse wheel (dev) for scrolling lists, converted into "how many rows to
  scroll" (`poll(events, area_rect) -> int`). Used by `device_select.py`,
  `firmware_list.py`, `file_picker.py`, `version_select.py`, and the
  description box in `firmware_detail.py`.

## On-screen keyboard (`src/ui_keyboard.py`)

A modal, tappable QWERTY keyboard widget (`ui_keyboard.run(input_handler,
initial_text="", placeholder="...")`, returns the typed text or `None` if
cancelled). Used when a text field (today: the filter field in
`device_select.py`/`firmware_list.py`) is tapped on a device with no
physical keyboard — a physical keyboard, if present, keeps working in
parallel (same `next_char()`/`last_key()` API).

## What's not abstracted yet

- **Native responsive layouts.** Screens always draw at 320×170 logical;
  very different physical screens get scale+letterbox, not a layout
  redesigned to use the extra space (e.g. the T-Display-CM0 has a much
  larger physical area than the scaled-up 320×170 content fills).
- **A physical USB mouse as a distinct device from touch.** Today there's
  only real touch (`EvdevTouchBackend`) or mouse-as-touch in dev mode
  (`PygamePointerBackend`) — a USB mouse plugged into a target device has
  no dedicated backend (it could reuse `EvdevTouchBackend`'s mechanism
  with a different event filter, but that hasn't been done).
- **A dedicated numeric keypad.** The hex address field in
  `file_install.py` (`_custom_parts_screen`) is editable via physical
  keyboard, but tapping it only focuses it — it doesn't open
  `ui_keyboard.py` (a full QWERTY, not ideal for hex) or a numeric keypad.
- **`boot.py`** has — and needs — no interaction at all (it's a splash
  screen that advances on its own); that's intentional, not a gap.

## How to add a new device

1. **Gather the specs**: physical resolution, natural holding orientation,
   whether the screen exposes a standard framebuffer (`/dev/fb*`) or needs
   direct KMS/DRM (the current HAL only knows how to write a raw
   framebuffer — a device requiring DRM/KMS would need a new
   `DisplayBackend`), and the input device names/paths.

2. **Add a `DeviceProfile`** in `src/hal/device_profile.py`:

   ```python
   # Hypothetical example — a generic ClockworkPi, 480x800 portrait
   # screen, no dedicated physical keyboard, some capacitive touch panel.
   _CLOCKWORKPI_TOUCH_DEVICE = device_discovery.find_input_device("clockworkpi-touch")

   CLOCKWORKPI = DeviceProfile(
       name="clockworkpi",
       screen_w=480,
       screen_h=800,
       fb_device=os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE", "/dev/fb0"),
       kb_device=None,
       has_keyboard=False,
       has_touch=True,
       touch_device=_CLOCKWORKPI_TOUCH_DEVICE,
       logical_w=320,
       logical_h=170,
       rotation=90,  # or 270 — depends on how the device is held
   )

   _KNOWN_PROFILES[CLOCKWORKPI.name] = CLOCKWORKPI
   ```

3. **If the input has no fixed path**, use
   `device_discovery.find_input_device("<substring>")` as above. To find
   the right substring, run this on the real device:

   ```sh
   cat /proc/bus/input/devices | less
   ```

   and look for the quoted text in the target peripheral's `N: Name="..."`
   — don't guess.

4. **Test in dev mode before touching real hardware**:

   ```sh
   ESPFLASHER_DEV_PROFILE=clockworkpi ESPFLASHER_DEV=1 ./run-dev.sh
   ```

   Visually confirm scale/rotation/letterbox, and if `has_touch=True`,
   that mouse clicks (add `ESPFLASHER_DEBUG_INPUT=1` to see per-event
   logs) navigate correctly.

5. **Auto-detection (optional)**: if the device should be selected on its
   own in production (without setting `ESPFLASHER_DEV_PROFILE` manually),
   extend `_detect_profile()` in `device_profile.py` with a new condition
   — today it only knows how to recognize `TDISPLAY_CM0` via
   `/proc/device-tree/model`. If that's not feasible or necessary,
   selecting via an environment variable (or a persisted config file,
   which this project doesn't have yet) is acceptable.
