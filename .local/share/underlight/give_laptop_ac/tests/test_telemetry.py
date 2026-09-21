from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Data
import unittest
from unittest.mock import patch

import pynvml
from telemetry import CounterRate, TelemetrySampler


class CounterRateTests(unittest.TestCase):
    def test_rates_reset_and_recover_without_inventing_zero_samples(self):
        rate = CounterRate()
        self.assertIsNone(rate.sample(100, 10))
        self.assertEqual(rate.sample(120, 12), 10)
        self.assertEqual(rate.sample(120, 14), 0)
        self.assertIsNone(rate.sample(5, 16))
        self.assertEqual(rate.sample(15, 18), 5)
        self.assertIsNone(rate.sample(None, 20))
        self.assertIsNone(rate.sample(100, 22))
        self.assertEqual(rate.sample(110, 24), 5)
        self.assertIsNone(rate.sample(115, 24))

    def test_energy_counter_wrap(self):
        rate = CounterRate()
        self.assertIsNone(rate.sample(90, 1, 100))
        self.assertEqual(rate.sample(10, 3, 100), 10)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory()))
        self.ec = {"cpu/realtime_temperature": "55", "cpu/realtime_fan_speed": "30"}
        self.net = Data(bytes_sent=8_000_000, bytes_recv=12_000_000)
        self.disk = Data(read_bytes=100_000_000, write_bytes=200_000_000)
        sources = {
            "virtual_memory": Data(percent=42),
            "sensors_battery": None,
            "cpu_freq": Data(current=2400),
            "cpu_percent": [20, 60],
            "net_io_counters": self.net,
            "disk_io_counters": self.disk,
            "sensors_temperatures": {},
        }
        for method, value in sources.items():
            self.stack.enter_context(patch(f"telemetry.psutil.{method}", return_value=value))
        self.clock = self.stack.enter_context(patch("telemetry.time.monotonic", return_value=100))

    def sampler(self, **kwargs):
        return TelemetrySampler(self.ec.get, powercap=self.root, **kwargs)

    def test_real_rates_and_missing_sensors(self):
        sampler = self.sampler()
        first = sampler.sample()
        self.assertIsNone(first.values["net_up"])
        self.assertIsNone(first.values["disk_read"])
        self.assertIsNone(first.values["cpu_load"])
        self.assertIsNone(first.values["battery"])
        self.assertIsNone(first.values["gpu_fan"])
        self.assertEqual(first.unavailable["gpu_load"], "NVIDIA NVML is not connected")
        self.clock.return_value = 102
        self.net.bytes_sent += 4_000_000
        self.net.bytes_recv += 8_000_000
        self.disk.read_bytes += 6_000_000
        self.disk.write_bytes += 10_000_000
        second = sampler.sample()
        self.assertEqual([second.values[key] for key in ("net_up", "net_down", "disk_read", "disk_write")], [2, 4, 3, 5])
        self.assertEqual(second.values["cpu_load"], 40)
        self.assertEqual(second.values["cpu_clock"], 2400)
        self.assertEqual(second.per_core, [20, 60])

    def test_cpu_package_power_does_not_double_count_subdomains(self):
        for name, label in (("intel-rapl:0", "package-0"), ("intel-rapl:0:0", "core"), ("intel-rapl:1", "psys")):
            zone = self.root / name
            zone.mkdir()
            (zone / "name").write_text(label)
            (zone / "energy_uj").write_text("1000000")
            (zone / "max_energy_range_uj").write_text("100000000")
        sampler = self.sampler()
        self.assertIsNone(sampler.sample().values["cpu_power"])
        self.clock.return_value = 102
        (self.root / "intel-rapl:0/energy_uj").write_text("11000000")
        self.assertEqual(sampler.sample().values["cpu_power"], 5)

    def test_gpu_queries_are_independent(self):
        sampler = self.sampler(nvml_available=True)
        with (
            patch("telemetry.pynvml.nvmlDeviceGetHandleByIndex", return_value=object()),
            patch("telemetry.pynvml.nvmlDeviceGetTemperature", return_value=62),
            patch("telemetry.pynvml.nvmlDeviceGetUtilizationRates", return_value=Data(gpu=75)),
            patch("telemetry.pynvml.nvmlDeviceGetMemoryInfo", return_value=Data(used=2, total=8)),
            patch("telemetry.pynvml.nvmlDeviceGetPowerUsage", side_effect=pynvml.NVMLError_NotSupported),
            patch("telemetry.pynvml.nvmlDeviceGetClockInfo", return_value=1800),
        ):
            sample = sampler.sample()
        self.assertIsNone(sample.values["gpu_power"])
        self.assertEqual(sample.values["gpu_temp"], 62)
        self.assertEqual(sample.values["gpu_load"], 75)
        self.assertEqual(sample.values["vram"], 25)
        self.assertEqual(sample.values["gpu_clock"], 1800)
        self.assertIn("not exposed", sample.unavailable["gpu_power"])

    def test_cpu_temperature_fallback_ignores_unrelated_sensors(self):
        self.ec.clear()
        with patch("telemetry.psutil.sensors_temperatures", return_value={
            "acpitz": [Data(label="", current=90)],
            "coretemp": [Data(label="Package id 0", current=50)],
        }):
            self.assertEqual(self.sampler().sample().values["cpu_temp"], 50)


if __name__ == "__main__":
    unittest.main()
