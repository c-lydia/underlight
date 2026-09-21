# Changelog

## Hybrid GPU Desktop Integration (2026-09-21)

- Retry NVML after a sleeping NVIDIA dGPU wakes instead of fixing GPU support
  to the result of the application's first startup probe.
- Surface the NVML connection reason and distinguish EC-only GPU telemetry.
- Connect the dashboard to Underlight's GPU/AI menu, system doctor, and
  opt-in AC/battery performance profiles.
- Document the Underlight Waybar and Hyprland launcher integration.

## Telemetry and Verified Controls (2026-09-15)

- Calculate network/disk MB/s from counter deltas and elapsed time.
- Read CPU package power from available RAPL package energy counters.
- Display current values and `N/A` for missing readings; query GPU capabilities independently.
- Use the battery power-supply and keyboard LED interfaces exposed by the driver.
- Verify hardware writes, restore prior settings after failed grouped changes, and report rollback failures.
- Save confirmed performance, fan, cooler-boost, and battery threshold settings.
- Show actual control states and disable unavailable controls, including the unconnected fan-curve actions.
- Add automated tests for telemetry, simulated control failures, and TUI behavior.

## Phase 1 — Config Persistence (2026-09-13)

### Added
- **`config.py`** — Pydantic v2 settings model with YAML persistence
- **XDG-compliant config location** — `~/.config/give_laptop_ac/config.yaml`
- **Auto-load on app mount** — Restores last preset, battery limit, keyboard brightness, performance mode, fan mode
- **Auto-save on quit** — Persists current state when exiting via `q` or `action_quit`
- **Live config updates** — Every control change updates config immediately

### Config Schema
```yaml
version: 1
last_preset: "p-balanced"      # Active preset (p-gaming, p-ai, p-balanced, p-silent)
battery_limit: 80              # Charge limit percentage (60-100)
kbd_brightness: 2              # Keyboard backlight level (0-max)
performance_mode: "comfort"    # eco, comfort, turbo
fan_mode: "auto"               # auto, silent, advanced
theme: "default"               # UI theme name
fan_curves:
  cpu:
    points: [[40, 20], [55, 40], [70, 70], [85, 100]]
  gpu:
    points: [[40, 20], [55, 40], [70, 70], [85, 100]]
alerts:
  cpu_warn: 75
  cpu_crit: 85
  gpu_warn: 78
  gpu_crit: 83
  fan_stall_enabled: true
logging:
  enabled: false
  interval_seconds: 10
  format: "jsonl"
  output_dir: "~/.local/share/give_laptop_ac/logs"
```

### Files
- **New:** `config.py` — Settings model, load/save/reset functions
- **Modified:** `main.py` — Config integration in `GiveLaptopAC` class

### Usage
```bash
# Run app (config auto-loads/saves)
python main.py

# Reset config to defaults
python main.py --reset-config  # (flag not yet implemented in CLI)
# Or manually:
rm ~/.config/give_laptop_ac/config.yaml

# View current config
cat ~/.config/give_laptop_ac/config.yaml
```

### Dependencies Added
- `pydantic>=2.13`
- `pyyaml>=6.0`
