# Underlight code walkthrough

This document explains how the complete repository works. It follows execution
from installation to login, then walks through the desktop helpers, widgets,
laptop controller, fan-control service, RAG pipeline, and tests. The final file
map accounts for every tracked file that is not generated at runtime.

## 1. The system in one view

Underlight is a collection of cooperating processes rather than one program:

```text
install.sh
  └─ links repository paths into $HOME
       └─ Hyprland reads ~/.config/hypr/hyprland.conf
            ├─ sources underlight/*.conf
            ├─ starts Waybar, Mako, Hyprpaper, Hypridle, and GTK widgets
            └─ maps keys and clicks to ~/.local/bin/underlight-*
                    ├─ menus, screenshots, clipboard, and power profiles
                    ├─ GPU/AI launchers and diagnostics
                    ├─ give_laptop_ac Textual dashboard
                    │    └─ busctl → privileged msi-ec-daemon → sysfs/raw EC
                    └─ optional RAG CLI
                         ├─ SentenceTransformer/Ollama embeddings
                         ├─ LanceDB
                         └─ Ollama generation
```

Configuration lives in the repository. Mutable state does not: backups,
workspace selection, chat logs, vector databases, Python environments,
screenshots, clipboard history, and application settings are all written below
the user's home/state directories.

## 2. Installation and rollback

### `install.sh`

The main installer runs with strict Bash error handling and treats the
repository directory as the source of truth. `target_home` is `$HOME` unless a
different directory is passed, which also makes the installer testable without
touching a real home directory.

`link_item(relative_path)` implements the install transaction:

1. Check that the repository item exists.
2. Return early if the target is already a symlink to that item.
3. Create the target's parent directory.
4. Move an existing file, directory, or symlink into a timestamped backup.
5. Create the new symbolic link and record its relative path.

The script links the Hyprland entry point and module directory, application
configs, style assets, helper commands, Neovim overlay, and bundled laptop
dashboard. The RAG source directory is linked only when
`UNDERLIGHT_WITH_RAG=1`.

Before linking those files, `install_neovim_workbench()` bootstraps the editor.
For a real-home Ubuntu install it uses `apt` when the `nvim` executable is
missing. It then clones `c-lydia/neovim_config` below
`~/.local/share/underlight`, or accepts an existing checkout through
`UNDERLIGHT_NEOVIM_SOURCE`. If `~/.config/nvim` is free, the workbench is linked
there and recorded in the same rollback transaction. An unrelated existing
configuration is never replaced; it only receives the transparency overlay.
`UNDERLIGHT_SKIP_NEOVIM=1` disables this optional bootstrap.

At the end, `linked-items` records exactly which targets this transaction
changed. Repository sources use the original one-column format; external
sources such as the Neovim checkout add the resolved source in a second column.
`--restore latest` finds the newest backup; an explicit backup path may also be
supplied. Restore processes entries in reverse order so nested overlays are
removed before a parent Neovim link. It removes only symlinks that still point
at their recorded source. If the user has replaced or edited a target into
something else, rollback preserves it and reports that decision. A backed-up
original is then moved home, or a link created for a previously absent target
is simply removed.

### `install-endeavouros.sh`

The EndeavourOS bootstrap adds machine provisioning around `install.sh`:

- Parses `--with-ai` and `--with-rag`; RAG implies AI.
- Refuses root execution and verifies an Arch-family `/etc/os-release` plus
  `pacman`.
- Installs the Hyprland desktop, Wayland utilities, fonts, build tools, Python
  GTK dependencies, Neovim tooling, and laptop-dashboard dependencies.
- Optionally adds Ollama and OpenCode.
- Clones the separate Neovim workbench into
  `~/.local/share/underlight/neovim_config`, without replacing an unrelated
  existing Neovim configuration.
- Calls the normal symlink installer, optionally exposing the RAG source.
- Creates isolated virtual environments for `give_laptop_ac` and, when
  selected, the RAG pipeline.
- Copies the example RAG configuration only when the user's config does not
  already exist.
- Optionally enables Ollama, but deliberately downloads neither models nor
  indexes.

The NVIDIA driver is outside this installer because the correct package is
machine- and kernel-specific.

## 3. Hyprland composition

### Entry point and source order

`.config/hypr/hyprland.conf` contains only ordered `source` directives. That
order matters: colors are declared before appearance uses them; environment and
GPU policy are loaded before applications start; bindings and rules come last.

The sourced modules are:

- `colors.conf`: declares the Tokyo Night-inspired color variables shared by
  Hyprland rules.
- `environment.conf`: exports cursor sizes, Wayland/Qt/Electron/Mozilla hints,
  the Hyprland desktop identifiers, and GNOME's menu prefix.
