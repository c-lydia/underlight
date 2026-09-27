# Underlight

Personal Hyprland desktop configuration for Ubuntu and EndeavourOS. The
repository mirrors paths below the home directory so the files can be restored
with symbolic links.

For an implementation-level tour of every configuration, executable, Python
module, C++ component, data file, and test, see
[CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md).

## Included

- Hyprland entry point and modular `underlight/` configuration
- Kitty, Waybar, Wofi, Mako, and desktop-widget styling with compositor blur
- A full Neovim workbench bootstrap plus an Underlight transparency overlay
- Desktop widget program and CSS
- Underlight launcher, clipboard, power, screenshot, sensor, and window helpers
- Hybrid Intel/NVIDIA PRIME offload and GPU readiness helpers
- Ollama, OpenCode, and Hermes launch/status integration
- Opt-in AC, battery, and AI performance profiles
- A bundled, transparent `give_laptop_ac` dashboard and optional RAG pipeline
- Persistent five-shell ROS 2/SSH workspaces with client keepalives
- A hardware-safe 2.4 GHz NetworkManager phone-hotspot workflow

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
so mouse and keyboard workflows share one implementation. `Super+X` opens a
keyboard-first system-actions menu containing every control exposed by the bar.
Waybar uses left click for primary actions and right click for advanced actions.
Use `Super+Tab`/`Super+Shift+Tab` to cycle desktops, or `Super+1…0` to jump
directly to one.

### Keyboard controls

Every Waybar function is available without a mouse. `Super+X` opens the
keyboard-driven system-actions menu; type to filter it, use the arrow keys to
select an action, and press Enter. It contains applications, Wi-Fi, desktop
widgets, the audio mixer, power profiles, the laptop dashboard, GPU tools,
system diagnostics, and session/power actions.

| Keys | Action |
| --- | --- |
| `Super+X` | Open all system actions |
| `Super+Space` or `Super+R` | Open the application launcher |
| `Super+Tab` | Move to the next active desktop |
| `Super+Shift+Tab` | Move to the previous active desktop |
| `Super+1…0` | Jump directly to desktop 1–10 |
| `Super+Shift+1…0` | Move the active window to desktop 1–10 |
| `Super+M` | Open session and power actions |
| `Super+Shift+V` | Open clipboard history |
| `Super+Shift+A` | Open the laptop dashboard |
| `Super+Shift+G` | Open GPU and compute actions |
| `Super+Shift+I` | Open AI tools |

Waybar remains fully interactive for mouse use. Left click always performs a
module's primary action, right click opens its advanced action or settings, and
scroll adjusts values such as volume or cycles workspaces. Tooltips show the
available actions for each module.

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

- `underlight-menu`, `underlight-control`, `underlight-network`,
  `underlight-clipboard`, and
  `underlight-power` present Wofi menus for applications, Wi-Fi connections,
  clipboard history, and session actions. The Wi-Fi menu uses NetworkManager
  directly, can create a 2.4 GHz NAT hotspot on an available Wi-Fi radio, and
  works the same way on Ubuntu and EndeavourOS.
- `underlight-shot` captures a screen or selected area, saves it under
  `~/Pictures/Screenshots`, and copies it to the Wayland clipboard when
  available.
- `underlight-sensor` and `underlight-window-mode` emit JSON consumed by
  Waybar.
- `underlight-background` launches arbitrary commands as collected transient
  systemd user services, keeping them independent of the calling terminal.
- `underlight-gpu-run` runs one demanding application on the discrete GPU while
  Hyprland and ordinary applications remain on the power-efficient iGPU.
- `underlight-gpu-check` reports DRM modesetting, render nodes, NVIDIA telemetry,
  and switcheroo-control discovery without changing the machine.
- `underlight-doctor` checks the desktop, NVIDIA/PRIME, Ollama, OpenCode,
  Hermes, Neovim, ROS 2, and laptop-dashboard integration. It distinguishes a
  restricted sandbox from a host driver failure.
- `underlight-ai` opens the existing Ollama, OpenCode, and Hermes setup without
  rewriting model, provider, or credential files.
- `underlight-profile` provides manual `ai`, `performance`, `balanced`,
  `battery`, and AC-aware `auto` power profiles. Nothing changes at login.
