import glob
import os
import re
import subprocess
import sys

import requests

_ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-Za-z]")
_PCT_RE  = re.compile(r"(\d+)(?:\.\d+)?\s*%")
_CHIP_RE = re.compile(r"(?:Chip is|Detecting chip type\.+\s*)ESP32(?:-([A-Za-z0-9]+))?", re.IGNORECASE)

from config import ASSETS_DIR

_IS_WINDOWS = sys.platform == "win32"
_ESPTOOL = [sys.executable, "-m", "esptool"]
_BAUD    = "460800"

ESP_ENV_NAME = {
    "32": "esp32", "s3": "esp32s3", "s2": "esp32s2", "c3": "esp32c3",
    "c5": "esp32c5", "c6": "esp32c6", "h2": "esp32h2", "p4": "esp32p4",
}
BOOTLOADER_OFFSET = {
    "32": 0x1000, "s2": 0x1000, "s3": 0x0, "c3": 0x0,
    "c6": 0x0,   "h2": 0x0,   "c5": 0x2000, "p4": 0x2000,
}


def is_merged_binary(path):
    """Return True if path is a full/merged binary (has partition table magic at 0x8000)."""
    try:
        with open(path, "rb") as f:
            file_size = f.seek(0, 2)
            if file_size < 0x8002:
                return False
            f.seek(0x8000)
            magic = f.read(2)
        return magic == b'\xaa\x50'
    except OSError:
        return False


def detect_chip_type(port, extra_flags=None):
    """Run chip_id on port and return the esp variant string ('32', 's3', etc.), or None."""
    extra_flags = extra_flags or []
    try:
        r = subprocess.run(
            _ESPTOOL + ["--port", port] + extra_flags + ["chip_id"],
            capture_output=True, timeout=10,
        )
        output = (r.stdout + r.stderr).decode("utf-8", errors="replace")
        m = _CHIP_RE.search(output)
        if not m:
            return None
        suffix = (m.group(1) or "").lower()
        return suffix if suffix else "32"
    except Exception:
        return None


def _list_serial_ports():
    """Return candidate serial port paths for the current OS."""
    if _IS_WINDOWS:
        import winreg
        ports = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            i = 0
            while True:
                try:
                    _, port, _ = winreg.EnumValue(key, i)
                    ports.append(port)
                    i += 1
                except OSError:
                    break
        except OSError:
            pass
        return sorted(ports)
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def detect_port():
    """
    Return (port, extra_flags) for the first port that responds to esptool, or (None, []).
    Tries two strategies per port:
      1. Default — works for ttyUSB chips with RTS/DTR auto-reset
      2. --before no_reset --no-stub — required for ESP32-S3 native USB/JTAG (ttyACM)
    The returned extra_flags must be passed to flash() so the same connection mode is used.
    """
    candidates = _list_serial_ports()
    strategies = [
        [],
        ["--before", "no_reset", "--no-stub"],
    ]
    for port in candidates:
        for extra in strategies:
            try:
                r = subprocess.run(
                    _ESPTOOL + ["--port", port] + extra + ["chip_id"],
                    capture_output=True,
                    timeout=10,
                )
                if r.returncode == 0:
                    return port, extra
            except Exception:
                continue
    return None, []


def is_app_format(version):
    """Return True when the version requires multi-part (bootloader+parts+app) flash."""
    install = version.get("install") if version else None
    if isinstance(install, dict):
        return install.get("format") == "app"
    return False


def resolve_parts(firmware, app_bin_path):
    """
    Return a list of (abs_path, hex_address_str) tuples for multi-part 'app' format.
    app_bin_path is the already-downloaded application .bin (goes to 0x10000).
    esp comes from firmware["esp"] ("32", "s3", "c3", etc.) — top-level API field.
    """
    esp       = firmware.get("esp", "32")
    env       = ESP_ENV_NAME.get(esp, "esp32")
    bl_offset = BOOTLOADER_OFFSET.get(esp, 0x1000)

    bl_path  = os.path.join(ASSETS_DIR, env, "bootloader.bin")
    pt_path  = os.path.join(ASSETS_DIR, env, "partitions.bin")

    return [
        (bl_path,      hex(bl_offset)),
        (pt_path,      "0x8000"),
        (app_bin_path, "0x10000"),
    ]


