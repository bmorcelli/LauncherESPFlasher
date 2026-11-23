"""Dynamic input-device discovery by name, reading /proc/bus/input/devices.

Needed because on the T-Display-CM0 the keyboard is an optional expansion
module (not always present) and event-node indices (/dev/input/eventN)
aren't stable across boots — the reference app (keyboard_ext.c's
find_tca8418_event()) solves this the same way: scan by device name
instead of hardcoding a path.

/proc/bus/input/devices format (relevant lines), one block per device:

    I: Bus=0018 Vendor=0000 Product=0000 Version=0000
    N: Name="Goodix Berlin Capacitive TouchScreen"
    P: Phys=i2c-10-0037
    ...
    H: Handlers=event4 mouse1
    ...
    (blank line separates blocks)
"""
import re

_PROC_INPUT_DEVICES = "/proc/bus/input/devices"

_NAME_RE = re.compile(r'^N:\s*Name="(.*)"\s*$')
_HANDLERS_RE = re.compile(r"^H:\s*Handlers=(.*)$")
_EVENT_RE = re.compile(r"\bevent(\d+)\b")


def find_input_device(name_substring, case_insensitive=True, devices_path=_PROC_INPUT_DEVICES):
    """Returns "/dev/input/eventN" for the first device block whose N: Name
    contains name_substring, or None if not found (including when
    devices_path doesn't exist/can't be read — never raises).

    devices_path is overridable for testing against a synthetic fixture
    instead of the real /proc/bus/input/devices.
    """
    try:
        with open(devices_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return None

    needle = name_substring.lower() if case_insensitive else name_substring

    for block in content.split("\n\n"):
        name = None
        event_num = None
        for line in block.splitlines():
            m = _NAME_RE.match(line)
            if m:
                name = m.group(1)
                continue
            m = _HANDLERS_RE.match(line)
            if m:
                ev = _EVENT_RE.search(m.group(1))
                if ev:
                    event_num = ev.group(1)

        if name is None:
            continue
        haystack = name.lower() if case_insensitive else name
        if needle in haystack and event_num is not None:
            return f"/dev/input/event{event_num}"

    return None
