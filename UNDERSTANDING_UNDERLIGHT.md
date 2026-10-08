# Understanding Underlight

This guide explains Underlight as one system. It is written for someone who
wants to operate it, troubleshoot it, and confidently change it without first
reading every source file.

For installation commands, use [README.md](README.md). For a file-by-file
implementation reference, use [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md).

## 1. What Underlight is

Underlight is a version-controlled Linux desktop configuration built around
Hyprland. It is not one large application or daemon. It is a collection of
configuration files and small programs that cooperate:

```text
Underlight repository
  │
  ├─ install.sh creates links into your home directory
  │
  └─ Hyprland starts the desktop session
       ├─ Waybar shows status and launches actions
       ├─ Wofi displays menus
       ├─ Mako displays notifications
       ├─ GTK displays desktop widgets
       └─ underlight-* commands perform focused tasks
            ├─ Wi-Fi and the phone hotspot
            ├─ screenshots and clipboard history
            ├─ GPU and power-profile selection
            ├─ laptop monitoring and fan control
            ├─ local AI and RAG launchers
            └─ Neovim, ROS 2, and SSH workspaces
```

The repository contains the desired configuration. Programs still store their
changing runtime data outside the repository. This separation makes the setup
repeatable without committing passwords, chat history, vector indexes, or
machine state.

## 2. The three layers to remember

Nearly every Underlight feature can be understood as one of three layers.

### Configuration

Files below `.config/` describe appearance, input, startup, window rules,
Waybar, Wofi, Kitty, Mako, and the Underlight widgets. Hyprland reads these
files directly through links installed below `~/.config`.

### Commands

Files below `.local/bin/` are executable helpers. A key binding, Waybar click,
or Wofi choice usually ends by running one of these commands. They are small on
purpose: NetworkManager owns networking, `systemd-run` owns background process
lifetime, and `powerprofilesctl` owns the machine power profile.

### Optional subsystems

The laptop dashboard, privileged MSI EC fan backend, and local RAG pipeline
are larger components below `.local/share/underlight/`. Underlight launches and
integrates them, but each subsystem has its own README and tests.

## 3. What happens from installation to login

### Installation

`install.sh` creates symbolic links from normal home-directory locations into
this repository. For example:

```text
~/.local/bin/underlight-network
  -> <repository>/.local/bin/underlight-network
```

This means editing the repository changes the installed command immediately.
There is no copy to keep synchronized.

Before replacing an existing path, the installer moves it into a timestamped
directory below `${XDG_STATE_HOME:-~/.local/state}`. It also records every link
created during the transaction. Restore is therefore targeted rather than a
blanket deletion:

```bash
./install.sh --restore latest
```

The Ubuntu installer links the configuration and can bootstrap the companion
Neovim workbench. `install-endeavouros.sh` additionally installs the Arch-side
desktop packages and can prepare the optional AI/RAG environments.

### Login

Hyprland opens `.config/hypr/hyprland.conf`, which sources the modular files in
this order:

1. `colors.conf` defines shared colors.
2. `environment.conf` exports Wayland and toolkit settings.
3. `gpu.conf` establishes the hybrid-GPU policy.
4. `monitors.conf` and `input.conf` define hardware-facing behavior.
5. `looknfeel.conf` defines layout, opacity, blur, and animation.
6. `autostart.conf` launches session services.
7. `background-apps.conf` supplies a personal startup extension point.
8. `bindings.conf` maps input to actions.
9. `rules.conf` controls application/window behavior.

`autostart.conf` launches Waybar, the GTK widget process, Hyprpaper, Hypridle,
Mako when installed, NetworkManager's tray applet, clipboard watchers, and a
delayed GPU health notification.

## 4. How an action travels through the system

There are usually several ways to reach the same command:

```text
keyboard binding ─┐
Waybar click ─────┼─> underlight-* helper ─> standard Linux service/tool
Wofi menu ────────┘
```

For example, selecting **Wi-Fi** from `Super+X` runs
`underlight-control`, which runs `underlight-network`, which calls `nmcli`.
Underlight does not implement a network stack; it provides a safe user
interface around NetworkManager.

The main keyboard entry points are:

| Keys | Result |
| --- | --- |
| `Super+X` | All system actions |
| `Super+Space` or `Super+R` | Application launcher |
| `Super+M` | Session and power menu |
| `Super+Shift+V` | Clipboard history |
| `Super+Shift+A` | Laptop dashboard |
| `Super+Shift+G` | GPU and compute menu |
| `Super+Shift+I` | AI menu |
| `Super+N` | Move the active window to/from the minimized shelf |
| `Super+Shift+N` | Show the minimized shelf |
| `Print` | Full-screen screenshot |
| `Super+Shift+S` | Area screenshot |

Window focus, movement, and resizing support arrow keys and Vim-style
H/J/K/L keys. `Super+Tab` and `Super+Shift+Tab` cycle active workspaces.

## 5. The visible desktop

### Hyprland

Hyprland is the composition root. It owns monitors, workspaces, window layout,
key bindings, and session startup. Underlight keeps its configuration modular
so a monitor change does not require editing the same file as a key binding.

### Waybar

Waybar is both a status display and a control surface. Native modules display
workspaces, network, CPU, memory, audio, battery, clock, and tray state.
Underlight helpers add window-mode, GPU, and fan information. Mouse actions and
the `Super+X` menu call the same helpers.

### Wofi

Wofi supplies application and action menus. Most helpers treat cancel as a
normal no-op. Password prompts for Wi-Fi and the hotspot use a password field;
the scripts pass secrets through standard input instead of command arguments.

### Desktop widgets

`underlight-widgets` is one Python/GTK 3 process that owns the calendar, media,
system-meter, and removable-drive windows. One process gives them consistent
stacking and a shared refresh loop. `underlight-widgets-toggle` starts, stops,
or restarts this process.

### Kitty, Mako, and styling

Kitty provides the terminal, Mako provides notifications, and CSS files style
Waybar, Wofi, and widgets. The color and transparency choices are presentation;
they do not own application state.

## 6. Helper command map

These commands are the best starting points when tracing behavior:

| Command | Responsibility |
| --- | --- |
| `underlight-control` | Top-level system-actions menu |
| `underlight-menu` | Application launcher |
| `underlight-network` | Wi-Fi selection and optional 2.4 GHz hotspot |
| `underlight-power` | Lock, logout, suspend, reboot, and shutdown menu |
| `underlight-clipboard` | Decode a `cliphist` item back to the clipboard |
| `underlight-shot` | Capture and copy a screenshot |
| `underlight-minimize` | Move a window to/from a special hidden workspace |
| `underlight-background` | Run a command as a transient user service |
| `underlight-window-mode` | Emit Waybar JSON for tiled/floating state |
| `underlight-sensor` | Emit Waybar JSON for GPU or fan state |
| `underlight-doctor` | Read-only integration diagnostics |
| `underlight-health-notify` | Quiet login-time NVIDIA health warning |
| `underlight-profile` | Select a power profile, optionally for one command |
| `underlight-gpu-run` | Launch one program on the discrete GPU |
| `underlight-gpu-menu` | GPU, compute, AI, profile, and diagnostic menu |
| `underlight-ai` | Launch/status wrapper for Ollama, OpenCode, and Hermes |
| `underlight-laptop` | Launch the laptop dashboard |
| `underlight-rag` | Launch the optional indexer, assistant, chat, or server |
| `nvim-workspace` | Remember/open a project-centered development layout |
| `ros2-workspace` | Create or reattach a persistent five-shell Screen session |

Use `underlight-doctor` when the desktop mostly works but an integration does
not. It reports hard failures separately from optional missing components and
recognizes when a sandbox simply cannot see host GPU devices.

## 7. Phone hotspot, routing, and NAT

This is the most important network mental model:

```text
                                         5 GHz network
phone                                    ┌────────────────────┐
2.4 GHz Wi-Fi                            │ another device      │
┌──────────────┐      laptop             │ UDP port 55555      │
│ app          │      ┌──────────────┐   └─────────▲──────────┘
│ sends UDP    ├─────>│ TP-Link USB  │             │
│ to :55555    │      │ 2.4 GHz AP   │             │
└──────────────┘      │      NAT     ├─────────────┘
                      │ built-in 5G  │
                      └──────────────┘
```

