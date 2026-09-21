# give_laptop_ac

Full-hardware TUI for MSI Cyborg 15 A12U (and compatible MSI laptops with `msi-ec` kernel module).

## Features

### Dashboard (Tab 1)
- Compact CPU, GPU, memory, and battery overview, adapting to terminal width
- Current firmware mode, cooling mode, and control-service connection at a glance
- Press `v` for the full colored sensor charts; CPU cores expand separately
- Real-time CPU/GPU temps with sparkline history
- RAM usage + history
- GPU utilization
- CPU/GPU fan speed (%) with history
- Network and disk throughput in MB/s, calculated from elapsed time
- Current numeric readings alongside the colored charts
- CPU package power from RAPL energy counters when readable
- Unavailable readings display `N/A`; the first rate sample waits for a second reading
- Per-core CPU usage bars
- Battery status, disk I/O, CPU frequency

### Controls (Tab 2)
- **Presets**: Gaming, AI Mode, Balanced, Silent (one-click)
- **Performance Mode**: Eco / Comfort / Turbo
- **Fan Mode**: Auto / Silent / Advanced
- **Cooler Boost** toggle (`c` key)
- **Super Battery** toggle
- **Battery Charge Limit**: 60%, 70%, 80%, 90%, 100%
- **Keyboard Backlight**: Off + adjustable levels
- Hardware writes are read back before a change is marked successful or saved
- Failed presets attempt to restore the previous settings and report any rollback failure
- D-Bus backend connection status, capability detection, and a Reconnect button
- Supported EC controls and presets run through the service when connected
- Fan-curve read/preset actions enable only when the backend reports a verified layout
- Restore Auto returns fan control to the firmware
- Unsupported controls show the reason they are unavailable

Network and disk rates use [psutil's cumulative I/O counters](https://psutil.io/api/).
CPU package watts are calculated from [RAPL energy counters](https://cdn.kernel.org/doc/html/latest/power/powercap/powercap.html).
GPU capabilities are queried independently through [NVML](https://docs.nvidia.com/deploy/nvml-api/api/group__nvmlDeviceQueries.html), so an unsupported power query does not hide available GPU temperature or clock readings.
On a hybrid-graphics desktop, the dashboard retries NVML periodically after a
sleeping NVIDIA GPU wakes and reports when it is temporarily using EC-only GPU
temperature/fan telemetry.

### Processes (Tab 3)
- Sortable process table (CPU, RAM, Name)
- Kill process (`🗡 Kill`)
- Drop caches (`🧹 Drop Cache`)

## Installation

```bash
# Requires msi-ec kernel module (see msi-ec/ submodule)
# Python deps:
pip install textual psutil pynvml pydantic pyyaml

# Run
python main.py
```

From the Underlight Hyprland configuration, middle-click the Waybar GPU readout
or press `Super+Shift+A`. The shared `underlight-laptop` launcher selects this
project's virtual environment automatically.

## Connect the backend

```bash
cd msi-ec-daemon
./build.sh Release
sudo ./install.sh --start
```

Log out and back in after the installer adds you to the `msi-ec` group. Then run
`python main.py`, press `o` for Controls, and select **Reconnect** (or press `r`).
See [backend setup and supported capabilities](msi-ec-daemon/README.md).

For Cyborg firmware `15K1IMS1.113`, enable the supported six-step fan curve:

```bash
sudo bash msi-ec-daemon/install.sh --enable-curves --start
```

Then select **Controls → Reconnect → Read Curve**. The backend uses `ec_sys`
for the fan-speed table, checks the firmware and current curve, and keeps the
firmware temperature thresholds fixed. See the [layout and validation notes](msi-ec-daemon/docs/cyborg-fan-layout.md).
Other firmware layouts remain disabled. The Controls tab's **Setup** button
shows these steps. Battery and keyboard controls still use direct sysfs permissions.

## Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `d` / `1` | Dashboard tab |
| `o` / `2` | Controls tab |
| `p` / `3` | Processes tab |
| `j` / `k` | Scroll down / up (move between rows in Processes) |
| `f` / `b` | Page down / up |
| `h` / `l` | Scroll left / right |
| `c` | Toggle Cooler Boost |
| `r` | Refresh now |
| `v` | Expand/collapse dashboard sensor charts |

The letter shortcuts work even when a button or the tab bar has focus.

## Configuration

Settings persist automatically to `~/.config/give_laptop_ac/config.yaml`:

```yaml
last_preset: "p-balanced"
battery_limit: 80
battery_start_limit: 70
kbd_brightness: 2
performance_mode: "comfort"
fan_mode: "auto"
cooler_boost: false
theme: "default"
# ... (see CHANGELOG.md for full schema)
```

### Reset to defaults
```bash
rm ~/.config/give_laptop_ac/config.yaml
```

## Requirements

- Linux kernel with `msi-ec` module loaded
- Running backend and `msi-ec` group membership for EC controls; local sysfs write permissions for battery/keyboard controls (or direct EC access)
- NVIDIA GPU with `nvidia-smi`/`pynvml` for GPU stats
- Python 3.10+

## Project Structure

```
give_laptop_ac/
├── main.py          # Main TUI application
├── dashboard.py     # Responsive overview cards
├── telemetry.py     # Sensor readings and counter-to-rate calculations
├── hardware.py      # Verified sysfs writes and preset rollback
├── fan_backend.py   # Async D-Bus client
├── msi-ec-daemon/   # C++ system-bus service and integration setup
├── config.py        # Configuration management
├── tests/           # Telemetry, simulated hardware, and headless TUI checks
├── msi-ec/          # Kernel module submodule (git submodule)
├── CHANGELOG.md     # Version history
└── README.md        # This file
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Hardware-control tests use temporary files to simulate sysfs, including rejected
writes and rollback failures. They do not require hardware privileges.

## License

MIT
