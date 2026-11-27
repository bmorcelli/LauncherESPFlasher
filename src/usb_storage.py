"""USB mass-storage helper (pendrives, USB SD-card readers) for the file picker.

`prepare()` finds every filesystem on a USB-attached block device, mounts the
ones that aren't mounted yet (at the system default location), and exposes
each one through a symlink in the user's home folder (~/USB, ~/USB2, ...).

The picker then browses through the symlink path *without resolving it*, so
going "up" from the USB root lands in the home folder instead of /media/...
"""
import getpass
import json
import os
import re
import shutil
import subprocess

LINK_PREFIX = "USB"

# Filesystems that don't support POSIX ownership: mount them owned by the
# current user so the files are readable without root.
_NO_OWNER_FS = {"vfat", "exfat", "ntfs", "ntfs3", "msdos"}
_SKIP_FS = {"swap", "crypto_LUKS", "LVM2_member", "linux_raid_member", "iso9660"}


def _run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _lsblk():
    r = _run(["lsblk", "-J", "-o", "NAME,PATH,TYPE,TRAN,FSTYPE,LABEL,MOUNTPOINT"])
    if r is None or r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout).get("blockdevices", [])
    except ValueError:
        return []


def find_usb_partitions(blockdevices=None):
    """Return [{path, name, label, fstype, mountpoint}] for every mountable
    filesystem whose disk is attached over USB. A disk formatted without a
    partition table (common on SD cards) is returned as itself."""
    if blockdevices is None:
        blockdevices = _lsblk()
    out = []

    def walk(node, usb):
        usb = usb or node.get("tran") == "usb"
        children = node.get("children") or []
        fstype = node.get("fstype")
        if usb and fstype and fstype not in _SKIP_FS:
            out.append({
                "path":       node.get("path") or "/dev/" + node.get("name", ""),
                "name":       node.get("name", ""),
                "label":      node.get("label"),
                "fstype":     fstype,
                "mountpoint": node.get("mountpoint"),
            })
        for c in children:
            walk(c, usb)

    for dev in blockdevices:
        walk(dev, False)
    return out


def _mounted_at(dev_path):
    for p in find_usb_partitions():
        if p["path"] == dev_path:
            return p["mountpoint"]
    return None


def _safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", text or "").strip("._") or "usb"


def _mount(part):
    """Mount a partition at the system default location. Returns the
    mountpoint, or None on failure."""
    dev = part["path"]

    # 1) udisks: same as the desktop automounter (/media/<user>/<label>).
    if shutil.which("udisksctl"):
        r = _run(["udisksctl", "mount", "--no-user-interaction", "-b", dev])
        if r is not None and r.returncode == 0:
            mp = _mounted_at(dev)
            if mp:
                return mp

    # 2) plain mount at /media/<user>/<label>; needs root (or passwordless sudo).
    user   = getpass.getuser()
    target = os.path.join("/media", user, _safe_name(part["label"] or part["name"]))
    opts   = []
    if part["fstype"] in _NO_OWNER_FS:
        opts = ["-o", "uid=%d,gid=%d,umask=022" % (os.getuid(), os.getgid())]
    prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
    if prefix and not shutil.which("sudo"):
        return None
    r = _run(prefix + ["mkdir", "-p", target])
    if r is None or r.returncode != 0:
        return None
    r = _run(prefix + ["mount"] + opts + [dev, target])
    if r is None or r.returncode != 0:
        return None
    return target


def _link_names(home):
    """Yields ~/USB, ~/USB2, ~/USB3, ..."""
    yield os.path.join(home, LINK_PREFIX)
    n = 2
    while True:
        yield os.path.join(home, "%s%d" % (LINK_PREFIX, n))
        n += 1


def _cleanup_stale_links(home):
    """Remove our own ~/USB* symlinks whose target no longer exists. Never
    touches real files/folders."""
    try:
        entries = os.listdir(home)
    except OSError:
        return
    for e in entries:
        if not re.fullmatch(LINK_PREFIX + r"\d*", e):
            continue
        p = os.path.join(home, e)
        if os.path.islink(p) and not os.path.exists(p):
            try:
                os.unlink(p)
            except OSError:
                pass


def _link(mountpoint, home):
    """Point the first free (or already matching) ~/USB* symlink at
    mountpoint. Returns the symlink path, or None."""
    for link in _link_names(home):
        if os.path.islink(link):
            if os.path.realpath(link) == os.path.realpath(mountpoint):
                return link
            continue  # belongs to another mounted device
        if os.path.lexists(link):
            continue  # real file/folder named USB — leave it alone
        try:
            os.symlink(mountpoint, link)
            return link
        except OSError:
            return None


def prepare(home=None):
    """Detect, mount and link every USB filesystem. Returns the list of
    symlink paths (in home), first device first; empty if none."""
    home = home or os.path.expanduser("~")
    _cleanup_stale_links(home)
    links = []
    for part in find_usb_partitions():
        mp = part["mountpoint"]
        if mp in ("[SWAP]",):
            continue
        if not mp:
            mp = _mount(part)
        if not mp or not os.path.isdir(mp):
            continue
        link = _link(mp, home)
        if link:
            links.append(link)
    return links
