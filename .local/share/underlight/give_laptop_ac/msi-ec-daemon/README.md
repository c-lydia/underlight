# MSI EC control backend

C++ system-bus service used by the `give_laptop_ac` TUI. It reads the `msi-ec`
kernel driver's capabilities and applies supported controls with readback.

## Build and install

Requires C++17, CMake 3.16+, pkg-config, and the **libsystemd development headers**.
The TUI uses `busctl`, so it needs no additional Python D-Bus dependency.

```bash
cd msi-ec-daemon
./build.sh Release
ctest --test-dir build --output-on-failure
sudo ./install.sh --start
```

The installer uses the CMake install prefix (default `/usr/local`), installs the
system-bus policy and systemd service, and adds the invoking sudo user to the
`msi-ec` group. Log out and back in after joining the group. Start the TUI as your
normal user, open Controls (`o`), and select **Reconnect** (or press `r`).

The service runs as root with access to the driver's sysfs files. D-Bus allows
read-only calls from other users; only root and the `msi-ec` group may change
controls. The API accepts an explicit list of controls and values. It does not
expose arbitrary paths, EC scans, or raw register writes to clients.

```bash
systemctl status msi-ec-daemon
journalctl -u msi-ec-daemon -n 30
```

## Controls and curves

- Firmware fan modes, performance modes, Cooler Boost, Super Battery, webcam,
  and Fn/Win placement use the driver's supported sysfs attributes.
- Transactions read current values, check each write and final state, and
  attempt to restore previous values on failure. Rollback failures are reported.
- The TUI keeps using direct verified sysfs access when the service is offline.
  It does not retry a failed service write through another path.
- Battery limits and keyboard brightness still use the TUI's verified sysfs
  path and require the appropriate local permissions.
- Curve reads/writes require both a raw EC interface and a layout verified for
  the **exact** firmware. The old built-in `0x50` paired-point layouts are
  unverified and remain disabled. Model-name matches alone do not enable them.
- Cyborg firmware `15K1IMS1.113` uses a separate, documented six-step speed
  table. Enable `ec_sys` and install the updated service with
  `sudo ./install.sh --enable-curves --start`. This also configures the driver
  for future boots. It enables curve access without applying a preset.
  See [the firmware-specific layout and checks](docs/cyborg-fan-layout.md).
- **Restore Auto** returns control to the firmware. It does not overwrite a
  curve with fabricated factory defaults.
- Curve writes validate every point, check readback, and verify advanced mode.
  They attempt to restore both the previous curve and mode if activation fails.
  Saved curves are not automatically replayed on startup.

The driver's [sysfs documentation](../msi-ec/docs/sysfs-platform-msi-ec) defines
its supported attributes and debug interface. The D-Bus implementation uses
[systemd's sd-bus API](https://www.freedesktop.org/software/systemd/man/latest/sd-bus.html).

## D-Bus API (protocol version 1)

Service/interface: `com.msi_ec.FanControl`

Object: `/com/msi_ec/FanControl`
Bus: system

| Method | Input → Output |
|---|---|
| `GetCapabilities` | `()` → `a{ss}` (protocol, firmware, curve support/reason) |
| `GetFirmwareVersion`, `GetModelId` | `()` → `s` |
| `ListFanModes`, `ListShiftModes` | `()` → `as` |
| `ReadFanMode`, `ReadShiftMode` | `()` → `s` |
| `ReadControl` | `s` → `s` |
| `WriteFanMode`, `WriteShiftMode` | `s` → `b` |
| `ApplyControls` | `a{ss}` → `b` |
| `ReadCurve` | `()` → `a(yy)` |
| `WriteCurve` | `a(yy)` → `b` (writes and activates advanced mode) |
| `SetCurvePreset` | `s` → `b` |

Errors are D-Bus errors, never substitute curves or successful-looking defaults.
Supported curve preset names are `performance`, `silent`, `balanced`, `default`
(an application preset, not a factory reset), and `max_cooling`. Presets must
match the verified layout's point count. On the supported Cyborg, presets are
sampled at the existing temperature steps and the hottest speed remains 100%.

## CLI

The CLI accesses sysfs directly; it is useful for diagnostics and requires
local write permissions for changing controls.

```bash
./build/msi-ec-cli info
./build/msi-ec-cli shift get
./build/msi-ec-cli mode get
./build/msi-ec-cli curve read
./build/msi-ec-cli mode set silent
./build/msi-ec-cli curve reset  # return to firmware automatic mode
```

## Tests

From the project root:

```bash
ctest --test-dir msi-ec-daemon/build --output-on-failure
dbus-run-session -- env MSI_EC_TEST_BUS=1 .venv/bin/python -m unittest discover -s tests -v
```

The integration tests start a daemon on a private session bus with a temporary
sysfs directory and simulated EC memory. They never write to live hardware.
`--session`, `--sysfs PATH`, and `--ec-io PATH` are explicit daemon options for this setup; production defaults to the system
bus and `/sys/devices/platform/msi-ec`.
