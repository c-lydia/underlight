#!/usr/bin/env bash

set -euo pipefail
shopt -s nullglob

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --restore ]]; then
  target_home=${HOME:?}
else
  target_home=${1:-${HOME:?}}
fi
backup_dir="${XDG_STATE_HOME:-$target_home/.local/state}/underlight-dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
backup_used=false
changed_items=()

restore_install() {
  local requested=${1:-latest}
  local state_root="${XDG_STATE_HOME:-$target_home/.local/state}"
  local restore_dir=$requested entry relative_path source_path target_path item_index
  local -a linked_items=()
  if [[ $requested == latest ]]; then
    local candidates=("$state_root"/underlight-dotfiles-backup-*)
    ((${#candidates[@]} > 0)) || { printf 'No Underlight rollback found in %s\n' "$state_root" >&2; return 1; }
    restore_dir=${candidates[-1]}
  fi
  [[ -f $restore_dir/linked-items ]] || { printf 'Invalid Underlight rollback: %s\n' "$restore_dir" >&2; return 1; }
  mapfile -t linked_items < "$restore_dir/linked-items"
  for ((item_index=${#linked_items[@]} - 1; item_index >= 0; item_index--)); do
    entry=${linked_items[item_index]}
    IFS=$'\t' read -r relative_path source_path <<< "$entry"
    [[ -n $relative_path ]] || continue
    source_path=${source_path:-"$repo_dir/$relative_path"}
    target_path="$target_home/$relative_path"
    if [[ -L $target_path ]] && [[ $(readlink -f -- "$target_path") == $(readlink -f -- "$source_path") ]]; then
      rm -- "$target_path"
    elif [[ -e $target_path || -L $target_path ]]; then
      printf 'Preserving changed target during rollback: %s\n' "$target_path" >&2
      continue
    fi
    if [[ -e $restore_dir/$relative_path || -L $restore_dir/$relative_path ]]; then
      mkdir -p -- "$(dirname -- "$target_path")"
      mv -- "$restore_dir/$relative_path" "$target_path"
      printf 'Restored: %s\n' "$relative_path"
    else
      printf 'Removed new link: %s\n' "$relative_path"
    fi
  done
  printf 'Rollback completed from %s\n' "$restore_dir"
}

if [[ ${1:-} == --restore ]]; then
  restore_install "${2:-latest}"
  exit
fi

link_item() {
  local relative_path=$1
  local source_path=${2:-"$repo_dir/$relative_path"}
  local target_path="$target_home/$relative_path"

  if [[ ! -e $source_path ]]; then
    printf 'Missing repository item: %s\n' "$source_path" >&2
    return 1
  fi

  if [[ -L $target_path ]] && [[ $(readlink -f -- "$target_path") == $(readlink -f -- "$source_path") ]]; then
    printf 'Already linked: %s\n' "$relative_path"
    return
  fi

  mkdir -p -- "$(dirname -- "$target_path")"
  if [[ -e $target_path || -L $target_path ]]; then
    mkdir -p -- "$backup_dir/$(dirname -- "$relative_path")"
    mv -- "$target_path" "$backup_dir/$relative_path"
    backup_used=true
  fi

  ln -s -- "$source_path" "$target_path"
  if [[ $source_path == "$repo_dir/$relative_path" ]]; then
    changed_items+=("$relative_path")
  else
    changed_items+=("$relative_path"$'\t'"$source_path")
  fi
  printf 'Linked: %s\n' "$relative_path"
}

install_neovim_workbench() {
  if [[ ${UNDERLIGHT_SKIP_NEOVIM:-0} == 1 ]]; then
    printf 'Skipping the Neovim workbench (UNDERLIGHT_SKIP_NEOVIM=1).\n'
    return
  fi

  local workbench_source=${UNDERLIGHT_NEOVIM_SOURCE:-}
  local data_root="$target_home/.local/share/underlight"
  local checkout="$data_root/neovim_config"
  local nvim_target="$target_home/.config/nvim"

  # A real home install on Ubuntu also installs the editor executable when it
  # is absent. Staged installs into another TARGET_HOME never mutate host
  # packages.
  if [[ $target_home == "${HOME:?}" ]] && ! command -v nvim >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
      printf 'Installing Neovim with apt...\n'
      sudo apt-get update
      sudo apt-get install -y neovim
    else
      printf 'Neovim is not installed and this system has no supported apt/sudo installer.\n' >&2
      printf 'Install Neovim 0.11.3 or newer, then run this installer again.\n' >&2
      return 1
    fi
  fi

  if [[ -n $workbench_source ]]; then
    workbench_source=$(realpath -- "$workbench_source")
    [[ -f $workbench_source/init.lua ]] || {
      printf 'Invalid Neovim workbench source: %s\n' "$workbench_source" >&2
      return 1
    }
  else
    mkdir -p -- "$data_root"
    if [[ ! -e $checkout ]]; then
      command -v git >/dev/null 2>&1 || {
        printf 'Git is required to install the Neovim workbench.\n' >&2
        return 1
      }
      printf 'Installing the Neovim workbench...\n'
      git clone --depth 1 https://github.com/c-lydia/neovim_config.git "$checkout"
    elif [[ ! -d $checkout/.git || ! -f $checkout/init.lua ]]; then
      printf 'Preserving non-workbench path: %s\n' "$checkout" >&2
      printf 'Set UNDERLIGHT_NEOVIM_SOURCE to a valid checkout or move that path aside.\n' >&2
      return 1
    else
      printf 'Using existing Neovim workbench checkout: %s\n' "$checkout"
    fi
    workbench_source=$checkout
  fi

  if [[ -e $nvim_target || -L $nvim_target ]]; then
    if [[ $nvim_target -ef $workbench_source ]]; then
      printf 'Neovim already uses the Underlight workbench.\n'
    else
      printf 'Preserving existing Neovim config: %s\n' "$nvim_target" >&2
      printf 'The Underlight transparency overlay will still be installed.\n' >&2
    fi
  else
    link_item .config/nvim "$workbench_source"
  fi
}

install_neovim_workbench

link_item .config/hypr/hyprland.conf
link_item .config/nvim/after/plugin/underlight-transparent.lua
link_item .config/kitty/kitty.conf
link_item .config/hypr/underlight
link_item .config/waybar/config.jsonc
link_item .config/waybar/style.css
link_item .config/wofi/config
link_item .config/wofi/style.css
link_item .config/mako/config
link_item .config/underlight/logo.svg
link_item .config/underlight/widgets.css
link_item .local/share/underlight/give_laptop_ac
link_item .local/bin/underlight-ai
link_item .local/bin/underlight-background
link_item .local/bin/underlight-clipboard
link_item .local/bin/underlight-doctor
link_item .local/bin/underlight-gpu-check
link_item .local/bin/underlight-gpu-menu
link_item .local/bin/underlight-gpu-run
link_item .local/bin/underlight-health-notify
link_item .local/bin/underlight-install-extras
link_item .local/bin/underlight-laptop
link_item .local/bin/underlight-menu
link_item .local/bin/underlight-minimize
link_item .local/bin/underlight-rag
link_item .local/bin/underlight-profile
link_item .local/bin/underlight-power
link_item .local/bin/underlight-sensor
link_item .local/bin/underlight-shot
link_item .local/bin/underlight-widgets
link_item .local/bin/underlight-widgets-toggle
link_item .local/bin/underlight-window-mode
link_item .local/bin/nvim-workspace

if [[ ${UNDERLIGHT_WITH_RAG:-0} == 1 ]]; then
  link_item .local/share/underlight/rag_pipeline
fi

if ((${#changed_items[@]} > 0)); then
  mkdir -p -- "$backup_dir"
  printf '%s\n' "${changed_items[@]}" > "$backup_dir/linked-items"
  if [[ $backup_used == true ]]; then
    printf '\nPrevious files were preserved in %s\n' "$backup_dir"
  else
    printf '\nRollback metadata saved in %s\n' "$backup_dir"
  fi
  printf 'Undo this installation with: %s --restore %s\n' "$0" "$backup_dir"
fi