- `gpu.conf`: documents the hybrid-GPU policy. It intentionally does not set
  NVIDIA vendor variables globally; per-application offload belongs to
  `underlight-gpu-run`.
- `monitors.conf`: uses each display's preferred mode, automatic placement,
  and native scale. It is the small extension point for machine-specific
  monitor rules.
- `input.conf`: configures a US keyboard, adaptive pointer acceleration,
  touchpad behavior, and three-finger horizontal workspace gestures.
- `looknfeel.conf`: sets gaps, gradient borders, opacity, shadows, blur,
  animations, the dwindle/master defaults, compositor performance options, and
  namespace-specific blur rules for Waybar, Wofi, Mako, and Underlight widgets.
- `autostart.conf`: imports the Wayland environment into D-Bus/systemd and
  starts Hyprpaper, Waybar, widgets, Hypridle, and optional helpers. Two
  `wl-paste` watchers feed text and image clipboard entries to `cliphist`. The
  health notification is delayed so the GPU driver has time to settle.
- `background-apps.conf`: an intentionally empty, documented extension point
  for user `exec-once` commands.
- `bindings.conf`: defines application launch keys, window operations,
  workspaces, mouse move/resize, media keys, screenshot keys, menus, and the
  special `minimized` workspace.
- `rules.conf`: suppresses maximize requests, floats settings and file dialogs,
  and inhibits idle while supported media applications are fullscreen.

### Binding-to-script flow

The central bindings are `Super+Space` for Wofi, `Super+X` for all system
actions, `Super+M` for power,
`Super+Shift+V` for clipboard history, `Super+Shift+A` for the laptop dashboard,
`Super+Shift+G` for GPU/compute actions, and `Super+Shift+I` for AI tools.
Print Screen captures the whole display; `Super+Shift+S` captures a selection.
`Super+N` moves the current window to or from a hidden special workspace.

Window focus, movement, and resize support both arrows and H/J/K/L.
`Super+Tab` and `Super+Shift+Tab` move to the next and previous desktops. Number
keys select workspaces; shifted number keys move windows. Audio and brightness
keys call PipeWire and `brightnessctl`, while media keys call `playerctl` only
when it is installed.

## 4. Desktop surfaces and styling

### Kitty, Mako, Wofi, and Neovim

`.config/kitty/kitty.conf` selects Noto Sans Mono, an 11.5-point size,
transparent background, padding, hidden client decorations, a beam cursor, and
the shared palette.

`.config/mako/config` creates compact translucent top-right notifications.
Normal notifications expire after six seconds; high-urgency notifications use
a red border and remain until dismissed.

`.config/wofi/config` selects application (`drun`) mode, fuzzy case-insensitive
matching, images, centered dimensions, and Kitty as the terminal. Its
`style.css` supplies the translucent rounded window, search box, entry states,
spacing, and selected-row colors.

`.config/nvim/after/plugin/underlight-transparent.lua` lists highlight groups
whose backgrounds should be transparent. `clear_backgrounds()` reads each
current highlight safely, removes GUI and terminal backgrounds, and writes it
back. It runs once after startup and after every `ColorScheme` event, so a theme
reload cannot permanently restore opaque backgrounds.

The full configuration installed from the companion `neovim_config`
repository is documented separately in
[NEOVIM_CONFIG_WALKTHROUGH.md](NEOVIM_CONFIG_WALKTHROUGH.md). That guide covers
its bootstrap, all Lua modules and plugin specifications, developer workflows,
installer, lockfiles, and release tests. Keeping it separate makes the boundary
clear: Underlight owns the installer, desktop commands, and transparency
overlay; the companion repository owns the editor workbench.

### Waybar

`.config/waybar/config.jsonc` divides the bar into three groups:

- Navigation: launcher, Hyprland workspaces, and active-window mode.
- Hardware: network, CPU, memory, GPU, and fan state.
- Session: widget toggle, tray, audio, battery, and power menu.

Native modules read system state directly. Custom modules execute
`underlight-window-mode` and `underlight-sensor`, both of which return Waybar
JSON. Click handlers reuse the same commands exposed by keyboard shortcuts.
`underlight-control` provides keyboard access to every bar action, and
`underlight-network` provides the same NetworkManager/Wofi Wi-Fi picker on
Ubuntu and EndeavourOS; the other hardware sections open the widgets,
diagnostics, laptop controls, audio mixer, or power-profile menu.

`.config/waybar/style.css` makes each group a translucent outlined capsule. It
styles workspace active/urgent states, tile/float state, hardware warning and
critical classes, sleeping/active GPUs, muted audio, charging batteries, hover
states, and tooltips. The class names emitted by helper scripts are therefore a
small interface between process output and CSS.

