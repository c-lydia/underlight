#!/usr/bin/env bash

set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
with_ai=false
with_rag=false

usage() {
  printf '%s\n' \
    'Usage: ./install-endeavouros.sh [--with-ai] [--with-rag]' \
    '' \
    'Default: install Underlight, the Neovim workbench, and give_laptop_ac.' \
    '  --with-ai   Also install Ollama and OpenCode; no models are downloaded.' \
    '  --with-rag  Also install the RAG pipeline and its Python environment.' \
    '              This implies --with-ai; indexes and models remain opt-in.'
}

while (($# > 0)); do
  case $1 in
    --with-ai) with_ai=true ;;
    --with-rag) with_rag=true; with_ai=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if ((EUID == 0)); then
  printf 'Run this installer as your normal desktop user, not as root.\n' >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  printf 'Cannot identify this Linux distribution: /etc/os-release is missing.\n' >&2
  exit 1
fi

# The distribution-owned file contains shell assignments such as ID and ID_LIKE.
# shellcheck disable=SC1091
source /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
  *" endeavouros "*|*" arch "*) ;;
  *)
    printf 'This installer is for EndeavourOS or another Arch-based distribution (found: %s).\n' "${PRETTY_NAME:-unknown}" >&2
    exit 1
    ;;
esac

command -v pacman >/dev/null 2>&1 || {
  printf 'pacman is required but was not found.\n' >&2
  exit 1
}

packages=(
  base-devel
  brightnessctl
  cliphist
  cmake
  curl
  fd
  firefox
  git
  grim
  gtk-layer-shell
  gtk3
  hypridle
  hyprland
  hyprpaper
  hyprpolkitagent
  jq
  kitty
  libnotify
  mako
  nautilus
  networkmanager
  network-manager-applet
  neovim
  ninja
  nodejs
  noto-fonts
  noto-fonts-emoji
  pavucontrol
  pipewire
  playerctl
  power-profiles-daemon
  python
  python-cairo
  python-gobject
  python-pip
  python-psutil
  ripgrep
  slurp
  switcheroo-control
  ttf-font-awesome
  udisks2
  unzip
  waybar
  wireplumber
  wl-clipboard
  wofi
  xdg-desktop-portal-gtk
  xdg-desktop-portal-hyprland
)

if [[ $with_ai == true ]]; then
  packages+=(ollama opencode)
fi

printf 'Installing Underlight desktop dependencies with pacman...\n'
sudo pacman -Syu --needed "${packages[@]}"
sudo systemctl enable --now NetworkManager.service

data_root="${HOME:?}/.local/share/underlight"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}/underlight"
venv_root="$data_root/venvs"
neovim_checkout="$data_root/neovim_config"

mkdir -p -- "$data_root" "$venv_root"
if [[ ! -e $neovim_checkout ]]; then
  printf '\nInstalling the Neovim workbench...\n'
  git clone --depth 1 https://github.com/c-lydia/neovim_config.git "$neovim_checkout"
elif [[ -d $neovim_checkout/.git ]]; then
  printf '\nUsing existing Neovim workbench checkout: %s\n' "$neovim_checkout"
else
  printf '\nPreserving non-Git Neovim workbench path: %s\n' "$neovim_checkout" >&2
fi

nvim_target="${XDG_CONFIG_HOME:-$HOME/.config}/nvim"
if [[ -x $neovim_checkout/scripts/install.sh ]]; then
  if [[ ! -e $nvim_target && ! -L $nvim_target ]]; then
    "$neovim_checkout/scripts/install.sh" --native --link
  elif [[ $nvim_target -ef $neovim_checkout ]]; then
    printf 'Neovim already uses the bundled workbench checkout.\n'
  else
    printf 'Preserving existing Neovim config: %s\n' "$nvim_target" >&2
    printf 'The Underlight transparency overlay will still be linked into it.\n' >&2
  fi
fi

printf '\nLinking the Underlight configuration into %s...\n' "${HOME:?}"
if [[ $with_rag == true ]]; then
  UNDERLIGHT_WITH_RAG=1 "$repo_dir/install.sh"
else
  "$repo_dir/install.sh"
fi

printf '\nCreating the give_laptop_ac Python environment...\n'
laptop_source="$data_root/give_laptop_ac"
laptop_venv="$venv_root/give_laptop_ac"
python -m venv "$laptop_venv"
"$laptop_venv/bin/python" -m pip install --upgrade pip
"$laptop_venv/bin/python" -m pip install -r "$laptop_source/requirements.txt"

if [[ $with_ai == true ]]; then
  printf '\nEnabling the optional Ollama service...\n'
  sudo systemctl enable --now ollama.service
fi

if [[ $with_rag == true ]]; then
  printf '\nCreating the optional RAG Python environment...\n'
  rag_source="$data_root/rag_pipeline"
  rag_venv="$venv_root/rag_pipeline"
  python -m venv "$rag_venv"
  "$rag_venv/bin/python" -m pip install --upgrade pip
  "$rag_venv/bin/python" -m pip install -r "$rag_source/requirements.txt"
  mkdir -p -- "$config_root"
  if [[ ! -e $config_root/rag.yaml ]]; then
    cp -- "$rag_source/.ragconfig.example.yaml" "$config_root/rag.yaml"
    printf 'Created editable RAG config: %s\n' "$config_root/rag.yaml"
  else
    printf 'Preserving existing RAG config: %s\n' "$config_root/rag.yaml"
  fi
fi

printf '%s\n' \
  '' \
  'Underlight is installed.' \
  'Log out, choose the Hyprland session in your login screen, and log back in.' \
  'From a TTY without a display manager, run: start-hyprland' \
  'System actions: Super+X' \
  'Next/previous desktop: Super+Tab / Super+Shift+Tab' \
  'Jump to desktop: Super+1..0; move a window: Super+Shift+1..0' \
  'After login, run underlight-doctor to check the setup.'

if [[ $with_ai == true ]]; then
  printf '%s\n' 'AI tools installed; use underlight-ai status. No model was downloaded.'
fi
if [[ $with_rag == true ]]; then
  printf '%s\n' \
    'RAG installed; review ~/.config/underlight/rag.yaml before indexing.' \
    'Start with: underlight-rag index --table projects --dry-run'
fi
