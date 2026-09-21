"""Run under dbus-run-session with MSI_EC_TEST_BUS=1; never uses live sysfs."""

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fan_backend import BackendError, FanBackend

DAEMON = Path(__file__).resolve().parents[1] / "msi-ec-daemon/build/msi-ec-daemon"


@unittest.skipUnless(os.environ.get("MSI_EC_TEST_BUS") == "1" and DAEMON.exists(), "requires isolated D-Bus test session and built daemon")
class DBusIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.ec = Path(self.directory.name)
        for name, value in {
            "fw_version": "15K1IMS1.113", "fan_mode": "auto", "shift_mode": "comfort",
            "available_fan_modes": "auto\nsilent\nadvanced\n",
            "available_shift_modes": "eco\ncomfort\nturbo\n", "cooler_boost": "off",
        }.items():
            (self.ec / name).write_text(value)
        arguments = [str(DAEMON), "--session", "--sysfs", str(self.ec)]
        if getattr(self, "curve_fixture", False):
            self.ec_io = self.ec / "raw-ec"
            raw = bytearray(256)
            raw[0xa0:0xac] = b"15K1IMS1.113"
            raw[0x6a:0x70] = bytes([51,58,65,73,78,83])
            raw[0x72:0x78] = bytes([20,40,55,70,90,100])
            raw[0x78] = 78
            self.ec_io.write_bytes(raw)
            arguments += ["--ec-io", str(self.ec_io)]
        self.daemon = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self.addAsyncCleanup(self.stop_daemon)
        ready = await asyncio.wait_for(self.daemon.stdout.readline(), 3)
        if b"ready" not in ready:
            self.fail((await self.daemon.stderr.read()).decode())
        self.backend = FanBackend(session=True)

    async def stop_daemon(self):
        if self.daemon.returncode is None:
            self.daemon.terminate()
            await asyncio.wait_for(self.daemon.communicate(), 3)

    async def test_real_protocol_reads_writes_and_capabilities(self):
        status = await self.backend.probe()
        self.assertTrue(status.connected, status.reason)
        self.assertEqual(status.firmware, "15K1IMS1.113")
        self.assertEqual(status.fan_modes, ("auto", "silent", "advanced"))
        self.assertFalse(status.curve_read)
        self.assertIn("ec_sys", status.reason)
        await self.backend.apply_controls({"fan_mode": "silent", "shift_mode": "eco", "cooler_boost": "off"})
        self.assertEqual((self.ec / "fan_mode").read_text(), "silent")
        self.assertEqual((self.ec / "shift_mode").read_text(), "eco")
        # Shift mode must use its own attribute, never the fan-mode register.
        self.assertEqual(await self.backend._call("ReadShiftMode", reply="s"), "eco")
        await self.backend.apply_controls({"fan_mode": "auto"})

    async def test_unsupported_curves_and_arbitrary_paths_are_rejected(self):
        for action in (self.backend.read_curve(), self.backend.set_preset("performance"), self.backend.apply_controls({"../outside": "on"})):
            with self.assertRaises(BackendError):
                await action
        self.assertEqual((self.ec / "fan_mode").read_text(), "auto")
        with self.assertRaises(BackendError):
            await self.backend._call("ReadControl", "s", "../outside", reply="s")

    @unittest.skipIf(os.geteuid() == 0, "permission simulation requires non-root test user")
    async def test_failed_write_restores_earlier_controls(self):
        (self.ec / "fan_mode").chmod(0o444)
        with self.assertRaisesRegex(BackendError, "previous values restored"):
            await self.backend.apply_controls({"cooler_boost": "on", "fan_mode": "silent"})
        self.assertEqual((self.ec / "cooler_boost").read_text(), "off")
        self.assertEqual((self.ec / "fan_mode").read_text(), "auto")

    async def test_disconnect_and_reconnect(self):
        self.assertTrue((await self.backend.probe()).connected)
        await self.stop_daemon()
        self.assertFalse((await self.backend.probe()).connected)


@unittest.skipUnless(os.environ.get("MSI_EC_TEST_BUS") == "1" and DAEMON.exists(), "requires isolated D-Bus test session and built daemon")
class CurveDBusTests(unittest.IsolatedAsyncioTestCase):
    curve_fixture = True
    asyncSetUp = DBusIntegrationTests.asyncSetUp
    stop_daemon = DBusIntegrationTests.stop_daemon

    async def test_cyborg_curve_read_write_and_fixed_registers(self):
        status = await self.backend.probe()
        self.assertTrue(status.curve_read, status.reason)
        self.assertTrue(status.curve_write, status.reason)
        curve = await self.backend.read_curve()
        self.assertEqual(curve[0], [51,20])
        before = self.ec_io.read_bytes()
        for preset in ("performance", "silent"):
            points = await self.backend.set_preset(preset)
            self.assertEqual([p[0] for p in points], [51,58,65,73,78,83])
            self.assertEqual(points[-1][1], 100)
            after = self.ec_io.read_bytes()
            self.assertEqual(before[:0x72], after[:0x72])
            self.assertEqual(before[0x78:], after[0x78:])
            self.assertEqual((self.ec / "fan_mode").read_text(), "advanced")

    async def test_temperature_changes_and_mismatched_ec_are_rejected(self):
        points = await self.backend.read_curve()
        points[0][0] = 50
        args = [str(len(points))] + [str(v) for p in points for v in p]
        before = self.ec_io.read_bytes()
        with self.assertRaisesRegex(BackendError, "fixed temperature"):
            await self.backend._call("WriteCurve", "a(yy)", *args, reply="b")
        self.assertEqual(self.ec_io.read_bytes(), before)
        mismatched = bytearray(before)
        mismatched[0xa0] = ord('X')
        self.ec_io.write_bytes(mismatched)
        self.assertFalse((await self.backend.probe()).curve_write)
        with self.assertRaises(BackendError):
            await self.backend.set_preset("performance")

    @unittest.skipIf(os.geteuid() == 0, "permission simulation requires non-root test user")
    async def test_read_only_curve_is_viewable_but_not_writable(self):
        self.ec_io.chmod(0o444)
        state = await self.backend.probe()
        self.assertTrue(state.curve_read)
        self.assertFalse(state.curve_write)
        before = self.ec_io.read_bytes()
        with self.assertRaisesRegex(BackendError, "read-only"):
            await self.backend.set_preset("performance")
        self.assertEqual(self.ec_io.read_bytes(), before)