- `underlight-gpu-menu` is the shared Wofi entry point for GPU applications,
  AI tools, diagnostics, profiles, and the laptop dashboard.
- `underlight-health-notify` reports a real host NVIDIA failure after login,
  while staying quiet when the driver is healthy or device nodes are hidden.
- `underlight-laptop` prefers a working copy at `~/projects/give_laptop_ac` and
  otherwise opens the bundled copy. Press `Super+Shift+A` to launch it.
- `underlight-rag` exposes the optional local RAG indexer, assistant, chat
  tracker, and HTTP server without storing indexes or models in this repo.
- `underlight-install-extras` installs the optional Ubuntu utilities used by
  the integrations. `install-endeavouros.sh` bootstraps a complete Hyprland
  session from the official Arch repositories before linking the same config.
- `ros2-workspace` opens five ROS-aware GNU Screen shells that survive a
  Neovim exit, terminal closure, or SSH client detachment.

### Installation model

The repository mirrors paths below the home directory. `install.sh` creates
symbolic links from those live paths into the repository, moving any replaced
files into a timestamped state-directory backup first. Runtime state stays
outside the repository; the notable persistent state is clipboard history,
which is maintained by `cliphist`.

## Install on Ubuntu

Clone the repository and run:

```bash
git clone https://github.com/c-lydia/underlight.git
cd underlight
./install.sh
```

The installer also installs Neovim through `apt` when it is missing, clones the
full workbench configuration to `~/.local/share/underlight/neovim_config`, and
links it as `~/.config/nvim`. An existing Neovim configuration is preserved;
only the Underlight overlays are added to it. GNU Screen is installed when
needed. The workbench requires Neovim 0.11.3 or newer. To keep an existing
editor setup without downloading the workbench, run
`UNDERLIGHT_SKIP_NEOVIM=1 ./install.sh`.

Underlight installs SSH keepalives in `~/.ssh/config.d/underlight.conf`. On a
new SSH setup it also links a main config that includes this directory. An
existing `~/.ssh/config` is never replaced; if it does not already contain
keepalives, add this line near its top:

```sshconfig
Include ~/.ssh/config.d/*
```

Existing files are moved to a timestamped directory below
`~/.local/state/underlight-dotfiles-backup-*` before links are created.
Every installation also writes rollback metadata. Restore the latest install
transaction with:

```bash
./install.sh --restore latest
```

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

## Install on EndeavourOS

On a newly installed EndeavourOS system, install Git, clone the repository,
and run the EndeavourOS bootstrap as your normal user:

```bash
sudo pacman -S --needed git
git clone https://github.com/c-lydia/underlight.git
cd underlight
./install-endeavouros.sh
```

The default bootstrap installs Hyprland, the complete Neovim workbench, and the
bundled `give_laptop_ac` dashboard. It installs the same `Super+X` system menu
and desktop-navigation bindings documented above; no EndeavourOS-specific
keybinding step is required. AI and RAG remain opt-in:

```bash
./install-endeavouros.sh --with-ai   # adds Ollama and OpenCode; no models
./install-endeavouros.sh --with-rag  # adds AI plus the isolated RAG environment
```

`--with-rag` creates `~/.config/underlight/rag.yaml`; review its source paths
before indexing. It does not download a model or build an index. The bootstrap
uses official Arch packages, then runs the same safe `install.sh` used on
Ubuntu. It does not replace or remove Ubuntu support. Existing dotfiles are
backed up under `~/.local/state/underlight-dotfiles-backup-*`.

When it finishes, log out. Select **Hyprland** from the session chooser on the
login screen and log back in. On a TTY-only setup, start it with:

```bash
start-hyprland
```

Hyprland starts Waybar, Mako, Hyprpaper, and the widgets automatically. To load
widget CSS or logo changes without logging out, run:

```bash
~/.local/bin/underlight-widgets-toggle restart
```

To reload the rest of the Hyprland configuration in an existing session and
check the installed commands:

```bash
hyprctl reload
underlight-doctor
```

