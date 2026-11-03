# Everyday Underlight workflows

These six helpers are included by `./install.sh` on Ubuntu and by the same
installer used by EndeavourOS. They are also linked by `./install-terminal.sh`:
text commands work in SSH and on a phone; graphical menus require Wofi and a
desktop session. All helpers provide `--help` and use Python 3.10 or newer.

Run the installer once after updating to link the new commands, then run
`hyprctl reload` in Hyprland. The machine hook is optional: existing installs
without the helper or a saved profile continue using their current monitors.
No new services run in the background. Local settings live under
`${XDG_CONFIG_HOME:-~/.config}/underlight`; keep these outside the checkout.

EndeavourOS installs all six by default with their desktop dependencies. See
[EndeavourOS setup and upgrades](FEATURES.md#endeavouros-feature-parity) for a
package preview and an example machine profile. `--with-rag` is only needed
for the optional note-retrieval environment, not the workflow commands themselves.

## Searchable shortcut guide

Press **Super+/** or select **Shortcut guide** in **Super+X**. Search by key,
command or description and select a row to run that action. The guide reads
the installed `hypr/underlight/bindings.conf`, expands its variables, and adds
menu actions such as audio, Android, privacy, profiles and snapshot preview.
It does not include bindings supplied by third-party plugins or other files.

```sh
underlight-shortcuts --list
underlight-shortcuts --list --search workspace
```

## Configuration snapshots

Preview first, save to a new filename, then inspect or restore:

```sh
underlight-snapshot create
underlight-snapshot create --output ~/underlight-before-update.json
underlight-snapshot inspect ~/underlight-before-update.json
underlight-snapshot restore ~/underlight-before-update.json
underlight-snapshot restore ~/underlight-before-update.json --apply
```

The allowlist includes desktop configs, SSH configuration files, Neovim's
`after/plugin/*.lua`, and Underlight capture, privacy, project and machine
settings. It covers the standard home-directory layout used by the installers;
`--home DIRECTORY` reads a staged home. It does not export entire Neovim setups,
Obsidian vaults, AI account/provider configs, SSH keys, model files, indexes,
caches or chat databases. Files containing recognized credential markers are
skipped. Snapshots are private files (mode 600), not encrypted archives; inspect
the preview before moving one to another machine. Custom secrets embedded in
otherwise ordinary settings cannot be identified reliably by a pattern scan.

Restore defaults to a filename-only preview. It checks paths, sizes and hashes
before writing, retains prior files and file symlinks under
`~/.local/state/underlight/snapshot-rollbacks/`, and rolls back if a write fails.
It never deletes settings absent from the snapshot. Restoring through a
directory symlink is refused to protect the linked dotfiles checkout. On an
installed machine with linked config directories, restore into a clean staging
directory and review/copy the wanted changes:

```sh
underlight-snapshot restore ~/underlight-before-update.json --target ~/underlight-restored --apply
```

The snapshot may contain machine paths and executable configuration. Review it
before applying it to a different host. It does not install packages or restart
applications.

## Project workspaces

Register a project once, then press **Super+Alt+W** or open it by name:

```sh
underlight-project add robot ~/projects/robot --vault ~/Notes --note 'Projects/Robot.md'
underlight-project open robot --preview
underlight-project open robot
underlight-project list
```

Each project owns a tmux session containing `editor`, `shell` and `logs` windows.
Repeated launches reuse that session, which survives closing Kitty or an SSH
disconnect. Use tmux's **Ctrl+B, D** to detach. In Hyprland, the helper opens
Kitty and the selected Obsidian note; in a plain terminal it attaches directly.
`--detach` creates/reuses the session without opening a UI. Obsidian and its URI
handler must already be installed for the note to open.

Use `--editor EXECUTABLE` when registering to choose an editor (default `nvim`).
Install tmux separately if needed: `sudo apt install tmux` on Ubuntu, or
`sudo pacman -S --needed tmux` on EndeavourOS. The EndeavourOS and terminal
package bootstraps already include it.

ROS setup is explicit:

```sh
underlight-project add robot-ros ~/projects/robot --ros-setup ~/projects/robot/install/setup.bash
```

This trusts and sources that file in each newly created window, including the
editor. No project-local scripts are discovered or executed automatically.
Edit `underlight/projects/NAME.json` to change a registration. Existing tmux
sessions retain their environment until you close and recreate them. Personal
project paths stay out of Git.

## Luma privacy controls

The desktop Luma panel shows the mode and opens a privacy menu. The Obsidian
Luma panel has the same modes in a dropdown. The AI and system menus also expose
them. **Local is the default**, including on existing installs without a saved
preference.

| Mode | Cloud-capable launches through Luma/underlight-ai | RAG MCP and HTTP results |
| --- | --- | --- |
| `local` | Blocked | Note retrieval and answers cannot be exported to clients; use `underlight-rag ask` locally |
| `local-answer` | Allowed | Locally generated answer and source metadata; raw retrieved chunks omitted |
| `cloud-context` | Allowed | Raw retrieved note/code excerpts may be returned |

```sh
underlight-privacy status
underlight-privacy set local-answer
underlight-privacy set local
UNDERLIGHT_PRIVACY=cloud-context underlight-ai opencode ~/projects/robot
```

The environment override applies to that command and its children. Saved
settings live in `underlight/privacy.json`. RAG checks the policy for each
request and again before returning its result. Local inference requires a
loopback Ollama endpoint and rejects cloud-labelled models. Qwen and **Ask my
notes** in the Obsidian companion open the local terminal tools, without
routing through Copilot/OpenCode. A vault's `.obsidian/underlight-rag.yaml` is
used when present. Optional RAG setup and indexing are still required.

This controls Underlight launches and RAG disclosure, not the whole machine's
network access. Existing agents, direct launches, other plugins, and their own
file-reading tools retain their permissions. In `local-answer`, an answer can
still quote or reveal facts from a note, and source paths are shared. The
setting does not sanitize generated answers or retroactively stop a running
cloud client. A local Ollama service must itself be configured to run locally.

Close Obsidian and reapply `underlight-obsidian /path/to/vault --luma` to update
an existing vault's companion. Restart desktop Luma to load its updated UI.

## Obsidian quick capture

Choose an existing vault, then press **Super+Alt+N**:

```sh
underlight-capture setup ~/Notes
underlight-capture text 'Check the robot battery before testing'
printf 'A longer thought\nwith another line\n' | underlight-capture text
underlight-capture link https://example.org/reference
underlight-capture clipboard
underlight-capture screenshot
```

The menu offers thought, link, clipboard text and selected-area screenshot.
Each capture creates a timestamped Markdown note in `00 Inbox`; change that with
`setup --inbox 'My Inbox'`. Screenshots are stored under
`90 Attachments/Captures` and embedded using relative Markdown links. Existing
notes are never overwritten. Cancelled menus or screenshot selections create
nothing. Symlinks that would escape the vault are refused.

Clipboard capture needs `wl-paste`; screenshots need `grim` and `slurp`.
These are the same tools used by the desktop configuration. Text/link commands
work without Obsidian running. An explicit `--vault /path` before the subcommand
overrides the saved vault; otherwise capture uses its setup, the active machine
vault, or Luma's vault preference, in that order.

## Per-machine profiles

Keep distro, hardware kind and user paths separate without copying the shared
desktop configuration:

```sh
underlight-machine create laptop --kind laptop --distro ubuntu --gpu hybrid \
  --monitor 'eDP-1,preferred,auto,1' --project-root ~/projects --vault ~/Notes
underlight-machine apply laptop --preview
underlight-machine apply laptop
hyprctl reload
underlight-machine status
```

Kinds are `laptop`, `desktop` and `phone`; distro metadata is `auto`, `ubuntu`,
`endeavouros` or `arch`. Profiles live in `underlight/machines/NAME.json` and
the selected settings in `underlight/machine.json`. `list` and `menu` let you
switch between saved profiles. Edit the JSON to update a profile, then apply it.

Monitor rules are validated and applied by `underlight-machine restore` after
Hyprland login/reload. Missing settings are a no-op. The hook uses Hyprland's
[dynamic keyword interface](https://wiki.hypr.land/0.52.0/Configuring/Using-hyprctl/)
and does not source a possibly missing file. Phone profiles skip monitor rules.
Only supply monitor names/modes that your machine supports.

`integrated` makes `underlight-gpu-run` launch without offload variables;
`auto` and `hybrid` retain the existing discrete-GPU discovery and fallback.
This affects new helper launches, not the compositor's GPU or installed drivers.
The default vault feeds capture and new project registrations; `project_root`
resolves relative directories passed to `underlight-project add`. Distro and
hardware kind are descriptive choices, not package or driver installers.

## Verification

`bash tests/smoke.sh` exercises all helpers and staged installation/rollback.
The workflow tests use temporary homes and fake clients; RAG tests mock model
and database calls to verify privacy without uploading notes. Desktop rendering,
real monitor modes and model quality require checks on the target machine.
