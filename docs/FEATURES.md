# Underlight feature guide

Ubuntu and EndeavourOS share the desktop configuration and helpers in this
repository. The terminal profile includes the network lab, SSH defaults and
workflow helpers; graphical actions still need a desktop session.
This index covers the current features, including the integrations added after
the original desktop walkthrough.

| Feature | Open it | Setup and details |
| --- | --- | --- |
| Desktop actions, Wi-Fi, audio and session controls | `Super+X` | [Keyboard controls](../README.md#keyboard-controls) |
| Searchable shortcut guide | `Super+/` | [Shortcut guide](WORKFLOWS.md#searchable-shortcut-guide) |
| Configuration snapshot and restore | `underlight-snapshot` | [Snapshot guide](WORKFLOWS.md#configuration-snapshots) |
| Persistent project workspaces | `Super+Alt+W` | [Projects](WORKFLOWS.md#project-workspaces) |
| Luma privacy modes | `underlight-privacy menu` | [Privacy behavior](WORKFLOWS.md#luma-privacy-controls) |
| Obsidian quick capture | `Super+Alt+N` | [Capture setup](WORKFLOWS.md#obsidian-quick-capture) |
| Machine monitor, GPU and path defaults | `underlight-machine` | [Machine profiles](WORKFLOWS.md#per-machine-profiles) |
| Network lab | `underlight-tui` or **Super+X → Network lab (TUI)** | [Network lab guide](TERMINAL.md) |
| Laptop overview, sensor charts and verified controls | `Super+Shift+A` or `underlight-laptop` | [Dashboard guide](../.local/share/underlight/give_laptop_ac/README.md) |
| Shared Luma AI companion | `underlight-luma --show` | [Luma setup and troubleshooting](OBSIDIAN.md#shared-luma-companion) |
| OpenCode, Zen, Hermes, Copilot CLI, Cursor and Antigravity | `underlight-ai menu` or `Super+Shift+I` | [AI entry points](../README.md#local-ai-stack) |
| Local Qwen and note retrieval | Luma's **Qwen** / **Ask my notes**, or `underlight-ai rag` | [GPU Qwen and RAG](OBSIDIAN.md#gpu-qwen-and-rag) |
| Obsidian styling, templates and home note | `underlight-obsidian /path/to/vault` | [Obsidian workbench](OBSIDIAN.md) |
| Obsidian Agent Client bridges | `underlight-obsidian /path/to/vault --hermes --copilot-cli --cursor --antigravity` | [Host agent setup](OBSIDIAN.md#host-agents-hermes-copilot-cli-cursor-antigravity) |
| Obsidian Copilot/OpenCode integration | `underlight-obsidian /path/to/vault --ai` plus required configuration | [Copilot, OpenCode and RAG](OBSIDIAN.md#copilot-opencode-and-local-rag) |
| Guarded Copilot and NotebookLM repairs | `--repair-copilot-view` / `--repair-notebooklm` with a vault | [Plugin repairs](OBSIDIAN.md#copilot-blank-panel-repair) |
| Android Studio, ADB, Flutter and emulator tools | **Super+X → Android & Flutter** | [Android guide](ANDROID.md) |
| Persistent ROS/SSH shells and development workspaces | `ros2-workspace` / `nvim-workspace` | [Workspace guide](../README.md#persistent-ros-2-and-ssh-shells) |
| GPU launchers, profiles and optional glass | `Super+Shift+G`, `underlight-profile`, `underlight-glass` | [Main desktop guide](../README.md) |
| Supervised wallpaper | Hyprland login or reload | [Wallpaper service](../README.md#configuration-layer) |

## Network lab interaction

The lab and laptop dashboard follow Underlight and the portfolio's dark violet,
pale cyan and lavender palette. The lab uses a single divider and previews the
selected tool before the first run. The dashboard uses compact, borderless cards
with normal-size readings at every terminal size. Process tables use alternating
row colors.

Tools are grouped into inspection, diagnostics, datagrams, connections and
available platform integrations. `/` filters names and descriptions. `Tab`
switches focus between tools and results; narrow windows show one pane at a
time. `?` shows all shortcuts. Result history (`[` / `]`) retains the last 20
runs in memory. Inputs remember their last values for the current session;
Escape cancels and Ctrl+U clears. No probes run automatically.

Running diagnostics show their tool name and elapsed time. Browse earlier
results while the current request finishes. Results include the destination,
completion time and scroll position. “Finished” means the tool returned; read
its output to see whether the network check succeeded. The same features work
in EndeavourOS, Ubuntu, SSH and the Arch/Termux terminal profile.

## Laptop dashboard interaction

The overview uses CPU, GPU, memory and battery cards with 60-reading trends.
Explicit N/A labels indicate unavailable readings. CPU/GPU temperature warnings add
**WARM** or **HOT** text and a warning border using the configured alert
thresholds. The overview heading shows the last refresh time. Hover over a card
or status message for its full details.

Press `v` to expand detailed sensor charts, `d`/`o`/`p` to switch between the
dashboard, controls and processes, and `j`/`k` or `f`/`b` to scroll. At narrow
widths, both overview cards and detailed sensor charts stack vertically. Control
rows can be scrolled horizontally with `h`/`l`. Hardware controls retain their
existing readback checks, capability checks and rollback behavior.

## EndeavourOS feature parity

The EndeavourOS bootstrap calls the same `install.sh`, so Luma, all Obsidian
bridges and repairs, the network lab, Android launchers, wallpaper service,
updated dashboard and glass configuration are included without separate copies.
It installs Python/GTK/layer-shell for Luma, Python YAML for Obsidian AI setup,
and Python/curses, iproute2, ping, OpenSSH and tmux for terminal workflows.

All six new workflows are installed by default, including their shared Python
modules and keyboard bindings:

| Workflow | EndeavourOS dependencies / first use |
| --- | --- |
| Configuration snapshot/restore | Python; run `underlight-snapshot create` to preview |
| Shortcut search (`Super+/`) | Wofi, Hyprland; ready after installation |
| Project workspaces (`Super+Alt+W`) | tmux, Neovim, Kitty and xdg-utils; register with `underlight-project add NAME DIRECTORY` |
| Luma privacy | Shared Python policy and GTK/Obsidian UI; default `local` blocks cloud-capable launches |
| Obsidian capture (`Super+Alt+N`) | grim/slurp and wl-clipboard; choose a vault with `underlight-capture setup /path/to/vault` |
| Machine profiles | Python and Hyprland; create a profile with `--distro endeavouros` |

The bootstrap explicitly installs `coreutils` for bounded diagnostic probes and
`xdg-utils` for note opening. Arch's
[xdg-utils file list](https://archlinux.org/packages/extra/any/xdg-utils/files/)
includes `xdg-open`. Use `./install-endeavouros.sh --print-packages` to review the
bootstrap package list without changing the host; add `--with-rag` to include
its optional AI packages in that preview.

An EndeavourOS profile can keep its own project and vault paths:

```sh
underlight-machine create endeavour-laptop --kind laptop --distro endeavouros \
  --gpu hybrid --project-root ~/projects --vault /path/to/vault
underlight-machine apply endeavour-laptop --preview
underlight-machine apply endeavour-laptop
```

Monitor rules are optional. No Ubuntu paths, selected projects, vault contents
or credentials are copied to an EndeavourOS host by the installer.

Optional setup still matters:

- `./install-endeavouros.sh --with-ai` adds Ollama and OpenCode.
- `./install-endeavouros.sh --with-rag` also prepares the RAG Python environment.
  Review sources and choose models before indexing.
- `./install-endeavouros.sh --with-android` prepares Android/Flutter dependencies.
  Studio, SDK licenses and emulator images follow the Android guide.
- Obsidian and its community plugins, Hermes, Copilot CLI, Cursor, Antigravity,
  model downloads and account sign-ins remain separate setup steps. A launcher
  being installed does not mean its client or account is configured.
- MSI fan control requires the supported driver/service and permissions. NVIDIA
  drivers and the optional version-pinned HyprGlass binary remain host-specific.

To update an existing EndeavourOS checkout, first preserve any local edits, then:

```sh
git pull --ff-only
./install-endeavouros.sh # retain --with-ai/--with-rag/--with-android if wanted
systemctl --user daemon-reload
hyprctl reload
underlight-doctor
```

The bootstrap can update system packages and prepare dependencies. For code and
symlink updates on a machine whose dependencies are already installed, use
`./install.sh` instead. Existing symlinks immediately point at updated helper
code. Close and reopen the network lab and laptop dashboard to load it. Log out
and back in to restart the desktop Luma process. For an existing Obsidian vault,
close Obsidian, rerun `underlight-obsidian /path/to/vault --luma`, then reopen it.
Plugin changes use the helper's normal backup/restore mechanism; installation
of dotfiles does not automatically rewrite vaults.

`tests/test_endeavouros.py` runs the real bootstrap and shared installer against
temporary homes, substituting package/service calls. It checks default and RAG
installs, repeated installation, settings preservation and all six helpers.
The GitHub Actions Arch job also runs the smoke suite inside an Arch container
as a normal user. These checks do not simulate a live Hyprland desktop or GPU.