Every Waybar section is interactive on both supported distributions. Click the
network section to scan, connect, disconnect, or toggle Wi-Fi; right-click it
for NetworkManager's advanced connection editor. Click the clock, CPU, or RAM
section for the desktop widgets, the fan section for laptop controls, and the
battery section for power profiles. Right-click audio for the volume mixer.

NVIDIA drivers are deliberately not installed by the bootstrap because the
correct package depends on the GPU and kernel. Install the driver through
EndeavourOS first; Underlight's PRIME helpers will detect it afterward.

## Hybrid GPU

The desktop compositor stays on the integrated Intel GPU by default. Run a
game, renderer, CUDA UI, or other graphics-heavy application on NVIDIA with:

```bash
underlight-gpu-run COMMAND [ARGUMENT ...]
```

The helper prefers `switcherooctl` and falls back to NVIDIA's PRIME render
offload variables. Check the driver, DRM modesetting, render nodes, and PRIME
discovery with `underlight-gpu-check`, or check the whole workstation with
`underlight-doctor`. The optional extras installer installs
`switcheroo-control`; NVIDIA's driver itself remains managed by the host distro.

The Waybar GPU pill reports sleeping, idle, or active state with temperature,
power, VRAM, and compute-process details. Left-click opens the GPU/compute menu,
middle-click opens `give_laptop_ac`, and right-click opens GPU diagnostics. Use
`Super+Shift+G` for the GPU menu and `Super+Shift+I` for the AI menu.

## Local AI stack

Underlight preserves the existing Ollama, OpenCode, and Hermes configuration.
AI is optional on EndeavourOS; enable it with `--with-ai` or `--with-rag`.
Underlight only supplies desktop entry points around it:

```bash
underlight-ai menu
underlight-ai status
underlight-ai opencode ~/projects/example
underlight-ai hermes ~/projects/example
underlight-ai ollama MODEL
```

Selecting an interactive AI workload applies the opt-in performance profile;
`underlight-profile balanced` returns to the normal balanced profile. Use
`underlight-profile auto` to choose performance on AC and power-saver on
battery for the current session.

The Neovim workbench exposes the same path through `:GpuRun`, `:GpuInfo`,
`:LaptopControl`, `:AI`, `:OpenCode`, `:Hermes`, `:OllamaInfo`,
`:PowerProfile`, and `:UnderlightDoctor`. Its `nvim-workspace` launcher
automatically uses kitty under Hyprland.

## Persistent ROS 2 and SSH shells

The workspace provides five named GNU Screen shells. Screen runs independently
of Neovim, so closing or crashing the editor detaches the display without
stopping the shells, ROS 2 commands, or SSH clients inside them.

### Open or recover the workspace

From normal mode in Neovim, press `Space t w` (`<leader>tw`). The default leader
is Space. The same workspace can be opened without Neovim:

```bash
ros2-workspace
```

The first launch creates `ros2-1` through `ros2-5`. Later launches reattach to
those same shells. Each shell automatically sources the first
`/opt/ros/*/setup.bash` it finds. If ROS 2 is installed only on another machine,
the local shell remains usable and prints a reminder to SSH to that machine.

### Move between shells

Screen commands begin with `Ctrl-a`. Press and release `Ctrl-a`, then press the
second key:

| Keys | Action |
| --- | --- |
| `Ctrl-a n` | Move to the next shell |
| `Ctrl-a p` | Move to the previous shell |
| `Ctrl-a 0` … `Ctrl-a 4` | Jump directly to `ros2-1` … `ros2-5` |
| `Ctrl-a d` | Detach while leaving every shell running |

For example, the five shells can hold separate ROS 2 nodes and tools:

```text
ros2-1: ssh robot.local          # robot shell / launch file
ros2-2: ssh robot.local          # second node
ros2-3: ssh robot.local          # topic and service inspection
ros2-4: ssh sensor-node.local    # hardware-side logs
ros2-5: local build or ros2 bag
```

After a Neovim or terminal failure, reopen Neovim and press `Space t w`, or run
`ros2-workspace` in any terminal. Do not start a new set of SSH sessions—the
existing ones should reappear.

The defaults can be changed for one launch:

```bash
ROS2_SCREEN_SHELLS=8 ros2-workspace
ROS2_SCREEN_SESSION=my-robot ros2-workspace
```

