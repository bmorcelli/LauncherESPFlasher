import json
import os
import threading

CACHE_DIR     = os.environ.get("ESPFLASHER_CACHE_DIR", "/var/tmp/launcherespflasher")
DOWNLOADS_DIR = os.path.join(CACHE_DIR, "downloads")


def _ensure():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _path(name):
    return os.path.join(CACHE_DIR, name)


def _safe(s):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (s or "unknown"))


# --- devices ---

def save_devices(categories):
    _ensure()
    with open(_path("devices.json"), "w") as f:
        json.dump(categories, f)


def load_devices():
    try:
        with open(_path("devices.json")) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# --- firmware per category ---

def save_firmware(category, items):
    _ensure()
    with open(_path(f"{_safe(category)}.json"), "w") as f:
        json.dump(items, f)


def load_firmware(category):
    try:
        with open(_path(f"{_safe(category)}.json")) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_devices_full(devices_full):
    _ensure()
    with open(_path("devices_full.json"), "w") as f:
        json.dump(devices_full, f)


def load_devices_full():
    try:
        with open(_path("devices_full.json")) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_all_firmware(all_firmware):
    """Split a full firmware list by category and save each shard."""
    by_cat = {}
    for fw in all_firmware:
        cat = fw.get("category", "unknown")
        by_cat.setdefault(cat, []).append(fw)
    for cat, items in by_cat.items():
        save_firmware(cat, items)
    categories = sorted(by_cat.keys())
    save_devices(categories)

    return categories


# --- downloaded firmware registry ---

def _dl_key(name, version_str):
    return f"{_safe(name)}__{_safe(version_str)}"


def _fw_dir(name):
    """Return (and create) the per-firmware folder: downloads/{fid}/"""
    d = os.path.join(DOWNLOADS_DIR, _safe(name))
    os.makedirs(d, exist_ok=True)
    return d


def download_path(name, version_str):
    """Return the persistent path for a firmware binary: downloads/{fid}/{version}/firmware.bin"""
    _ensure()
    d = os.path.join(_fw_dir(name), _safe(version_str))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "firmware.bin")


def cover_path(name):
    """Return the persistent path for a firmware cover image: downloads/{fid}/cover.jpg"""
    _ensure()
    return os.path.join(_fw_dir(name), "cover.jpg")


def load_downloaded():
    """Return the downloaded-firmware registry dict (empty dict if none yet)."""
    try:
        with open(_path("downloaded.json")) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_downloaded(registry):
    _ensure()
    with open(_path("downloaded.json"), "w") as f:
        json.dump(registry, f, indent=2)


def mark_downloaded(firmware, version_obj, file_path):
    """Record a successfully downloaded firmware version in the registry."""
    registry = load_downloaded()
    name = firmware.get("name", "unknown")
    ver  = version_obj.get("version", "?")
    key  = _dl_key(name, ver)
    registry[key] = {
        "name":        name,
        "category":    firmware.get("category", ""),
        "version":     ver,
        "path":        file_path,
        "firmware":    firmware,
        "version_obj": version_obj,
    }
    _save_downloaded(registry)


def is_downloaded(name, version_str):
    """Return True if the firmware binary exists on disk and is registered."""
    key      = _dl_key(name, version_str)
    registry = load_downloaded()
    if key not in registry:
        return False
    path = registry[key].get("path", "")
    return bool(path and os.path.exists(path))


def get_download_path(name, version_str):
    """Return the local path of a downloaded binary, or '' if not present."""
    key      = _dl_key(name, version_str)
    registry = load_downloaded()
    return registry.get(key, {}).get("path", "")


def get_offline_categories():
    """Return sorted list of categories that have at least one downloaded firmware."""
    registry = load_downloaded()
    cats = set()
    for entry in registry.values():
        fw = entry.get("firmware")
        if fw:
            cat = fw.get("category", "")
            if cat:
                cats.add(cat)
    return sorted(cats)


def get_offline_firmware_list(category=None):
    """Return deduplicated firmware dicts from the downloaded registry.
    One entry per firmware name (the most recently registered version)."""
    registry = load_downloaded()
    seen = {}  # name → firmware dict
    for entry in registry.values():
        fw = entry.get("firmware")
        if not fw:
            continue
        if category and fw.get("category") != category:
            continue
        name = fw.get("name", "")
        if name not in seen:
            seen[name] = dict(fw)
    return list(seen.values())


# --- tutorial preference ---

def tutorial_dismissed():
    return os.path.exists(_path("tutorial_dismissed"))


def dismiss_tutorial():
    _ensure()
    with open(_path("tutorial_dismissed"), "w") as f:
        f.write("1")


# --- prefetch ---

def _prefetch_worker():
    try:
        import api   # lazy import avoids circular dependency
        import state
        if not api.is_online():
            state.offline_mode = True
            return
        api.refresh_all()
    except Exception:
        pass  # boot must never fail due to cache


def start_prefetch():
    """Fire-and-forget: fetch everything during boot animation."""
    t = threading.Thread(target=_prefetch_worker, daemon=True)
    t.start()
    return t