### Desktop widget CSS and logo

`.config/underlight/widgets.css` styles all four GTK panels. It covers panel
glass/hover effects, the brand header, large clock, calendar grid and current
day, media metadata and buttons, separators, progress meters, removable-drive
rows, status errors, and action buttons.

`.config/underlight/logo.svg` is a 64×64 U-shaped mark filled by a pink-violet-
cyan gradient with a translucent highlight. The GTK date panel loads it from
the live config directory.

## 5. Helper commands

### Application and session helpers

- `.local/bin/underlight-menu` replaces itself with Wofi's application view.
- `.local/bin/underlight-control` presents every Waybar action in one
  keyboard-driven Wofi menu and provides the shared audio-mixer fallback.
- `.local/bin/underlight-network` scans and selects Wi-Fi with NetworkManager,
  reuses saved credentials, and requests a missing password through Wofi.
- `.local/bin/underlight-power` pipes five actions into Wofi, then maps the
  chosen label to `loginctl`, `systemctl`, or `hyprctl`. Canceling produces no
  action.
- `.local/bin/underlight-clipboard` verifies `cliphist` and `wl-copy`, lets the
  user pick an encoded history row, decodes it, and returns it to the Wayland
  clipboard.
- `.local/bin/underlight-shot` creates a timestamped PNG below
  `Pictures/Screenshots`. It prefers Grim/Slurp, falls back to GNOME Screenshot,
  copies the result with `wl-copy`, and sends a notification.
- `.local/bin/underlight-minimize` reads the active Hyprland window as JSON. A
  normal window moves silently to `special:minimized`; a window already there
  moves to the current numbered workspace and closes the special-workspace
  view.
- `.local/bin/underlight-background` sanitizes the executable name, adds a
  random suffix, and starts the command as a collected transient systemd user
  service. This detaches lifetime and logs from the launching terminal.

### Status and diagnostics

- `.local/bin/underlight-window-mode` converts `hyprctl activewindow -j` into
  `DESK`, `FLOAT`, or `TILE` JSON with a matching CSS class and contextual
  tooltip.
- `.local/bin/underlight-sensor` has `gpu` and `fan` modes. GPU mode first parses
  `nvidia-smi`, classifies activity from utilization/power/VRAM, and adds compute
  process names. If NVIDIA is present but inaccessible it reports sleep; it can
  then fall back to Intel GT clock files. Fan mode scans hwmon fan inputs while
  excluding the misleading `msi_wmi_platform` source and reports the fastest
  RPM. `json()` escapes text for Waybar.
- `.local/bin/underlight-gpu-check` prints display controllers, DRM nodes,
  NVIDIA DRM modesetting, NVIDIA telemetry, PRIME discovery, and usage examples.
  `--terminal` relaunches the report in Kitty.
- `.local/bin/underlight-doctor` accumulates pass/warn/fail counts. It verifies
  core executables and Hyprland syntax, distinguishes an inaccessible sandboxed
  GPU from a host driver failure, checks PRIME and power profiles, probes the AI
  tools and configs, then checks Neovim, ROS 2, the laptop dashboard, and the
  optional RAG environment. Only hard failures make the final exit status fail.
- `.local/bin/underlight-health-notify` is the quiet login check. It only sends a
  critical notification when `nvidia-smi` fails while `/dev/nvidiactl` is
  actually visible; missing device nodes in a container do not trigger it.

### GPU, power, and AI launchers

- `.local/bin/underlight-gpu-run` requires a command. It prefers
  `switcherooctl launch` when the service reports GPUs, otherwise sets NVIDIA
  PRIME variables when NVIDIA hardware/driver evidence exists, and finally
  uses Mesa's `DRI_PRIME=1` fallback.
- `.local/bin/underlight-profile` reads AC state from power-supply sysfs and
  applies `balanced`, `performance`/`ai`, `power-saver`, or an AC-aware `auto`
  choice through `powerprofilesctl`. If a trailing command is supplied,
  performance/AI mode also routes that command through discrete-GPU offload.
- `.local/bin/underlight-gpu-menu` is the Wofi dispatcher for AI tools, an
  arbitrary NVIDIA command, the dashboard, diagnostics, or power profiles.
- `.local/bin/underlight-ai` provides `menu`, `status`, `opencode`, `hermes`, and
  `ollama`. It detects installed tools, checks the Hermes gateway PID, selects
  Ollama models with Wofi, switches interactive workloads to the AI profile,
  and launches each tool in a correctly titled/classed Kitty window. It does
  not edit provider or credential configuration.
