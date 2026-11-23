"""Deterministic unit tests for hal.device_profile's auto-detection.

Monkeypatches the two low-level probes (_read_device_tree_model and
device_discovery.find_input_device) so these tests never touch the real
/proc on the machine running them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hal import device_profile


class DetectProfileTests(unittest.TestCase):
    def setUp(self):
        self._orig_read_model = device_profile._read_device_tree_model
        self._orig_find_device = device_profile.device_discovery.find_input_device
        self._orig_env = os.environ.pop("ESPFLASHER_DEV_PROFILE", None)

    def tearDown(self):
        device_profile._read_device_tree_model = self._orig_read_model
        device_profile.device_discovery.find_input_device = self._orig_find_device
        if self._orig_env is not None:
            os.environ["ESPFLASHER_DEV_PROFILE"] = self._orig_env

    def test_no_device_tree_model_falls_back_to_cardputerzero(self):
        device_profile._read_device_tree_model = lambda: None
        device_profile.device_discovery.find_input_device = lambda name: None
        self.assertIs(device_profile.get_active_profile(), device_profile.CARDPUTERZERO)

    def test_compute_module_plus_goodix_selects_tdisplay_cm0(self):
        device_profile._read_device_tree_model = lambda: "Raspberry Pi Compute Module Zero Rev 1.0"
        device_profile.device_discovery.find_input_device = lambda name: (
            "/dev/input/event4" if name == "goodix" else None
        )
        self.assertIs(device_profile.get_active_profile(), device_profile.TDISPLAY_CM0)

    def test_compute_module_without_goodix_falls_back_to_cardputerzero(self):
        # Device tree says Compute Module, but no Goodix touch found — not
        # conclusive enough, stay on the safe default.
        device_profile._read_device_tree_model = lambda: "Raspberry Pi Compute Module Zero Rev 1.0"
        device_profile.device_discovery.find_input_device = lambda name: None
        self.assertIs(device_profile.get_active_profile(), device_profile.CARDPUTERZERO)

    def test_unrelated_model_falls_back_to_cardputerzero(self):
        device_profile._read_device_tree_model = lambda: "Raspberry Pi Zero 2 W Rev 1.0"
        device_profile.device_discovery.find_input_device = lambda name: None
        self.assertIs(device_profile.get_active_profile(), device_profile.CARDPUTERZERO)

    def test_never_raises_when_proc_missing(self):
        # _read_device_tree_model itself already swallows OSError; this
        # just double-checks get_active_profile() never propagates one.
        try:
            device_profile.get_active_profile()
        except Exception as e:  # pragma: no cover - failure path
            self.fail(f"get_active_profile() raised {e!r}")

    def test_env_override_wins_over_detection(self):
        device_profile._read_device_tree_model = lambda: "Raspberry Pi Compute Module Zero Rev 1.0"
        device_profile.device_discovery.find_input_device = lambda name: "/dev/input/event4"
        os.environ["ESPFLASHER_DEV_PROFILE"] = "cardputerzero"
        try:
            self.assertIs(device_profile.get_active_profile(), device_profile.CARDPUTERZERO)
        finally:
            del os.environ["ESPFLASHER_DEV_PROFILE"]


if __name__ == "__main__":
    unittest.main()