The built-in Wi-Fi remains a 5 GHz client. The TP-Link USB Wi-Fi adapter is the
separate radio used for the 2.4 GHz access point. A typical single radio cannot
remain a 5 GHz client while also serving a normal 2.4 GHz access point, so
`underlight-network` refuses to disconnect or repurpose the only active Wi-Fi
uplink.

### What the script configures

`underlight-network hotspot-start`:

1. Finds a disconnected Wi-Fi adapter.
2. Asks for an SSID and an 8–63 character WPA password.
3. Creates or updates the `Underlight Phone Hotspot` NetworkManager profile.
4. Forces 2.4 GHz AP mode with `802-11-wireless.band=bg`.
5. Sets `ipv4.method=shared` and disables IPv6 for that profile.
6. Starts the profile without enabling automatic connection at boot.

NetworkManager's shared mode provides DHCP, DNS forwarding, IPv4 forwarding,
connection tracking, and masquerading/NAT. Underlight does not directly write
`iptables` or `nftables` rules.

### Where UDP port 55555 belongs

NAT itself does **not** use port `55555`, and Underlight does not hardcode a
NAT port. Shared mode translates outbound flows for all protocols and ports.

Port `55555` belongs to your application:

- The phone sends a unicast UDP packet to the 5 GHz device's IP address and
  destination port `55555`.
- The receiving application listens on UDP port `55555`.
- The receiving device's firewall must allow UDP `55555` from the applicable
  network.
- A reply associated with that flow returns through the laptop's connection
  tracking and is translated back to the phone.

You can check for a listener on the receiving Linux device with:

```bash
ss -lunp | grep ':55555'
```

If the phone is talking to the laptop itself, use the laptop's hotspot-side
gateway address as the destination. Discover it instead of assuming an address:

```bash
nmcli -t -f DEVICE,TYPE,STATE device
ip -4 address
```

### What NAT does not provide

A device on the 5 GHz network cannot normally initiate a new connection to the
phone's private hotspot address. That would require an explicit destination
NAT/port-forward rule, a routed design, or an application-level relay.

Ordinary NAT also does not relay multicast discovery between the two subnets.
Standard ROS 2 DDS discovery often uses multicast and additional dynamically
derived UDP ports. Your application's custom UDP `55555` flow can work while
automatic ROS 2 peer discovery still does not. For ROS 2 across these subnets,
use explicit/static peers, a ROS 2 Discovery Server, or a bridge such as Zenoh.

### Useful hotspot checks

```bash
# Show radios and whether the TP-Link adapter is available.
nmcli -t -f DEVICE,TYPE,STATE device

# Show the active uplink and hotspot profiles.
nmcli connection show --active

# Start or stop without opening the menu.
underlight-network hotspot-start
underlight-network hotspot-stop

# Inspect IPv4 addresses and routes.
ip -4 address
ip -4 route
```

Do not place a hotspot password in this repository. NetworkManager stores the
secret in its protected system connection profile.

## 8. GPU, power, and AI

Underlight keeps the desktop on the efficient GPU and offloads individual
programs when requested. `underlight-gpu-run` tries `switcherooctl` first,
then NVIDIA PRIME environment variables, and finally Mesa's `DRI_PRIME=1`.
It does not globally force every application onto the discrete GPU.

`underlight-profile` changes the system power profile only when explicitly
called. Its `auto` mode chooses an AC-aware profile. Performance/AI mode can
also run one trailing command through the discrete-GPU launcher.

`underlight-ai` is orchestration, not an AI provider. It discovers and launches
Ollama, OpenCode, and Hermes using their existing configuration. Whether data
stays local depends on the selected tool and provider: Ollama is intended for
local models, while OpenCode or Hermes may use remote services if configured
that way.

## 9. Neovim, project workspaces, ROS 2, and SSH

The full Neovim workbench lives in a companion checkout. Underlight installs
three overlays into it:

- transparency that survives colorscheme changes;
- persistent ROS 2 workspace commands;
- optional RAG commands.

`nvim-workspace` stores the selected project below
`${XDG_STATE_HOME:-~/.local/state}/nvim-workspace` and can launch a development
layout containing Neovim, a terminal, Codex or a shell fallback, and Firefox.

