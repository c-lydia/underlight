# Underlight terminal network lab

The same `underlight-tui` runs on Ubuntu/Debian, EndeavourOS/Arch, and Arch Linux
ARM inside Termux. It uses Python's standard-library curses interface, with a
compact phone layout and a two-pane desktop layout at 100 columns or more.
Arrow keys or j/k select tools, Enter runs them, b returns from results, and q
quits. Page Up/Down scroll results. Resize the terminal at any time. Use a
terminal of at least 28 columns by 8 rows; 40 by 24 is comfortable on a phone.
Long-running diagnostics run outside the rendering loop. A pending network
operation may take a few seconds to finish after quitting.

## Profile choices

| Environment | Installer | Included |
| --- | --- | --- |
| Ubuntu/Debian desktop | `./install.sh` | Full Underlight, TUI, GPU and Android helpers |
| EndeavourOS/Arch desktop | `./install-endeavouros.sh` | Full desktop packages and the same helpers |
| Arch/Arch ARM in Termux | `./install-terminal.sh --packages` | Python/curses, network clients, SSH, tmux, and TUI |
| Existing Linux terminal/SSH host | `./install-terminal.sh` | Only minimal configuration links; keep existing packages |

The minimal profile does not install Hyprland, Wofi, NetworkManager, Neovim,
NVIDIA/CUDA, Android Studio, Flutter, an emulator, or background services.
It can run as the guest root account used by PRoot. The graphical EndeavourOS
installer is for a regular desktop account, not the phone container.

## Set up Arch on an Android phone

Install Termux from a source listed by the [Termux project](https://github.com/termux/termux-app#installation).
Keep the Linux filesystem in Termux's private storage, not shared Android
storage, so executable files and symlinks work.

In Termux:

```sh
pkg update
pkg install proot-distro curl
uname -m
proot-distro --version
proot-distro install --help
```

For a typical `aarch64` phone, use the AArch64 multi-platform root filesystem
from [Arch Linux ARM downloads](https://archlinuxarm.org/about/downloads).
Download it into Termux's home directory and verify its accompanying signature
using the publisher's instructions. Do not use an x86_64 Arch desktop image.

Recent PRoot-Distro versions accept a local rootfs archive:

```sh
proot-distro install ./ArchLinuxARM-aarch64-latest.tar.gz --name arch --architecture aarch64
proot-distro login arch
```

These flags are documented by [PRoot-Distro](https://github.com/termux/proot-distro#readme).
Older releases use distro aliases: if `proot-distro list` explicitly offers
`archlinux`, use `proot-distro install archlinux` and
`proot-distro login archlinux` instead. Do not mix the old and new command
formats. Use the matching ARM archive for a 32-bit device.

Inside Arch, initialize its package keys as described in the
[Arch Linux ARM installation guide](https://archlinuxarm.org/platforms/armv8/generic),
then install Underlight:

```sh
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Syu --needed git ca-certificates
git clone https://github.com/c-lydia/underlight.git ~/dotfiles
cd ~/dotfiles
./install-terminal.sh --packages
export PATH="$HOME/.local/bin:$PATH"
underlight-tui
```

Add the PATH export to the guest's `~/.bashrc` for future sessions. Keep the
repository in place: installed commands are symlinks to it. To preserve a lab
session while switching terminal tabs, run `tmux new -As underlight` before
starting the TUI. Android can still terminate Termux in the background.

Use the same `proot-distro login` command to return later. The normal desktop
installer rollback works here too:

```sh
~/dotfiles/install.sh --restore latest
```

Rollback removes linked configuration; it does not uninstall packages.

## Network tools

The lab offers interface/route/socket inspection, DNS lookup, ping, a single
TCP connection test, a UDP sender/receiver, and interactive SSH. Actions only
contact the destination entered by the operator; opening the TUI performs no
network scan. Plain commands work in scripts or narrow terminals:

```sh
underlight-tui status
underlight-tui dns example.com
underlight-tui tcp 192.168.1.10 22
underlight-tui ping 192.168.1.10
underlight-tui udp-listen 55555
underlight-tui udp-send 192.168.1.10 55555 'hello from phone'
```

The UDP receiver binds all IPv4 interfaces, receives at most one 4096-byte
packet, and times out after ten seconds. UDP send reports a send, not proof of
delivery. Use the actual reachable receiver address. Ping, `ip`, and `ss` may be
restricted by Android even though DNS, TCP, UDP, and SSH work. The TUI displays
these errors without treating the entire lab as unavailable. PRoot shares the
host kernel and networking; it does not provide a separate network namespace.

On desktops, **Super+X → Network lab (TUI)** opens it in Kitty. It also appears
in the application launcher. The desktop TUI adds Android tools when available,
and NetworkManager settings/hotspot actions when system services are present.
`underlight-network tui` opens the lab directly; a headless network-menu launch
falls back to it automatically.

## Hotspot and NAT

On a rootless phone, create the hotspot through Android's settings. PRoot's
simulated root cannot configure Android's radios, routing, or firewall.

On a desktop with NetworkManager and a spare Wi-Fi adapter:

```sh
underlight-network hotspot-start
underlight-network hotspot-stop
```

These commands support both desktop dialogs and terminal prompts. The existing
protection against disconnecting the only Wi-Fi uplink remains in place.
NetworkManager supplies addressing, DHCP, and NAT for its shared connection.

A separate IPv4 NAT helper is available for a real-root Linux host or a rooted
Android chroot with `CAP_NET_ADMIN`, an `iptables` executable, and kernel NAT
support. It is independent of NetworkManager. Do not layer it over Android's
or NetworkManager's already-managed tethering connection.

First configure the actual uplink, downstream interface/address, and client
addresses (DHCP or static) on the host. The helper does not create a Wi-Fi AP,
DHCP server, or routes. Inspect a plan without privileges:

```sh
underlight-net-admin status
underlight-net-admin nat-plan eth0 wlan0 192.168.50.0/24
```

Replace the example interfaces and subnet with your lab's values. To enable
forwarding and apply the plan on a regular Linux desktop:

```sh
sudo sysctl -w net.ipv4.ip_forward=1
sudo "$HOME/.local/bin/underlight-net-admin" nat-start eth0 wlan0 192.168.50.0/24
sudo "$HOME/.local/bin/underlight-net-admin" nat-stop
```

For a rooted phone, run the corresponding commands from a real root shell in
the chroot. Root access alone is insufficient if the kernel or Android policy
does not permit the operation. The helper checks effective kernel capabilities
and never elevates privileges itself.

Rules live in dedicated `UNDERLIGHT_NAT` and `UNDERLIGHT_FWD` chains. Start
refuses existing chains without its ownership state, rolls back failed
transactions, and records inverses under `/run/underlight-network`. Stop removes
only its own recorded rules. It never flushes the host firewall or changes
`ip_forward`; restore forwarding yourself when appropriate for the host.
Rules are temporary and are not installed as a boot service.

## Validation scope

Automated tests exercise compact/wide layouts in pseudo-terminals, resizing,
missing network utilities, input validation, installer rollback, NAT permission
checks, and firewall transaction rollback using mocks. A physical Android
phone, its kernel restrictions, and actual Wi-Fi/NAT hardware still require an
on-device check. No firewall changes occur during the test suite.
