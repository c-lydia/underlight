"""Verified sysfs writes and grouped changes with rollback."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class WriteResult:
    success: bool
    message: str = ""

    def __bool__(self) -> bool:
        return self.success


def read_attr(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text().strip()
    except OSError:
        return None


def write_verified(path: Path | None, value: str) -> WriteResult:
    if path is None:
        return WriteResult(False, "Control unavailable on this machine")
    try:
        before = path.read_text().strip()
        if before == value:
            return WriteResult(True)
        # Do not create missing attributes. This also works with ordinary files
        # used to exercise the controller without writing to real hardware.
        descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC)
        with os.fdopen(descriptor, "w") as attribute:
            attribute.write(value)
        observed = path.read_text().strip()
    except PermissionError:
        return WriteResult(False, f"{path.name}: permission denied")
    except FileNotFoundError:
        return WriteResult(False, f"{path.name}: control unavailable")
    except OSError as error:
        return WriteResult(False, f"{path.name}: {error.strerror or error}")
    if observed != value:
        return WriteResult(False, f"{path.name}: requested {value}, hardware reports {observed}")
    return WriteResult(True)


def apply_verified(changes: dict[Path, str]) -> WriteResult:
    """Read original values first, then restore attempted writes on a failure."""
    before = {}
    for path in changes:
        original = read_attr(path)
        if original is None:
            return WriteResult(False, f"{path.name}: control unavailable or unreadable")
        before[path] = original

    attempted = []
    failure = None
    for path, value in changes.items():
        attempted.append(path)
        result = write_verified(path, value)
        if not result:
            failure = result.message
            break
    if failure is None:
        # Firmware may couple controls, so later writes can change earlier ones.
        for path, value in changes.items():
            observed = read_attr(path)
            if observed != value:
                failure = f"{path.name}: requested {value}, hardware reports {observed}"
                break
    if failure is not None:
        failures = []
        for changed in reversed(attempted):
            restored = write_verified(changed, before[changed])
            if not restored:
                failures.append(changed.name)
        for changed in attempted:
            if read_attr(changed) != before[changed] and changed.name not in failures:
                failures.append(changed.name)
        recovery = "Previous settings restored" if not failures else "Could not restore: " + ", ".join(failures)
        return WriteResult(False, f"{failure}. {recovery}")
    return WriteResult(True)
