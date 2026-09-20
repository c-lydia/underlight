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
  local restore_dir=$requested relative_path source_path target_path
  if [[ $requested == latest ]]; then
    local candidates=("$state_root"/underlight-dotfiles-backup-*)
    ((${#candidates[@]} > 0)) || { printf 'No Underlight rollback found in %s\n' "$state_root" >&2; return 1; }
    restore_dir=${candidates[-1]}
  fi
  [[ -f $restore_dir/linked-items ]] || { printf 'Invalid Underlight rollback: %s\n' "$restore_dir" >&2; return 1; }
  while IFS= read -r relative_path; do
    [[ -n $relative_path ]] || continue
    source_path="$repo_dir/$relative_path"
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
  done < "$restore_dir/linked-items"
  printf 'Rollback completed from %s\n' "$restore_dir"
}

if [[ ${1:-} == --restore ]]; then
  restore_install "${2:-latest}"
  exit
fi

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
  changed_items+=("$relative_path")
  printf 'Linked: %s\n' "$relative_path"
}

link_item .config/hypr/hyprland.conf
link_item .config/hypr/underlight
link_item .config/waybar/config.jsonc
link_item .config/waybar/style.css
link_item .config/underlight/widgets.css
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
link_item .local/bin/underlight-profile
link_item .local/bin/underlight-power
link_item .local/bin/underlight-sensor
link_item .local/bin/underlight-shot
link_item .local/bin/underlight-widgets
link_item .local/bin/underlight-widgets-toggle
link_item .local/bin/underlight-window-mode

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
