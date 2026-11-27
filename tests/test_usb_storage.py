"""Unit tests for usb_storage (no real block devices or mounts touched)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import usb_storage

_LSBLK = [
    {"name": "mmcblk0", "path": "/dev/mmcblk0", "type": "disk", "tran": None,
     "fstype": None, "label": None, "mountpoint": None, "children": [
         {"name": "mmcblk0p1", "path": "/dev/mmcblk0p1", "type": "part", "tran": None,
          "fstype": "vfat", "label": "bootfs", "mountpoint": "/boot/firmware"},
         {"name": "mmcblk0p2", "path": "/dev/mmcblk0p2", "type": "part", "tran": None,
          "fstype": "ext4", "label": "rootfs", "mountpoint": "/"},
     ]},
    {"name": "sda", "path": "/dev/sda", "type": "disk", "tran": "usb",
     "fstype": None, "label": None, "mountpoint": None, "children": [
         {"name": "sda1", "path": "/dev/sda1", "type": "part", "tran": None,
          "fstype": "vfat", "label": "PENDRIVE", "mountpoint": "/media/pi/PENDRIVE"},
         {"name": "sda2", "path": "/dev/sda2", "type": "part", "tran": None,
          "fstype": "swap", "label": None, "mountpoint": "[SWAP]"},
     ]},
    # SD card in a USB reader, no partition table, not mounted
    {"name": "sdb", "path": "/dev/sdb", "type": "disk", "tran": "usb",
     "fstype": "exfat", "label": "SDCARD", "mountpoint": None},
]


class FindUsbPartitions(unittest.TestCase):
    def test_only_usb_filesystems(self):
        parts = usb_storage.find_usb_partitions(_LSBLK)
        self.assertEqual([p["path"] for p in parts], ["/dev/sda1", "/dev/sdb"])
        self.assertEqual(parts[0]["mountpoint"], "/media/pi/PENDRIVE")
        self.assertIsNone(parts[1]["mountpoint"])

    def test_empty(self):
        self.assertEqual(usb_storage.find_usb_partitions([]), [])


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp  = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.mnt1 = os.path.join(self.tmp.name, "PENDRIVE")
        self.mnt2 = os.path.join(self.tmp.name, "SDCARD")
        for d in (self.home, self.mnt1, self.mnt2):
            os.makedirs(d)

    def tearDown(self):
        self.tmp.cleanup()

    def _parts(self):
        return [
            {"path": "/dev/sda1", "name": "sda1", "label": "PENDRIVE",
             "fstype": "vfat", "mountpoint": self.mnt1},
            {"path": "/dev/sdb", "name": "sdb", "label": "SDCARD",
             "fstype": "exfat", "mountpoint": None},
        ]

    def test_links_mounted_and_mounts_unmounted(self):
        with mock.patch.object(usb_storage, "find_usb_partitions", return_value=self._parts()), \
             mock.patch.object(usb_storage, "_mount", return_value=self.mnt2) as m:
            links = usb_storage.prepare(self.home)
        m.assert_called_once()
        self.assertEqual(links, [os.path.join(self.home, "USB"), os.path.join(self.home, "USB2")])
        self.assertEqual(os.readlink(links[0]), self.mnt1)
        self.assertEqual(os.readlink(links[1]), self.mnt2)

    def test_reuses_link_and_never_clobbers_real_folder(self):
        os.makedirs(os.path.join(self.home, "USB"))          # user's own folder
        os.symlink("/nonexistent", os.path.join(self.home, "USB2"))  # stale link
        with mock.patch.object(usb_storage, "find_usb_partitions", return_value=self._parts()[:1]):
            first  = usb_storage.prepare(self.home)
            second = usb_storage.prepare(self.home)
        self.assertEqual(first, [os.path.join(self.home, "USB2")])
        self.assertEqual(first, second)
        self.assertTrue(os.path.isdir(os.path.join(self.home, "USB")))
        self.assertFalse(os.path.islink(os.path.join(self.home, "USB")))

    def test_mount_failure_skips_device(self):
        with mock.patch.object(usb_storage, "find_usb_partitions", return_value=self._parts()[1:]), \
             mock.patch.object(usb_storage, "_mount", return_value=None):
            self.assertEqual(usb_storage.prepare(self.home), [])


if __name__ == "__main__":
    unittest.main()