- `.local/bin/underlight-install-extras` is the Ubuntu-specific apt wrapper for
  notifications, screenshots, clipboard history, brightness, media, audio,
  PRIME, and network applet utilities.

### Workspace and component launchers

`.local/bin/nvim-workspace` parses a project directory plus `--set-only`,
repeatable `--gui`, and repeatable `--flatpak` options. It validates the project,
atomically writes its real path to
`$XDG_STATE_HOME/nvim-workspace/project`, and optionally opens a four-application
development workspace. Under Hyprland it launches separate Kitty classes for a
normal Neovim instance, a Neovim terminal, and Codex (or a shell fallback), plus
Firefox. Outside Hyprland it launches desktop entries with `gtk-launch`. Extra
native and Flatpak apps are started afterward. Window placement is left to the
desktop rules/integration that recognizes those application classes.

`.local/bin/underlight-laptop` selects the dashboard source in this order:
`GIVE_LAPTOP_AC_HOME`, `~/projects/give_laptop_ac`, then the bundled copy. It
similarly prefers a project-local virtual environment, then Underlight's shared
environment, then system Python. `--inline` runs in the current terminal;
otherwise it prefers Kitty and falls back to `x-terminal-emulator`.

`.local/bin/underlight-rag` verifies that the optional source, virtual
environment, and config all exist. It maps friendly subcommands to the Python
programs: `ask` uses retrieval, `direct` calls Ollama without retrieval, `chat`
manages history, `index` builds tables, `server` starts HTTP, and `opencode`
starts the companion tool with the RAG environment on `PATH`.

## 6. GTK desktop widgets

`.local/bin/underlight-widgets` is a single Python/GTK 3 process owning four
layer-shell windows. Keeping them in one process provides consistent stacking
and one timer loop.

### Construction

`UnderlightWidgets.__init__()` loads CSS and constructs:

- Date window: logo, brand label, live clock/date, month title, and calendar.
- Media window: current MPRIS playback state, title, artist, and
  previous/play-pause/next buttons. It is hidden when no active player has a
  title.
- System window: uptime plus CPU, memory, root-filesystem, and battery meters.
- Drives window: external filesystem rows and mount/open actions.

It performs an initial update, then schedules clock updates every second,
system readings every two seconds, and media/drive discovery every three.

### Window and layout methods

`_new_window()` creates a transparent, undecorated GTK window, assigns its
namespace, attaches content, and registers destroy/resize callbacks.
`_clear_window_background()` uses Cairo's source operator so CSS alpha reaches
Hyprland. `_put_on_underlight_layer()` calls the `gtk-layer-shell` C ABI through
`ctypes`, putting panels above the wallpaper but below ordinary windows with no
exclusive zone. `_queue_restack()` coalesces layout requests; `_restack()`
places visible windows down the right edge, skipping the media panel when
hidden. `_set_layer_margin()` performs the actual top-margin update.

`_load_css()`, `_rule()`, and `_meter()` are construction helpers for shared
styles, separators, and labeled progress bars. `show()` displays the normally
visible panels and schedules a stack calculation. Destroying a window exits the
GTK loop.

### Data update methods

`_update_clock()` refreshes labels and only rebuilds the calendar when the date
changes. `_rebuild_calendar()` draws weekday headers and month cells, adding a
`today` class. `_set_meter()` clamps values to 0–100. `_update_system()` reads
psutil CPU, memory, disk, boot time, and battery information.

`_session_bus()` returns the session D-Bus connection. `_media_properties()`
lists MPRIS services, requests player properties, and returns the first player
with a title. `_update_media()` shows/hides and populates the panel;
`_media_action()` sends the selected MPRIS method.

`_walk_devices()` recursively flattens `lsblk` nodes. `_external_volumes()`
requests JSON, identifies removable/USB disks, excludes anything containing
root, home, or boot, and returns mountable filesystem partitions.
`_update_drives()` hashes that result to avoid unnecessary widget rebuilds.
`_drive_row()` chooses an open or mount button. `_open_drive()` starts Nautilus;
`_mount_drive()` starts `udisksctl` without blocking GTK; `_mount_finished()`
polls it, reports errors, and refreshes the rows.

`lock_single_instance()` takes a nonblocking per-user `flock` under `/tmp`.
Starting a second copy exits cleanly. The module entry point retains the lock,
creates the UI, shows it, and enters `Gtk.main()`.

`.local/bin/underlight-widgets-toggle` finds the exact widget command line,
stops existing instances, and either exits (`toggle`) or waits briefly and
restarts through `hyprctl` (`restart`).

## 7. `give_laptop_ac` dashboard

The bundled dashboard is a Textual application with three tabs. It is designed
to read broadly available telemetry without privileges while treating every
hardware write as a verified operation.

### Configuration: `config.py`

