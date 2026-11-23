# Manual checklist — new `DeviceProfile`

Use this checklist when testing a new profile (`DeviceProfile`) on real
hardware, whether it's `TDISPLAY_CM0` or a device added later following
the guide in
[architecture.md](architecture.md#how-to-add-a-new-device).
It's manual and intentionally not automated — there's no physical-hardware
CI for this project.

**Baseline first**: run this same checklist on `CARDPUTERZERO` before
closing out the new device's work, to confirm nothing regressed.

## Display

- [ ] The screen renders without visible distortion/cropping across at
      least: `boot` → `device_select` → `firmware_list` →
      `firmware_detail` → `flash_screen`.
- [ ] Rotation/orientation is correct when the device is held the way it's
      meant to be used (text isn't upside down or sideways).
- [ ] If the physical resolution's aspect ratio differs from the logical
      canvas (320×170), the letterbox bars appear symmetrically
      (centered), not offset to one side.

## Keyboard (if `has_keyboard=True`)

- [ ] Arrow keys (↑↓←→) navigate lists and move focus correctly.
- [ ] Enter activates the focused item/button.
- [ ] Esc goes back/cancels.
- [ ] Tab advances focus.
- [ ] Backspace deletes in the filter field.
- [ ] Ctrl+O, Ctrl+R, Ctrl+H (shortcuts documented in the app's guide)
      work.
- [ ] Holding Esc for 5 seconds exits the app.

## Touch (if `has_touch=True`)

- [ ] Tapping a list item (`device_select`, `firmware_list`,
      `file_picker`, `version_select`) selects/activates it.
- [ ] Dragging a finger vertically over a list scrolls it.
- [ ] Tapping the bottom navbar goes back/cancels the current screen.
- [ ] Tapping outside any active area doesn't trigger unwanted navigation.
- [ ] Tapping the filter field opens the on-screen keyboard
      (`ui_keyboard.py`) and the typed text filters the list correctly on
      confirm.
- [ ] On confirmation dialogs (exit the app, multi-part flash, etc.),
      tapping a button decides immediately (no separate confirm tap
      needed).

## Profile / detection

- [ ] Running without `ESPFLASHER_DEV_PROFILE` set (a real device boot,
      not dev mode), `get_active_profile()` picks the right profile on its
      own — confirm via log (`ESPFLASHER_DEBUG_INPUT=1` prints the chosen
      profile at startup) or temporary instrumentation.
- [ ] If auto-detection doesn't recognize the device yet, the app falls
      back to `CARDPUTERZERO` without crashing (a safe, if "wrong",
      behavior until detection is extended).

## Regression

- [ ] Run this whole checklist on `CARDPUTERZERO` (or whatever device
      already worked before) too, and confirm nothing changed.
