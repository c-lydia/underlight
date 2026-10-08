#!/usr/bin/env bash
# Minimal network/TUI profile: no desktop, drivers, SDKs, services, or workbench.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  printf 'Usage: ./install-terminal.sh [--packages] [TARGET_HOME]\n'
  exit 0
fi
if [[ ${1:-} == --packages ]]; then
  shift
  elevate=()
  if (( EUID != 0 )); then elevate=(sudo); fi
  # shellcheck disable=SC1091
  . /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *' arch '*|*' archarm '*|*' endeavouros '*)
      "${elevate[@]}" pacman -Syu --needed python ncurses iproute2 iputils openssh tmux curl
      ;;
    *' ubuntu '*|*' debian '*)
      "${elevate[@]}" apt-get update
      "${elevate[@]}" apt-get install -y python3 ncurses-term iproute2 iputils-ping openssh-client tmux curl
      ;;
    *) printf 'Install Python 3, ncurses, iproute2, ping, OpenSSH, tmux, and curl for your distribution, then run without --packages.\n' >&2; exit 1 ;;
  esac
fi
(( $# <= 1 )) || { printf 'Usage: ./install-terminal.sh [--packages] [TARGET_HOME]\n' >&2; exit 2; }
UNDERLIGHT_PROFILE=minimal "$repo_dir/install.sh" "$@"
printf '%s\n' 'Minimal Underlight installed. Add ~/.local/bin to PATH, then run underlight-tui.' \
  'Plain diagnostics: underlight-tui status | underlight-tui tcp HOST PORT' \
  'Phone setup and optional privileged networking: docs/TERMINAL.md'