Pydantic models define fan curves, thermal alerts, optional logging, and the
full settings record. `load_config()` reads
`~/.config/give_laptop_ac/config.yaml`, validates it, and falls back to defaults
on invalid input. `save_config()` creates the directory and serializes the
model. `reset_config()` removes only that settings file. These functions return
success flags instead of hiding persistence failures from the UI.

### Safe local writes: `hardware.py`

`WriteResult` carries a boolean plus an explanation. `read_attr()` turns sysfs
read failures into `None`. `write_verified()` refuses missing paths, opens an
existing attribute without create permission, writes, reads it back, and
reports permission, availability, I/O, or mismatch errors.

`apply_verified()` is the local transaction primitive. It reads all original
values before writing anything, applies each change, performs a final pass to
detect firmware-coupled controls, and rolls back attempted writes in reverse
order after any failure. Its result says whether rollback itself succeeded.

### Telemetry: `telemetry.py`

`number()` rejects nonnumeric and nonfinite input. `optional_call()` normalizes
expected psutil/NVML/platform errors to missing data. `CounterRate` converts
cumulative byte/energy counters into per-second rates, handles an optional
counter modulus, and deliberately returns no value for the first or invalid
sample.

`TelemetrySnapshot` groups values, per-core CPU percentages, charging state,
and human-readable unavailability reasons. `TelemetrySampler`:

- Selects only package-level Intel RAPL zones to avoid double-counting power.
- Prefers MSI EC CPU temperature, then known CPU sensor drivers/labels.
- Samples CPU cores, memory, battery, frequency, network, disk, fans, and EC
  temperatures.
- Queries each NVML capability independently, so a missing power query does not
  erase working temperature or memory readings.
- Converts RAPL microjoules to watts and byte counters to decimal MB/s.
- Returns explicit reasons for unsupported voltages, unavailable GPU metrics,
  and counters that still need a second sample.

### Reusable UI widgets: `dashboard.py`

`reading()` formats a sensor or returns `N/A`. `OverviewCard` builds a title,
headline, detail line, and sparkline. `update_reading()` updates all three,
keeps the latest 60 valid points, hides the chart when data is missing, and
clears stale history.

### D-Bus client: `fan_backend.py`

`BackendStatus` records connection, firmware, curve read/write capabilities,
the limitation reason, and valid fan modes. `FanBackend._call()` invokes
`busctl` asynchronously with autostart and interactive authorization disabled,
enforces a timeout, kills a stuck child, translates common service/access
errors, parses `--json=short`, and validates the exact reply signature.

`probe()` requires protocol version 1, valid boolean capability strings, and a
string mode list. `apply_controls()` serializes an `a{ss}` map and reads every
control back. `read_curve()` validates point count, value ranges, strictly
increasing temperatures, and nondecreasing fan speeds. `set_preset()` accepts
only known names, asks the service to apply one, then verifies both the returned
curve and advanced fan mode.

### Main TUI: `main.py`

The top-level helpers map MSI EC, battery threshold, and keyboard-backlight
paths to the safe read/write functions. `SparkCard`, `CoreBar`, and `IoCard`
keep bounded histories. `CtrlRow` generates a labeled set of buttons, reflects
the active value, and routes clicks back to the app's verified write path.

`GiveLaptopAC` declares tab, navigation, detail, cooling, and refresh bindings.
Its constructor loads settings, initializes process/backend/UI state, attempts
NVML, and creates the telemetry sampler. `_connect_nvml()` records the GPU name
or schedules a retry so a sleeping hybrid GPU can appear later.

The embedded Textual CSS defines responsive overview layouts, sparkline
sections, hardware-control rows, process controls, backend status, and curve
actions. `compose()` builds:

1. Dashboard: four overview cards, compact power/activity summaries, optional
   detailed charts, and per-core charts.
2. Controls: four presets, performance/fan modes, EC toggles, battery limits,
   keyboard brightness, D-Bus state, and fan-curve actions.
3. Processes: sortable table plus terminate and drop-cache actions.

`_compose_sensor_charts()` creates and stores the metric cards.
`_compose_controls_and_processes()` builds the other tabs. `on_mount()` titles
containers, initializes the process table, synchronizes controls, installs the
two- and three-second timers, and probes the backend.

The synchronization path is deliberately separate from event handlers:

- `_layout_dashboard()` assigns wide/narrow CSS classes.
- `_update_dashboard_context()` summarizes mode, fan, boost, GPU, and backend.
- `_apply_config()` restores persisted EC settings through D-Bus when connected
  or verified local sysfs otherwise, then handles battery and keyboard state.
