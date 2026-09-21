"""Read hardware telemetry without changing hardware settings."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import time
from typing import Callable

import psutil
import pynvml


def number(value) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def optional_call(function, *args):
    try:
        return function(*args)
    except (OSError, ValueError, NotImplementedError, psutil.Error, pynvml.NVMLError):
        return None


class CounterRate:
    """Convert cumulative counters into rates, resetting after missing samples."""

    def __init__(self):
        self.previous: tuple[float, float] | None = None

    def sample(self, value: float | None, now: float, modulus: float | None = None) -> float | None:
        if value is None or not math.isfinite(value) or value < 0:
            self.previous = None
            return None
        previous, self.previous = self.previous, (now, value)
        if previous is None or now <= previous[0]:
            return None
        delta = value - previous[1]
        if delta < 0:
            if modulus is None or not (0 <= value < modulus and previous[1] < modulus):
                return None
            delta += modulus
        return delta / (now - previous[0])


@dataclass
class TelemetrySnapshot:
    values: dict[str, float | None]
    per_core: list[float] = field(default_factory=list)
    battery_charging: bool = False
    unavailable: dict[str, str] = field(default_factory=dict)


class TelemetrySampler:
    def __init__(
        self,
        ec_read: Callable[[str], str | None],
        *,
        nvml_available: bool = False,
        nvml_reason: str = "NVIDIA NVML is not connected",
        powercap: Path = Path("/sys/class/powercap"),
    ):
        self.ec_read = ec_read
        self.nvml_available = nvml_available
        self.nvml_reason = nvml_reason
        self._rates: dict[str, CounterRate] = {}
        self._cpu_primed = False
        self._power_zones = []
        # Select package domains only; adding core/uncore domains would double count.
        for zone in sorted(powercap.glob("intel-rapl:*")):
            try:
                if (zone / "name").read_text().strip().startswith("package-"):
                    self._power_zones.append(zone)
            except OSError:
                continue

    def _rate(self, key: str, value: float | None, now: float, modulus=None) -> float | None:
        return self._rates.setdefault(key, CounterRate()).sample(value, now, modulus)

    def _cpu_temperature(self) -> float | None:
        temperature = number(self.ec_read("cpu/realtime_temperature"))
        if temperature is not None:
            return temperature
        sensors = optional_call(psutil.sensors_temperatures) or {}
        for driver in ("coretemp", "k10temp", "zenpower"):
            entries = sensors.get(driver, [])
            for label in ("Package id 0", "Tdie", "Tctl"):
                for entry in entries:
                    if entry.label == label and number(entry.current) is not None:
                        return number(entry.current)
            temperatures = [number(entry.current) for entry in entries]
            temperatures = [value for value in temperatures if value is not None]
            if temperatures:
                return max(temperatures)
        return None

    def _cpu_power(self, now: float) -> tuple[float | None, str]:
        if not self._power_zones:
            return None, "CPU package energy counters are unavailable"
        powers = []
        reason = "Collecting two CPU energy samples"
        for zone in self._power_zones:
            energy = modulus = None
            try:
                energy = number((zone / "energy_uj").read_text())
                modulus = number((zone / "max_energy_range_uj").read_text())
            except PermissionError:
                reason = "CPU energy counter is not readable with current permissions"
            except OSError:
                reason = "CPU energy counter is unavailable"
            rate = self._rate(str(zone), energy, now, modulus)
            powers.append(None if rate is None else rate / 1_000_000)
        if any(power is None for power in powers):
            return None, reason
        return sum(powers), ""

    def sample(self) -> TelemetrySnapshot:
        now = time.monotonic()
        ram = optional_call(psutil.virtual_memory)
        battery = optional_call(psutil.sensors_battery)
        frequency = optional_call(psutil.cpu_freq)
        per_core = optional_call(psutil.cpu_percent, None, True)
        cpu_usage = None
        if per_core is not None:
            if self._cpu_primed and per_core:
                cpu_usage = sum(per_core) / len(per_core)
            else:
                # psutil's first nonblocking CPU sample is not a measurement.
                self._cpu_primed = True
                per_core = []
        else:
            self._cpu_primed = False

        values = {
            "cpu_temp": self._cpu_temperature(),
            "gpu_temp": number(self.ec_read("gpu/realtime_temperature")),
            "cpu_fan": number(self.ec_read("cpu/realtime_fan_speed")),
            "gpu_fan": number(self.ec_read("gpu/realtime_fan_speed")),
            "ram": number(ram.percent) if ram is not None else None,
            "battery": number(battery.percent) if battery is not None else None,
            "cpu_load": cpu_usage,
            "cpu_frequency": number(frequency.current) if frequency and frequency.current > 0 else None,
            "gpu_load": None,
            "vram": None,
            "gpu_power": None,
            "gpu_clock": None,
            "cpu_voltage": None,
            "gpu_voltage": None,
        }
        unavailable = {
            "cpu_voltage": "CPU voltage is not exposed by the supported sensor interfaces",
            "gpu_voltage": "GPU voltage is not exposed by the supported sensor interfaces",
        }
        if not self.nvml_available:
            for metric in ("gpu_load", "vram", "gpu_power", "gpu_clock"):
                unavailable[metric] = self.nvml_reason
        values["cpu_clock"] = values["cpu_frequency"]
        values["cpu_power"], unavailable["cpu_power"] = self._cpu_power(now)

        net = optional_call(psutil.net_io_counters)
        disk = optional_call(psutil.disk_io_counters)
        for key, counters, attribute in (
            ("net_up", net, "bytes_sent"),
            ("net_down", net, "bytes_recv"),
            ("disk_read", disk, "read_bytes"),
            ("disk_write", disk, "write_bytes"),
        ):
            counter = getattr(counters, attribute, None)
            rate = self._rate(key, counter, now)
            # MB/s uses decimal megabytes, matching the displayed unit.
            values[key] = None if rate is None else rate / 1_000_000
            unavailable[key] = "Collecting two counter samples" if counters is not None else "I/O counters unavailable"

        if self.nvml_available:
            handle = optional_call(pynvml.nvmlDeviceGetHandleByIndex, 0)
            if handle is not None:
                # Query each capability independently: unsupported power readings
                # must not hide working temperature, memory, or clock readings.
                temperature = optional_call(pynvml.nvmlDeviceGetTemperature, handle, pynvml.NVML_TEMPERATURE_GPU)
                if temperature is not None:
                    values["gpu_temp"] = number(temperature)
                utilization = optional_call(pynvml.nvmlDeviceGetUtilizationRates, handle)
                values["gpu_load"] = number(utilization.gpu) if utilization is not None else None
                memory = optional_call(pynvml.nvmlDeviceGetMemoryInfo, handle)
                if memory is not None and memory.total > 0:
                    values["vram"] = memory.used / memory.total * 100
                power = number(optional_call(pynvml.nvmlDeviceGetPowerUsage, handle))
                values["gpu_power"] = None if power is None else power / 1000
                values["gpu_clock"] = number(optional_call(pynvml.nvmlDeviceGetClockInfo, handle, pynvml.NVML_CLOCK_GRAPHICS))
                for metric in ("gpu_load", "vram", "gpu_power", "gpu_clock"):
                    if values[metric] is None:
                        unavailable[metric] = f"{metric.replace('_', ' ').title()} is not exposed by this GPU/driver"
            else:
                for metric in ("gpu_load", "vram", "gpu_power", "gpu_clock"):
                    unavailable[metric] = "NVIDIA GPU handle is unavailable"

        return TelemetrySnapshot(
            values=values,
            per_core=per_core or [],
            battery_charging=bool(battery and battery.power_plugged),
            unavailable=unavailable,
        )