The shell count may be 1–20. Increasing it backfills missing named windows in
an existing session.

### SSH persistence levels

Underlight configures `ServerAliveInterval 30` and `ServerAliveCountMax 6`, so
an SSH client waits through approximately three minutes of missed replies. The
local Screen workspace also protects the client when Neovim disappears.

Neither mechanism can preserve the remote process after a complete or extended
network disconnection. For that, start a multiplexer after connecting to the
remote machine:

```bash
ssh robot.local
screen -xRR ros2
```

If the remote machine uses tmux instead:

```bash
ssh robot.local
tmux new -As ros2
```

Detach the remote Screen session with `Ctrl-a d`, or detach tmux with
`Ctrl-b d`, before closing SSH when possible.

On a pre-existing SSH configuration, ensure this line is present near the top
of `~/.ssh/config` unless keepalives are already configured there:

```sshconfig
Include ~/.ssh/config.d/*
```

## 2.4 GHz phone hotspot

This feature creates a WPA-protected 2.4 GHz access point for phones such as the
Galaxy A20. NetworkManager supplies DHCP, IPv4 forwarding, connection tracking,
and NAT through its `ipv4.method=shared` mode. The profile does not autoconnect.

### Requirements

The laptop must have an available Wi-Fi radio for the hotspot. These layouts
work:

| Upstream connection | Hotspot radio | Result |
| --- | --- | --- |
| Ethernet or USB tether | Laptop Wi-Fi | Supported |
| Built-in Wi-Fi | Second USB Wi-Fi adapter | Supported |
| Built-in 5 GHz Wi-Fi | Same built-in radio at 2.4 GHz | Not supported on a one-channel radio |

Underlight deliberately refuses to disconnect or repurpose the only active
Wi-Fi uplink. On the current single-radio laptop, the last layout therefore
produces an explanatory error instead of dropping the network. Wi-Fi Direct is
not presented as a normal hotspot and is not used by this command.

If the command prints the following, it made no network changes and did not
create a hotspot profile:

```text
underlight-network: refusing to disconnect the only active Wi-Fi uplink.
A 5 GHz client plus a 2.4 GHz AP requires another Wi-Fi adapter or a non-Wi-Fi uplink.
```

Connect the laptop upstream through Ethernet or USB tethering and retry, or
attach a second Wi-Fi adapter. There is no configuration toggle that makes a
single one-channel radio operate as a 5 GHz client and a normal 2.4 GHz access
point simultaneously.

### Start the hotspot

1. Connect the upstream through Ethernet/USB, or connect a second Wi-Fi adapter.
2. Click the Waybar network section, or open `Super+X` and select Wi-Fi.
3. Select **Start 2.4 GHz phone hotspot**.
4. Enter the network name and a password containing 8–63 characters.
5. On the phone, open Wi-Fi settings and join the new network.

The equivalent terminal command is:

```bash
underlight-network hotspot-start
```

The default suggested SSID is `Underlight-Phone`. The password is passed to
NetworkManager through standard input rather than exposed in the command line.

### Stop the hotspot

Select **Stop 2.4 GHz phone hotspot** from the same network menu, or run:

```bash
underlight-network hotspot-stop
```

### UDP and ROS 2 behavior

For custom unicast UDP, configure the phone application to send to the upstream
device's IP address and UDP port. The laptop translates the outbound packet;
replies belonging to that flow return through NetworkManager's connection
tracking. The upstream device cannot initiate a new connection directly to the
phone's private hotspot address without explicit forwarding.

ROS 2 DDS discovery usually relies on multicast, which ordinary NAT does not
forward between the hotspot and upstream network. Use a ROS 2 Discovery Server,
explicit/static peers, or a routing bridge such as Zenoh when ROS nodes must
discover one another across these subnets.

When the optional RAG component is installed, review its config and start with
a dry run:

```bash
underlight-rag index --table projects --dry-run
underlight-rag ask "summarize this project"
```

## Background applications

Launch any command independently from the terminal with:

```bash
underlight-background COMMAND [ARGUMENT ...]
```

To start applications automatically at login, add `exec-once` entries to
`~/.config/hypr/underlight/background-apps.conf`.