`ros2-workspace` creates a detached GNU Screen session with five named shells.
The session survives closing Neovim, Kitty, or the SSH client. SSH keepalive
settings detect broken connections sooner, but they do not keep a remote shell
alive by themselves; Screen or tmux provides that persistence on the remote
machine.

## 10. Laptop dashboard and privileged fan control

`give_laptop_ac` is the Textual dashboard for telemetry, controls, and process
views. It prefers a development checkout at `~/projects/give_laptop_ac` and
falls back to the bundled copy.

The UI is unprivileged. Fan/EC operations cross a narrow D-Bus boundary to
`msi-ec-daemon`. The daemon validates the machine identity, protocol, allowed
operations, fan-curve ordering, and readback. Its core logic supports rollback
when a multi-step write fails. This is intentionally safer than granting a UI
arbitrary root file access.

Hardware control is machine-specific. Read the dashboard and daemon READMEs
before enabling writes on a new laptop model:

- `.local/share/underlight/give_laptop_ac/README.md`
- `.local/share/underlight/give_laptop_ac/msi-ec-daemon/README.md`

## 11. Optional local RAG

The RAG pipeline can index configured code, documents, PDFs, images, and other
text-like data into LanceDB. It combines retrieved chunks with a question and
can call an Ollama model to produce an answer. It also has chat tracking, an
HTTP server, and OpenCode integration.

The source is installed only when RAG is requested. Configuration, virtual
environments, vector data, and chat history live outside the repository. The
important rule is that “local RAG” describes the bundled storage/retrieval
path; a configured external model provider can still send prompts elsewhere.

Start with:

- `.local/share/underlight/rag_pipeline/README.md` for operation;
- `.local/share/underlight/rag_pipeline/DESIGN.md` for architecture.

## 12. State, secrets, and privilege boundaries

Underlight deliberately separates source from changing or sensitive data:

| Data | Typical owner/location |
| --- | --- |
| Installed configuration | Symlinks from `$HOME` into this repository |
| Install backups | `${XDG_STATE_HOME:-~/.local/state}/underlight-dotfiles-backup-*` |
| Selected Neovim project | `${XDG_STATE_HOME:-~/.local/state}/nvim-workspace` |
| Screen sockets | `${XDG_STATE_HOME:-~/.local/state}/screen` |
| Hotspot password | Protected NetworkManager connection profile |
| RAG config/data/chat | XDG config/data locations outside the repository |
| Screenshots | `~/Pictures/Screenshots` |
| Clipboard history | `cliphist` runtime storage |

The repository should not contain Wi-Fi passwords, API tokens, model weights,
chat logs, vector indexes, screenshots, or raw hardware credentials.

Most helpers are unprivileged. System power actions use system services,
NetworkManager applies network configuration, and the fan controller uses its
restricted D-Bus service. Review any change that introduces `sudo`, broad file
writes, or a new privileged service boundary.

## 13. Where to make common changes

| Desired change | Start here |
| --- | --- |
| Key binding | `.config/hypr/underlight/bindings.conf` |
| Program launched at login | `.config/hypr/underlight/autostart.conf` or `background-apps.conf` |
| Monitor layout | `.config/hypr/underlight/monitors.conf` |
| Window rule | `.config/hypr/underlight/rules.conf` |
| Gaps, blur, opacity, animation | `.config/hypr/underlight/looknfeel.conf` |
| Waybar modules/clicks | `.config/waybar/config.jsonc` |
| Waybar appearance | `.config/waybar/style.css` |
| System-actions menu | `.local/bin/underlight-control` |
| Wi-Fi or hotspot behavior | `.local/bin/underlight-network` |
| Desktop widgets | `.local/bin/underlight-widgets` and `.config/underlight/widgets.css` |
| GPU launch policy | `.local/bin/underlight-gpu-run` |
| Power policy | `.local/bin/underlight-profile` |
| AI launch behavior | `.local/bin/underlight-ai` |
| Installation links | `install.sh` and `tests/smoke.sh` |

Because installed paths are symlinks, edit the repository copy. Do not replace
the live symlink with an unrelated file unless you intentionally want to stop
tracking that path.

## 14. Safe change and test workflow

For a normal change:

