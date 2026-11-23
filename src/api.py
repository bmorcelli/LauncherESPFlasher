import requests
import cache
import state
from config import API_BASE

TIMEOUT      = 10
PROBE_TIMEOUT = 3   # fast connectivity check

CDN_COVER    = "https://m5burner-cdn.m5stack.com/cover/"
CDN_FIRMWARE = "https://m5burner-cdn.m5stack.com/firmware/"


def is_online(timeout=PROBE_TIMEOUT):
    """Return True if the API endpoint is reachable. Works over any network interface."""
    try:
        requests.head(API_BASE, timeout=timeout)
        return True
    except Exception:
        return False


def sync_offline_state():
    """Probe connectivity and update state.offline_mode.
    Auto-transitions ONLINE→OFFLINE on connection failure.
    OFFLINE→ONLINE only via manual toggle (set state.checking_online = True first).
    Returns (is_offline, show_warning)."""
    # When already offline and not doing a manual online-check: skip the probe entirely.
    # The 1.5s timeout would waste time and state can't change without a manual toggle.
    if state.offline_mode and not state.checking_online:
        return (True, False)

    state.checking_online = False   # consume the flag

    online = is_online(timeout=1.5)

    if online:
        # Connection confirmed — clear offline state and allow re-warning on next drop
        state.offline_mode    = False
        state.offline_notified = False
        return (False, False)

    # Probe failed — transition to offline if not already there
    if not state.offline_mode:
        state.offline_mode = True
        if not state.offline_notified:
            state.offline_notified = True
            return (True, True)    # first auto-detection: show warning

    return (True, False)


def _fetch_all_firmware():
    """Raw fetch of the full firmware list from the network (no cache)."""
    resp = requests.get(f"{API_BASE}/GiveMeTheList", timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def refresh_all():
    """Fetch devices and firmware from network and update the cache.
    Called on boot (via prefetch thread) and on Ctrl+R during use."""
    # Fetch devices_full
    try:
        resp = requests.get(f"{API_BASE}/devices", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data and isinstance(data[0], dict) and "category" in data[0]:
            devices_full = [
                {
                    "name": item["category"],
                    "firmware_count": item.get("firmware_count", 0),
                    "sources": [item["source"]] if item.get("source") else ["m5stack"],
                }
                for item in data
                if item.get("category")
            ]
            if devices_full:
                cache.save_devices_full(devices_full)
    except Exception:
        pass

    # Fetch all firmware (also writes per-category shards and devices.json)
    try:
        data = _fetch_all_firmware()
        cache.save_all_firmware(data)
    except Exception:
        pass


def get_devices_full():
    """
    Returns a list of rich device dicts: [{name, firmware_count, sources}, ...]
    Serves from cache (populated by boot refresh); falls back to network on cache miss.
    When offline, derives list from the downloaded-firmware registry.
    """
    if state.offline_mode:
        cats = cache.get_offline_categories()
        return [{"name": c, "firmware_count": 0, "sources": ["custom"]} for c in cats]

    cached = cache.load_devices_full()
    if cached is not None:
        return cached

    # Cache miss (boot refresh failed) — try network directly
    try:
        resp = requests.get(f"{API_BASE}/devices", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data and isinstance(data[0], dict) and "category" in data[0]:
            devices_full = [
                {
                    "name": item["category"],
                    "firmware_count": item.get("firmware_count", 0),
                    "sources": [item["source"]] if item.get("source") else ["m5stack"],
                }
                for item in data
                if item.get("category")
            ]
            if devices_full:
                cache.save_devices_full(devices_full)
                return devices_full
    except Exception:
        pass

    # Fallback: convert simple string list to minimal rich dicts
    try:
        simple = get_devices()
        return [{"name": n, "firmware_count": 0, "sources": ["m5stack"]} for n in simple]
    except Exception:
        pass

    raise RuntimeError("Could not fetch device list and no cache available.")


def get_devices():
    """
    Returns a sorted list of device category strings.
    Serves from cache; fetches network on cache miss; stale cache as last resort.
    """
    if state.offline_mode:
        return cache.get_offline_categories()

    cached = cache.load_devices()
    if cached is not None:
        return cached

    try:
        resp = requests.get(f"{API_BASE}/devices", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            if isinstance(data[0], str):
                result = sorted(data)
                cache.save_devices(result)
                return result
            if isinstance(data[0], dict):
                key = next((k for k in ("name", "category", "id") if k in data[0]), None)
                if key:
                    result = sorted(item[key] for item in data if item.get(key))
                    cache.save_devices(result)
                    return result
    except Exception:
        pass

    # Fallback: derive categories from full firmware list
    try:
        firmwares = _fetch_all_firmware()
        categories = cache.save_all_firmware(firmwares)
        return categories
    except Exception:
        pass

    raise RuntimeError("Could not fetch device list and no cache available.")


def get_firmware_list(category=None):
    """
    Returns the firmware list for a given category, sorted by downloads desc.
    Serves from cache (populated by boot refresh); fetches network on cache miss.
    When offline, returns only downloaded firmware for that category.
    """
    if state.offline_mode:
        return cache.get_offline_firmware_list(category)

    if category:
        cached = cache.load_firmware(category)
        if cached is not None:
            return cached

    # Cache miss — try network directly
    try:
        data = _fetch_all_firmware()
        cache.save_all_firmware(data)
        if category:
            data = [f for f in data if f.get("category") == category]
        return sorted(data, key=lambda x: x.get("download", 0), reverse=True)
    except Exception:
        pass

    raise RuntimeError("Could not fetch firmware list and no cache available.")


def firmware_file_url(filename):
    """Returns the download URL for a firmware .bin file."""
    if not filename:
        return ""
    if filename.startswith(("http://", "https://")):
        return filename
    return f"{CDN_FIRMWARE}{filename}"


def cover_image_url(filename):
    """Returns the download URL for a cover image."""
    if not filename:
        return ""
    if filename.startswith(("http://", "https://", "/")):
        return filename
    return f"{CDN_COVER}{filename}"
