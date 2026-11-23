"""Deterministic unit tests for hal.device_discovery.find_input_device.

Uses a synthetic /proc/bus/input/devices fixture (never touches the real
/proc on the machine running the tests).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hal.device_discovery import find_input_device

_FIXTURE = """\
I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="vc4-hdmi"
P: Phys=vc4-hdmi
S: Sysfs=/devices/platform/soc/fe902000.hdmi/input/input0
U: Uniq=
H: Handlers=event0
B: PROP=0
B: EV=3
B: SW=140

I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="ti,tca8418"
P: Phys=i2c-1-0034
S: Sysfs=/devices/platform/soc/fe804000.i2c/i2c-1/1-0034/input/input1
U: Uniq=
H: Handlers=sysrq kbd event1
B: PROP=0
B: EV=120013
B: KEY=1000000000007 ff9f207ac14057ff febeffdfffefffff fffffffffffffffe

I: Bus=0018 Vendor=0000 Product=0000 Version=0000
N: Name="Goodix Berlin Capacitive TouchScreen"
P: Phys=i2c-10-0037
S: Sysfs=/devices/platform/soc/fe804000.i2c/i2c-10/10-0037/input/input4
U: Uniq=
H: Handlers=event4 mouse1
B: PROP=0
B: EV=b
B: KEY=400 0 0 0 0 0 0 0 0 0 0
B: ABS=e61800000000003

I: Bus=0003 Vendor=046d Product=c52b Version=0111
N: Name="Logitech USB Receiver"
P: Phys=usb-3f980000.usb-1.3/input0
S: Sysfs=/devices/platform/soc/3f980000.usb/usb1/1-1/1-1.3/1-1.3:1.0/0003:046D:C52B.0001/input/input5
U: Uniq=
H: Handlers=event5
B: PROP=0
B: EV=17
"""


class FindInputDeviceTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".devices")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_FIXTURE)

    def tearDown(self):
        os.remove(self.path)

    def test_finds_keyboard_by_substring(self):
        result = find_input_device("tca8418", devices_path=self.path)
        self.assertEqual(result, "/dev/input/event1")

    def test_finds_touch_by_substring(self):
        result = find_input_device("goodix", devices_path=self.path)
        self.assertEqual(result, "/dev/input/event4")

    def test_case_insensitive_by_default(self):
        result = find_input_device("GOODIX", devices_path=self.path)
        self.assertEqual(result, "/dev/input/event4")

    def test_case_sensitive_when_requested(self):
        result = find_input_device("GOODIX", case_insensitive=False, devices_path=self.path)
        self.assertIsNone(result)
        result = find_input_device("Goodix", case_insensitive=False, devices_path=self.path)
        self.assertEqual(result, "/dev/input/event4")

    def test_missing_substring_returns_none(self):
        self.assertIsNone(find_input_device("nonexistent-device", devices_path=self.path))

    def test_missing_file_returns_none_not_raises(self):
        result = find_input_device("tca8418", devices_path="/nonexistent/path/devices")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