- `_sync_ctrl()` reads actual hardware and updates every active/disabled state.
- `_sync_backend()` updates capability text and disables curve/write controls
  while work is in flight.
- `_probe_backend()` is a Textual worker so D-Bus never blocks rendering.

Preset, battery, keyboard, toggle, curve, and single-control event handlers all
save only after readback. `_run_curve_action()` and
`_apply_backend_controls()` serialize backend work, surface errors, and re-probe
after failure. No failed D-Bus write is silently retried through direct sysfs.

The process tab enumerates psutil processes, sorts by CPU/RAM/name, shows 100
rows, sends `SIGTERM` to the selected PID, and requests Linux cache dropping
when asked. `_tick()` reconnects NVML as needed, updates every overview/chart,
builds status summaries, and applies temperature/fan-stall alerts.
`_tick_procs()` refreshes the process table. Action methods implement tab
switching, scroll/key navigation, detail expansion, refresh, and boost. On
unmount the application shuts NVML down. The module entry point also supports
`--reset-config`.

## 8. Privileged MSI EC service

The C++ service is a narrow privileged boundary. The TUI cannot supply paths or
raw register addresses over D-Bus; it can only call allowlisted operations.

### Build and installation files

- `msi-ec-daemon/CMakeLists.txt` builds a C++17 core library, optional CLI, and
  libsystemd-based daemon; installs headers, binaries, data, service/policy
  files; and registers the core test with CTest.
- `build.sh` configures all components in `build/` and compiles in parallel.
- `install.sh` requires root and an existing build. It optionally enables
  writable `ec_sys` only for firmware `15K1IMS1.113`, persists that module
  configuration, creates the `msi-ec` group, adds the invoking sudo user,
  installs artifacts, reloads systemd, and optionally starts the service.
- `systemd/msi-ec-daemon.service.in` runs the service as a D-Bus unit with
  automatic restart and a hardened filesystem/kernel/capability sandbox. Only
  MSI EC sysfs/debug paths are writable.
- `systemd/com.msi_ec.FanControl.conf` lets everyone introspect and read state,
  lets only `msi-ec` members call all control methods, and lets root own the bus
  name.

### EC abstraction: `include/ec_interface.h` and `src/ec_interface.cpp`

The header defines register descriptions, curve points/curves, fan/shift enums,
thermal readings, and an abstract byte/block EC interface. Shared helpers scan
addresses and compare snapshots.

`SysfsEC` is the production implementation. Initialization requires the MSI EC
directory and `fan_mode`. Known firmware/mode/telemetry registers map to named
sysfs attributes. Raw access uses the driver's debug endpoint or `ec_sys` I/O
only after the raw firmware bytes exactly match the reported firmware. Writes
check permissions, never create attributes, and verify readback.
`apply_controls()` validates names/values against allowlists or the driver's
advertised modes, takes a before-snapshot, writes and verifies, then restores on
failure.

Raw byte reads/writes use `pread`/`pwrite` when appropriate and otherwise the
MSI driver's debug protocol. Block methods repeat verified byte operations.
`PortIOEC` implements a lower-level command/data-port protocol, but
`create_best_backend()` intentionally selects only the supported sysfs backend;
there is no automatic raw port-I/O fallback.

### Curve logic: `include/fan_curve_manager.h` and
`src/fan_curve_manager.cpp`

`ModelFanCurveConfig` describes exact firmware, layout, telemetry addresses,
and whether the curve layout is verified. `ModelDatabase` loads built-in model
records and matches exact firmware strings. Only the Cyborg layout is flagged
as verified; the older generic `0x50` layouts remain discoverable but cannot be
used for curve I/O.

`FanCurveManager` reads and writes either paired points or separate temperature
and speed arrays. It rejects unsupported layouts, wrong point counts, values
outside 0–100, non-increasing temperatures, and decreasing speeds. On the
verified Cyborg layout, temperatures are fixed and the hottest speed must stay
at 100%. Writes take a snapshot, verify the entire result, and restore the old
curve after a failure. `apply_curve()` additionally activates advanced mode and
restores both curve and mode if activation fails.

Preset factories define default, performance, silent, balanced, and maximum
cooling shapes. `preset_for_hardware()` interpolates their speeds onto fixed
hardware temperature steps. `reset_to_default()` means returning fan mode to
firmware `auto`, not inventing a factory curve. `ECScanner` can dump all 256
bytes and flag adjacent percentage-like values for offline investigation; its
snapshot-diff method is currently a placeholder.

### D-Bus layer: `include/dbus_service.h`, `src/dbus_service.cpp`, and
`src/main.cpp`

`DBusService` owns the sd-bus connection and delegates control logic to the
manager. Static vtable entries expose capabilities, firmware/model, available
modes, allowlisted control reads/writes, grouped transactions, and curve
operations. Helpers construct string arrays/maps and translate C++ exceptions
to D-Bus errors.

