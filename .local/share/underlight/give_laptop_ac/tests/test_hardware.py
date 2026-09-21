from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hardware import WriteResult, apply_verified, write_verified


class HardwareTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.shift = self.root / "shift_mode"
        self.fan = self.root / "fan_mode"
        self.shift.write_text("comfort")
        self.fan.write_text("auto")

    def test_write_requires_readback_and_never_creates_attributes(self):
        self.assertTrue(write_verified(self.shift, "eco"))
        self.assertEqual(self.shift.read_text(), "eco")
        missing = self.root / "missing"
        self.assertFalse(write_verified(missing, "on"))
        self.assertFalse(missing.exists())
        with patch.object(Path, "read_text", side_effect=["eco", "comfort"]):
            result = write_verified(self.shift, "turbo")
        self.assertFalse(result)
        self.assertIn("hardware reports comfort", result.message)

    def test_permission_failure_is_reported(self):
        with patch("hardware.os.open", side_effect=PermissionError):
            result = write_verified(self.shift, "turbo")
        self.assertFalse(result)
        self.assertIn("permission denied", result.message)

    def test_partial_preset_is_rolled_back(self):
        def driver(path, value):
            if path == self.fan and value == "advanced":
                return WriteResult(False, "fan mode rejected")
            return write_verified(path, value)

        with patch("hardware.write_verified", side_effect=driver):
            result = apply_verified({self.shift: "turbo", self.fan: "advanced"})
        self.assertFalse(result)
        self.assertIn("Previous settings restored", result.message)
        self.assertEqual(self.shift.read_text(), "comfort")
        self.assertEqual(self.fan.read_text(), "auto")

    def test_final_state_detects_coupled_controls(self):
        def driver(path, value):
            result = write_verified(path, value)
            if path == self.fan and value == "advanced":
                self.shift.write_text("eco")
            return result

        with patch("hardware.write_verified", side_effect=driver):
            result = apply_verified({self.shift: "turbo", self.fan: "advanced"})
        self.assertFalse(result)
        self.assertIn("hardware reports eco", result.message)
        self.assertEqual(self.shift.read_text(), "comfort")

    def test_failed_rollback_is_not_reported_as_success(self):
        def driver(path, value):
            if path == self.fan or value == "comfort":
                return WriteResult(False, "driver refused write")
            return write_verified(path, value)

        with patch("hardware.write_verified", side_effect=driver):
            result = apply_verified({self.shift: "turbo", self.fan: "advanced"})
        self.assertFalse(result)
        self.assertIn("Could not restore", result.message)
        self.assertNotIn("Previous settings restored", result.message)

    def test_missing_control_fails_before_any_changes(self):
        result = apply_verified({self.shift: "turbo", self.root / "missing": "on"})
        self.assertFalse(result)
        self.assertEqual(self.shift.read_text(), "comfort")


if __name__ == "__main__":
    unittest.main()
