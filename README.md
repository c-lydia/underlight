# Underlight

Personal Hyprland desktop configuration for Ubuntu. The repository mirrors the
paths below the home directory so the files can be restored with symbolic
links.

## Included

- Hyprland entry point and modular `underlight/` configuration
- Waybar configuration and styling
- Desktop widget program and CSS
- Underlight launcher, clipboard, power, screenshot, sensor, and window helpers

## Components and architecture

Underlight is a configuration and orchestration layer around Hyprland, not a
single long-running application. Hyprland is the composition root: it loads the
modular desktop configuration, starts the visible shell processes, and routes
key bindings to small helper programs.

```text
Hyprland session
├── ~/.config/hypr/hyprland.conf
│   └── underlight/*.conf
│       ├── session environment, monitors, input, and appearance
│       ├── window and workspace rules
│       ├── keyboard and mouse bindings ───────┐
│       └── autostart                          │
├── Waybar                                    │
│   ├── native workspace/system modules       │
│   └── Underlight sensor/window helpers      │
├── GTK desktop widgets                       │
│   ├── clock and calendar                    │
│   ├── media status and controls             │
│   ├── CPU, memory, disk, and battery meters │
│   └── removable-drive controls              │
└── user actions ◄────────────────────────────┘
    ├── Wofi launcher, clipboard, and power menus
    ├── screenshot capture
    └── transient systemd user services
```

### Configuration layer

`~/.config/hypr/hyprland.conf` is the entry point. It sources the files in
`~/.config/hypr/underlight/`, separating colors, environment variables,
monitors, input, appearance, autostart, background applications, bindings, and
window rules. `autostart.conf` launches Hyprpaper, Waybar, the widget process,
Hypridle, and optional notification, network, and clipboard services.

### Shell and status layer

Waybar is the always-visible shell surface. Its native modules show workspaces,
network, CPU, memory, audio, battery, clock, and tray state. Custom modules call
`underlight-window-mode` and `underlight-sensor` to read Hyprland, GPU, and fan
state. Waybar buttons and Hyprland key bindings invoke the same helper scripts,
so mouse and keyboard workflows share one implementation.

### Widget layer

`underlight-widgets` is one Python/GTK 3 process that owns four layer-shell
windows: date/calendar, media, system meters, and removable drives. The windows
sit above the wallpaper but below normal application windows and are styled by
`~/.config/underlight/widgets.css`. The process reads:

- `psutil` for CPU, memory, storage, battery, and uptime
- MPRIS over the D-Bus session bus for media metadata and playback control
- `lsblk` for removable volumes, with `udisksctl` and Nautilus for mount/open
  actions

`underlight-widgets-toggle` starts, stops, or restarts the single widget
instance through Hyprland.

### Helper layer

Programs in `~/.local/bin/underlight-*` are deliberately small adapters around
standard Wayland/Linux tools:

- `underlight-menu`, `underlight-clipboard`, and `underlight-power` present Wofi
  menus for applications, clipboard history, and session actions.
- `underlight-shot` captures a screen or selected area, saves it under
  `~/Pictures/Screenshots`, and copies it to the Wayland clipboard when
  available.
- `underlight-sensor` and `underlight-window-mode` emit JSON consumed by
  Waybar.
- `underlight-background` launches arbitrary commands as collected transient
  systemd user services, keeping them independent of the calling terminal.
- `underlight-install-extras` installs the optional Ubuntu utilities used by
  the integrations.

### Installation model

The repository mirrors paths below the home directory. `install.sh` creates
symbolic links from those live paths into the repository, moving any replaced
files into a timestamped state-directory backup first. Runtime state stays
outside the repository; the notable persistent state is clipboard history,
which is maintained by `cliphist`.

## Install

Clone the repository and run:

```bash
./install.sh
```

Existing files are moved to a timestamped directory below
`~/.local/state/underlight-dotfiles-backup-*` before links are created.

The widget requires GTK 3, `gtk-layer-shell`, PyGObject, and Python `psutil`.
Optional desktop utilities can be installed on Ubuntu with:

```bash
~/.local/bin/underlight-install-extras
```

Log out and back into Hyprland after the initial installation, or restart the
widgets with:

```bash
~/.local/bin/underlight-widgets-toggle restart
```

## Background applications

Launch any command independently from the terminal with:

```bash
underlight-background COMMAND [ARGUMENT ...]
```

To start applications automatically at login, add `exec-once` entries to
`~/.config/hypr/underlight/background-apps.conf`.
