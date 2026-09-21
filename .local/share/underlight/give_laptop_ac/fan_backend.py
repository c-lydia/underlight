"""Async client for the local MSI EC system-bus service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import shutil


class BackendError(RuntimeError):
    """A rejected operation or an invalid response; never implies success."""


@dataclass(frozen=True)
class BackendStatus:
    connected: bool = False
    firmware: str = "unknown"
    curve_read: bool = False
    curve_write: bool = False
    reason: str = "Service not connected"
    fan_modes: tuple[str, ...] = ()


class FanBackend:
    SERVICE = "com.msi_ec.FanControl"
    OBJECT = "/com/msi_ec/FanControl"

    def __init__(self, *, session: bool = False, timeout: float = 3.0):
        self.bus = "--user" if session else "--system"
        self.timeout = timeout
        self.status = BackendStatus()

    async def _call(self, method: str, signature: str = "", *args: str, reply: str):
        busctl = shutil.which("busctl")
        if busctl is None:
            raise BackendError("busctl is missing; install systemd's command-line tools")
        command = [
            busctl, self.bus, "--json=short", f"--timeout={self.timeout}",
            "--auto-start=no", "--allow-interactive-authorization=no", "call",
            self.SERVICE, self.OBJECT, self.SERVICE, method,
        ]
        if signature:
            command.extend((signature, *args))
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise BackendError(f"Could not launch busctl: {exc}") from exc
        try:
            output, errors = await asyncio.wait_for(process.communicate(), self.timeout + 0.5)
        except (TimeoutError, asyncio.CancelledError) as exc:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise BackendError("Service timed out; refresh to check whether the operation completed") from exc
        if process.returncode:
            message = errors.decode(errors="replace").strip()
            if any(word in message for word in ("ServiceUnknown", "not provided", "not activatable", "not found", "not running")):
                message = "Service offline; start msi-ec-daemon and reconnect"
            elif "Access denied" in message or "AccessDenied" in message:
                message = "Service access denied; your login needs membership in the msi-ec group"
            raise BackendError(message[:400] or "D-Bus call failed")
        try:
            response = json.loads(output)
            if not isinstance(response, dict) or response["type"] != reply or not isinstance(response["data"], list) or len(response["data"]) != 1:
                raise ValueError("unexpected reply type")
            return response["data"][0]
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise BackendError("Invalid response from fan-control service; rebuild/restart the daemon") from exc

    async def probe(self) -> BackendStatus:
        try:
            caps = await self._call("GetCapabilities", reply="a{ss}")
            if not isinstance(caps, dict) or caps.get("protocol_version") != "1":
                raise BackendError("Incompatible fan-control service; rebuild/restart the daemon")
            if any(caps.get(key) not in ("true", "false") for key in ("curve_read", "curve_write")):
                raise BackendError("Service returned invalid capabilities")
            if not all(isinstance(value, str) for value in caps.values()):
                raise BackendError("Service returned invalid capabilities")
            modes = await self._call("ListFanModes", reply="as")
            if not isinstance(modes, list) or not all(isinstance(mode, str) for mode in modes):
                raise BackendError("Service returned invalid fan modes")
            self.status = BackendStatus(
                connected=True, firmware=caps.get("firmware", "unknown"),
                curve_read=caps["curve_read"] == "true", curve_write=caps["curve_write"] == "true",
                reason=caps.get("curve_reason", ""), fan_modes=tuple(modes),
            )
        except BackendError as exc:
            self.status = BackendStatus(reason=str(exc))
        return self.status

    async def apply_controls(self, changes: dict[str, str]) -> None:
        args = [str(len(changes))]
        for name, value in changes.items():
            args.extend((name, value))
        if await self._call("ApplyControls", "a{ss}", *args, reply="b") is not True:
            raise BackendError("Service rejected the control change")
        for name, expected in changes.items():
            actual = await self._call("ReadControl", "s", name, reply="s")
            if actual != expected:
                raise BackendError(f"{name} readback differs from the requested value; refresh hardware state")

    async def read_curve(self) -> list[list[int]]:
        points = await self._call("ReadCurve", reply="a(yy)")
        if not isinstance(points, list) or not 2 <= len(points) <= 12:
            raise BackendError("Service returned an invalid curve")
        for index, point in enumerate(points):
            if not isinstance(point, list) or len(point) != 2 or any(type(v) is not int or not 0 <= v <= 100 for v in point):
                raise BackendError("Service returned an invalid curve point")
            if index and (point[0] <= points[index - 1][0] or point[1] < points[index - 1][1]):
                raise BackendError("Service returned an invalid curve order")
        return points

    async def set_preset(self, preset: str) -> list[list[int]]:
        if preset not in ("performance", "silent", "balanced", "default", "max_cooling"):
            raise BackendError("Unknown curve preset")
        if await self._call("SetCurvePreset", "s", preset, reply="b") is not True:
            raise BackendError("Service rejected the curve preset")
        points = await self.read_curve()
        if await self._call("ReadFanMode", reply="s") != "advanced":
            raise BackendError("Curve was written but advanced mode is not active; refresh hardware state")
        return points
