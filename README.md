# Underlight

Personal Hyprland desktop configuration for Ubuntu. The repository mirrors the
paths below the home directory so the files can be restored with symbolic
links.

## Included

- Hyprland entry point and modular `underlight/` configuration
- Waybar configuration and styling
- Desktop widget program and CSS
- Underlight launcher, clipboard, power, screenshot, sensor, and window helpers

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