`handle()` validates method-specific arguments, caps grouped controls at seven,
rejects duplicates/arbitrary controls, and never returns a success-shaped
default when hardware work fails. Capability discovery distinguishes curve
read support from raw write support.

The daemon `main.cpp` accepts test-only session-bus/sysfs/EC-I/O overrides,
initializes the sysfs backend, detects exact firmware, registers the service,
handles termination signals, and drives the sd-bus process/wait loop.

### CLI and static data

`src/cli.cpp` provides direct diagnostics for info, thermal readings, modes,
curves, scans, dumps, and known models. It parses custom point pairs with
`from_chars`, validates them, and delegates all safety/rollback behavior to the
manager.

`config/models.json` mirrors legacy model/register metadata and
`config/presets.json` describes the five human-readable curve shapes. CMake
installs them, but the present runtime deliberately uses compiled-in model and
preset definitions: `load_from_json()` is disabled. Changes to these JSON files
alone therefore do not alter service behavior.

`docs/cyborg-fan-layout.md` records the evidence and constraints for the sole
verified six-step Cyborg layout.

## 9. Optional RAG pipeline

### Configuration and dependencies

`.ragconfig.example.yaml` defines three source roots (`projects`, `downloads`,
and `home`), extensions and exclusions, OCR choices, chunk sizes, embedding
model/device, LanceDB paths/tables, Ollama settings, chat storage, and default
assistant tables. `config_loader.py` finds `RAG_CONFIG` (or a local default),
requires a YAML mapping, and recursively expands `~` and environment variables
in every string.

`requirements.txt` includes Sentence Transformers, LanceDB/PyArrow dependencies,
YAML, image/OCR libraries, Requests, tqdm, PyMuPDF, and Tree-sitter packages.

### Indexer: `indexer.py`

`Embedder` loads Sentence Transformers unless the configured device is
`ollama`. Its local path batches encoding; the Ollama path posts each text to
the embeddings API.

Chunk routing is extension-based:

- `chunk_code()` starts chunks at simple function/class/type declarations and
  falls back to line chunks when a block is large.
- `chunk_lines()` approximates tokens with whitespace words and keeps trailing
  lines as overlap.
- `chunk_text()` splits paragraphs, then large paragraphs by lines.
- `chunk_kicad()` groups top-level S-expressions using parenthesis depth.
- `chunk_pdf_pages()` emits one labeled chunk per extractable page.
- `ocr_image()` uses EasyOCR for configured GPU OCR or Tesseract/Pillow as the
  fallback.

`should_index()` enforces file type, excluded path components, and a 100 MiB
ceiling. `read_file_text()` selects PDF, image, KiCad, code, or text handling and
returns `(text, source-description)` pairs. `make_table_schema()` defines source
metadata plus a 384-float embedding. `index_dir()` discovers files, supports a
non-mutating dry run, embeds each file's chunks, creates deterministic IDs,
flushes batches of 2,000 rows, and writes the remainder. `main()` selects one or
all configured roots.

Current behavior worth knowing: table writes append rows rather than deleting
an older row with the same ID, despite the helper name `upsert_table`; config
`include` globs and image min/max sizes are present but are not consulted by the
current indexer.

### Retrieval and generation: `assistant.py`

The module loads config, the sentence-transformer model, and LanceDB at import
time. `_table_exists()` handles LanceDB versions that return either names or
tuples. `retrieve()` embeds a query, searches each requested table, converts
distance to a score, filters by minimum score, globally sorts, and returns the
top results.

`build_prompt()` labels retrieved chunks with score/source/path, includes up to
six remembered messages, adds a default or caller-provided system prompt, and
appends the question. `ask_ollama()` calls `/api/generate` with non-streaming
sampling options and converts timeout/connection failures into readable error
strings. `cmd_answer()` reports three progress stages, optionally retrieves and
logs chat history, and prints timing plus the answer. `cmd_ask_ollama()` skips
retrieval. `main()` exposes these as `answer` and `ask`.

### Chat memory: `chat_tracker.py`

Chat entries are stored twice: append-only JSONL for readable history and an
embedding table for semantic lookup. `_log_path()` sanitizes project labels.
`log_message()` timestamps in UTC, appends JSON, embeds the text, and calls
`store_msg()`. The table schema stores role, project, timestamp, metadata JSON,
and a 384-float vector.

`read_log()` returns recent chronological JSONL entries. `list_projects()`
lists log stems. `query_chat()` searches the vector table, optionally filters a
project, and decodes metadata. Command handlers implement `log`, `query`, and
`list` output.

