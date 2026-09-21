import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fan_backend import BackendError, FanBackend


class FanBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_and_curve_validation(self):
        backend = FanBackend()
        with patch.object(backend, "_call", new=AsyncMock(return_value={"protocol_version": "0"})):
            status = await backend.probe()
            self.assertFalse(status.connected)
            self.assertIn("Incompatible", status.reason)
        for bad in (None, [], [[40, 200], [80, 100]], [[40, 80], [80, 20]], [[40, 20], [40, 100]]):
            with self.subTest(points=bad), patch.object(backend, "_call", new=AsyncMock(return_value=bad)):
                with self.assertRaises(BackendError):
                    await backend.read_curve()

    async def test_readback_and_rejected_writes(self):
        backend = FanBackend()
        for replies in ([False], [True, "comfort"]):
            with self.subTest(replies=replies), patch.object(backend, "_call", new=AsyncMock(side_effect=replies)):
                with self.assertRaises(BackendError):
                    await backend.apply_controls({"shift_mode": "turbo"})
        with patch.object(backend, "_call", new=AsyncMock(side_effect=[True, [[40, 20], [80, 100]], "auto"])):
            with self.assertRaisesRegex(BackendError, "advanced mode"):
                await backend.set_preset("performance")

    async def test_subprocess_arguments_json_and_missing_service(self):
        process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(json.dumps({"type": "s", "data": ["auto"]}).encode(), b"")))
        with patch("fan_backend.shutil.which", return_value="/usr/bin/busctl"), patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as launch:
            backend = FanBackend()
            self.assertEqual(await backend._call("ReadFanMode", reply="s"), "auto")
            self.assertIn("--system", launch.call_args.args)
            self.assertIn("--auto-start=no", launch.call_args.args)
            process.communicate.return_value = (b'{"type":"b","data":[true]}', b"")
            with self.assertRaisesRegex(BackendError, "Invalid response"):
                await backend._call("ReadFanMode", reply="s")
            process.returncode = 1
            process.communicate.return_value = (b"", b"ServiceUnknown: name not provided")
            self.assertFalse((await backend.probe()).connected)

    async def test_timeout_cleans_up_child_and_reports_uncertain_outcome(self):
        stopped = asyncio.Event()
        async def communicate():
            await stopped.wait()
            return b"", b""
        process = SimpleNamespace(returncode=None, communicate=communicate, kill=Mock(side_effect=stopped.set))
        with patch("fan_backend.shutil.which", return_value="busctl"), patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            with self.assertRaisesRegex(BackendError, "whether the operation completed"):
                await FanBackend(timeout=0.01)._call("WriteFanMode", "s", "auto", reply="b")
            process.kill.assert_called_once()