1. Check `git status` so you do not overwrite unrelated work.
2. Edit the smallest responsible file.
3. Run the repository smoke test:

   ```bash
   bash tests/smoke.sh
   ```

4. Reload only the affected component. Examples:

   ```bash
   hyprctl reload
   pkill -SIGUSR2 waybar
   underlight-widgets-toggle restart
   ```

5. Exercise the changed behavior manually.
6. Inspect the diff before committing.

The smoke test checks Bash syntax, executable bits, Waybar JSON, RAG unit tests,
a temporary installation, and rollback behavior. The laptop dashboard and EC
daemon have additional Python/C++ tests in their own directories.

Network changes deserve a recovery plan. Keep a local terminal open when
testing Wi-Fi, verify which device is the upstream before starting the hotspot,
and never assume that Wi-Fi interface names are identical across machines.

## 15. Troubleshooting by symptom

### A menu does not open

Run the underlying helper in a terminal. For example:

```bash
underlight-network
underlight-doctor
```

Terminal output usually reveals a missing program. Confirm that `~/.local/bin`
is on `PATH` and that the installed path is still a symlink into this repo.

### Waybar information is missing

Run the custom module directly, such as `underlight-sensor gpu`. Then check
Waybar's user-service logs. Missing NVIDIA device nodes inside a sandbox are
not the same as a broken host driver.

### The hotspot refuses to start

Run:

```bash
nmcli -t -f DEVICE,TYPE,STATE device
```

If the only Wi-Fi adapter is already the 5 GHz uplink, attach the TP-Link USB
adapter or use a non-Wi-Fi upstream. The refusal is a safety behavior, not a
password failure.

### The phone joins but UDP 55555 does not arrive

Do not decide that two devices share a subnet merely because both addresses
begin with `192.168`. That entire range is private address space, not one
subnet. Compare each address together with its CIDR prefix or subnet mask:

- `192.168.50.20/24` and `192.168.1.102/24` are on different subnets.
- `192.168.1.20/24` and `192.168.1.102/24` are on the same subnet.
- A NetworkManager shared hotspot commonly receives a separate range such as
  `10.42.0.0/24`, but discover the actual address instead of assuming it.

Inspect the laptop's interface addresses, routes, and route to the 5 GHz target:

```bash
ip -4 -brief address
ip -4 route
ip route get 192.168.1.102  # replace with the target's actual address
```

Check, in order:

1. The phone is sending to the 5 GHz target's actual IP, not the phone subnet's
   gateway unless the laptop itself is the target.
2. The receiver is listening on UDP `55555` and not only on loopback.
3. The receiver firewall allows UDP `55555`.
4. The laptop has both the hotspot and 5 GHz routes active.
5. The application uses unicast. Multicast ROS 2 discovery will not be fixed by
   opening only port `55555`.

To verify the path directly, capture only the application traffic while sending
a test packet:

```bash
sudo tcpdump -ni any udp port 55555
```

Packets entering through the TP-Link hotspot interface and leaving through the
5 GHz interface show that the phone is crossing subnets through the laptop.
With NetworkManager shared mode, the packet leaving toward the 5 GHz network
normally has the laptop's 5 GHz address as its translated source. A packet sent
to the laptop itself is delivered locally and does not need to leave through
the 5 GHz interface.

### A GPU application uses the wrong GPU

Launch it through `underlight-gpu-run`, then inspect `underlight-gpu-check` and
`underlight-doctor`. Avoid setting NVIDIA vendor variables globally unless the
entire session is intentionally changing GPUs.

### An installation replaced an old config

The old path should be in the timestamped Underlight backup under the XDG state
directory. Use `./install.sh --restore latest` only after checking which install
transaction is newest.

## 16. Recommended reading order

To learn the system without being overwhelmed:

1. Read sections 1–7 of this guide.
2. Use the desktop and run the helpers directly from a terminal.
3. Read the relevant section of `README.md` before installing an optional
   subsystem.
4. Follow `CODE_WALKTHROUGH.md` when changing implementation details.
5. Read a subsystem's own README before changing RAG or hardware-control code.

The shortest useful summary is: Hyprland connects user actions to small helper
commands; those helpers delegate to established Linux services; the repository
stores configuration while mutable state and secrets stay outside it.