### HTTP service: `rag_server.py`

`RagHandler` implements:

- `GET /health`: model, embedder, store, and table configuration.
- `POST /ask`: validates a query, retrieves chunks, optionally searches/logs
  chat memory, builds a prompt, asks Ollama, and returns answer/timing plus three
  context snippets.
- `POST /log`: validates text and records a chat message.

`_json()` writes UTF-8 JSON with explicit length. Default request logging is
suppressed. `main()` binds the standard-library `HTTPServer` to configurable
host/port and handles Ctrl-C. It is intentionally a simple synchronous local
service; the default bind address is `127.0.0.1` and there is no authentication
layer if the user chooses a public bind address.

### Shell entry points and existing design docs

`run_assistant.sh`, `run_chat.sh`, and `run_server.sh` change to the source
directory, require `RAG_CONFIG`, and replace themselves with the relevant Python
program. `run_opencode.sh` verifies OpenCode and config, then passes all
arguments through. `run_index.sh` installs requirements, prints important
config values, and performs projects/downloads dry runs before showing the real
commands. `verify_host.sh` checks config fields, Ollama/model reachability,
Python modules, OCR GPU availability, and store disk visibility.

The RAG directory's `README.md` is the operator guide and `DESIGN.md` explains
the Route A architecture, component boundaries, data flow, and deployment
choices.

## 10. Tests and continuous integration

### Repository smoke test

`tests/smoke.sh` syntax-checks the major Bash commands, verifies executable
bits, validates Waybar JSON, installs into a temporary home, asserts important
links, rolls back the latest transaction, and confirms the links disappeared.
`.github/workflows/check.yml` runs this test for every push and pull request on
Ubuntu.

### Python dashboard tests

- `tests/test_hardware.py`: readback, no accidental file creation, permission
  errors, grouped rollback, coupled-control final state, rollback failure, and
  preflight of missing controls.
- `tests/test_telemetry.py`: missing/reset counters, energy wrap, real rate
  units, RAPL package selection, independent NVML capabilities, and safe CPU
  temperature fallback.
- `tests/test_fan_backend.py`: protocol validation, curve ordering, write
  readback, exact subprocess construction, missing service, and timeout cleanup.
- `tests/test_dbus_integration.py`: runs the real daemon on an isolated session
  bus and temporary fake sysfs/EC file, testing protocol reads/writes,
  capabilities, allowlists, rollback, reconnect, fixed Cyborg registers, raw-EC
  identity checks, and read-only curves.
- `tests/test_tui.py`: drives the Textual app headlessly to verify failure does
  not alter UI/settings, successful persistence reflects actual hardware,
  preset rollback, disabled controls, keyboard navigation, backend-only failure
  semantics, reconnect limitations, startup restoration, and responsive layout.

### C++ core test

`msi-ec-daemon/tests/core_test.cpp` defines an in-memory `FakeEC`. It verifies
that unverified firmware cannot read/write curves, matching is exact, invalid
curves cause no writes, partial curve/mode failures roll back, persistent
failures are visible, the Cyborg write range and fixed temperatures are
respected, and fake sysfs transactions reject path traversal and missing
attributes.

## 11. Complete tracked-file map

The sections above explain every executable/source/config path. The remaining
tracked files are documentation, metadata, or assets:

| Path | Role |
|---|---|
| `README.md` | User-facing overview, install, and operation guide. |
| `CODE_WALKTHROUGH.md` | Implementation guide you are reading. |
| `LICENSE` | Apache License 2.0 for the repository. |
| `.gitignore` | Ignores editor/AL artifacts plus Python bytecode and logs. |
| `.github/workflows/check.yml` | CI entry point for the smoke test. |
| `.local/share/underlight/give_laptop_ac/README.md` | Dashboard usage/setup guide. |
| `.local/share/underlight/give_laptop_ac/CHANGELOG.md` | Dashboard version history. |
| `.local/share/underlight/give_laptop_ac/requirements.txt` | Textual, psutil, NVML, Pydantic, and YAML dependencies. |
| `.local/share/underlight/give_laptop_ac/msi-ec-daemon/README.md` | Backend build, security, API, CLI, and test guide. |
| `.local/share/underlight/give_laptop_ac/msi-ec-daemon/docs/cyborg-fan-layout.md` | Firmware-specific register evidence and safety rules. |
| `.local/share/underlight/rag_pipeline/README.md` | RAG installation and command guide. |
| `.local/share/underlight/rag_pipeline/DESIGN.md` | RAG architecture and design rationale. |

No runtime secrets, model weights, vector indexes, chat logs, screenshots,
clipboard entries, virtual environments, or hardware state are intended to be
tracked by this repository.