_PART_ENTRY_SIZE     = 32
_PART_MAGIC          = b'\xaa\x50'
_PART_APP_MIN_OFFSET = 0xFFFF


def is_split_format(version):
    """Return True when the version ships separate bootloader+partitions+app files
    that must be merged into a single flashable image at download time."""
    install = version.get("install") if version else None
    if isinstance(install, dict):
        return install.get("format") == "split"
    return False


def resolve_app_offset(partitions_path):
    """Parse an ESP-IDF partition table binary and return the address of the first
    partition located after 0xFFFF (the app partition), falling back to 0x10000."""
    try:
        with open(partitions_path, "rb") as f:
            data = f.read()
    except OSError:
        return 0x10000

    offsets = []
    for i in range(0, len(data) - _PART_ENTRY_SIZE + 1, _PART_ENTRY_SIZE):
        entry = data[i:i + _PART_ENTRY_SIZE]
        if entry[:2] != _PART_MAGIC:
            continue
        offset = int.from_bytes(entry[4:8], "little")
        if offset > _PART_APP_MIN_OFFSET:
            offsets.append(offset)
    return min(offsets) if offsets else 0x10000


def merge_split_binary(esp, bootloader_path, partitions_path, app_path, out_path):
    """Merge bootloader + partition table + app image into a single binary flashed
    at 0x0, via `esptool merge-bin`."""
    env        = ESP_ENV_NAME.get(esp, "esp32")
    bl_offset  = BOOTLOADER_OFFSET.get(esp, 0x1000)
    app_offset = resolve_app_offset(partitions_path)

    cmd = _ESPTOOL + [
        "--chip", env, "merge-bin",
        "-o", out_path,
        hex(bl_offset), bootloader_path,
        "0x8000", partitions_path,
        hex(app_offset), app_path,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(msg[-200:] if msg else "merge-bin failed")


def download(url, dest_path, progress_cb=None):
    """Stream url to dest_path; calls progress_cb(0-100) as bytes arrive."""
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    done  = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=16384):
            if chunk:
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(99, int(done * 100 / total)))
    if progress_cb:
        progress_cb(100)


def flash(port, parts, progress_cb=None, extra_flags=None):
    """
    Flash one or more (path, address) pairs to the ESP32 on port using a single
    write_flash call so the connection is established only once.
    extra_flags: connection flags from detect_port() (e.g. --before no_reset --no-stub).
    When --no-stub is present, --baud is omitted (stub required for baud negotiation).
    progress_cb(0-100) tracks overall progress across all parts.
    """
    extra_flags = extra_flags or []
    no_stub     = "--no-stub" in extra_flags
    baud_args   = [] if no_stub else ["--baud", _BAUD]

    # Build a single write_flash command with all addr-file pairs
    addr_file_args = []
    for bin_path, addr in parts:
        addr_file_args += [addr, bin_path]

    cmd = (
        _ESPTOOL
        + ["--port", port]
        + extra_flags
        + baud_args
        + ["--after", "hard_reset"]
        + ["write_flash", "--flash_mode", "dio"]
        + addr_file_args
    )

    n       = len(parts)
    segment = 0

    env = {**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"}

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )

    buf = b""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch in (b"\r", b"\n"):
            line = _ANSI_RE.sub(b"", buf).decode("utf-8", errors="replace").strip()
            buf  = b""
            if line.startswith("Wrote ") and segment < n - 1:
                segment += 1
            m = _PCT_RE.search(line)
            if m and progress_cb:
                pct     = int(m.group(1))
                overall = (segment * 100 + min(pct, 100)) // n
                progress_cb(overall)
        else:
            buf += ch

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"esptool exited with code {proc.returncode}")
    if progress_cb:
        progress_cb(100)
