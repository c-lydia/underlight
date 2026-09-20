#!/usr/bin/env bash

set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target_home=${1:-${HOME:?}}
backup_dir="${XDG_STATE_HOME:-$target_home/.local/state}/underlight-dotfiles-backup-$(date +%Y%m%d-%H%M%S)"
backup_used=false

link_item() {
  local relative_path=$1
  local source_path="$repo_dir/$relative_path"
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
  printf 'Linked: %s\n' "$relative_path"
}

link_item .config/hypr/hyprland.conf
link_item .config/hypr/underlight
link_item .config/waybar/config.jsonc
link_item .config/waybar/style.css
link_item .config/underlight/widgets.css
link_item .local/bin/underlight-background
link_item .local/bin/underlight-clipboard
link_item .local/bin/underlight-install-extras
link_item .local/bin/underlight-menu
link_item .local/bin/underlight-power
link_item .local/bin/underlight-sensor
link_item .local/bin/underlight-shot
link_item .local/bin/underlight-widgets
link_item .local/bin/underlight-widgets-toggle
link_item .local/bin/underlight-window-mode

if [[ $backup_used == true ]]; then
  printf '\nPrevious files were preserved in %s\n' "$backup_dir"
fi
