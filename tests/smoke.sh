#!/usr/bin/env bash

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scripts=(
  "$root/install.sh"
  "$root/install-endeavouros.sh"
  "$root/.local/bin/underlight-ai"
  "$root/.local/bin/underlight-control"
  "$root/.local/bin/underlight-doctor"
  "$root/.local/bin/underlight-gpu-check"
  "$root/.local/bin/underlight-gpu-menu"
  "$root/.local/bin/underlight-gpu-run"
  "$root/.local/bin/underlight-health-notify"
  "$root/.local/bin/underlight-install-extras"
  "$root/.local/bin/underlight-laptop"
  "$root/.local/bin/underlight-minimize"
  "$root/.local/bin/underlight-rag"
  "$root/.local/bin/underlight-profile"
  "$root/.local/bin/underlight-sensor"
  "$root/.local/bin/nvim-workspace"
)
bash -n "${scripts[@]}"
for script in "${scripts[@]}"; do
  [[ -x $script ]] || { printf 'not executable: %s\n' "$script" >&2; exit 1; }
done
python3 -m json.tool "$root/.config/waybar/config.jsonc" >/dev/null

test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
test_home="$test_root/home"
test_state="$test_root/state"
mkdir -p "$test_home" "$test_state"
test_workbench="$test_root/neovim-workbench"
mkdir -p "$test_workbench"
printf '%s\n' '-- test Neovim workbench' > "$test_workbench/init.lua"
HOME="$test_home" XDG_STATE_HOME="$test_state" \
  UNDERLIGHT_NEOVIM_SOURCE="$test_workbench" "$root/install.sh" >/dev/null
[[ -L $test_home/.config/nvim ]]
[[ $(readlink -f -- "$test_home/.config/nvim") == $(readlink -f -- "$test_workbench") ]]
[[ -L $test_home/.local/bin/underlight-control ]]
[[ -L $test_home/.local/bin/underlight-doctor ]]
[[ -L $test_home/.config/nvim/after/plugin/underlight-transparent.lua ]]
[[ -L $test_home/.config/kitty/kitty.conf ]]
[[ -L $test_home/.config/wofi/config ]]
[[ -L $test_home/.config/wofi/style.css ]]
[[ -L $test_home/.config/mako/config ]]
[[ -L $test_home/.config/underlight/logo.svg ]]
[[ -L $test_home/.config/underlight/widgets.css ]]
[[ -L $test_home/.local/share/underlight/give_laptop_ac ]]
[[ -L $test_home/.local/bin/underlight-rag ]]
[[ -L $test_home/.local/bin/nvim-workspace ]]
grep -Fq 'bind = $mainMod, X, exec, ~/.local/bin/underlight-control' \
  "$test_home/.config/hypr/underlight/bindings.conf"
grep -Fq 'bind = $mainMod, TAB, workspace, e+1' \
  "$test_home/.config/hypr/underlight/bindings.conf"
grep -Fq 'bind = $mainMod SHIFT, TAB, workspace, e-1' \
  "$test_home/.config/hypr/underlight/bindings.conf"
HOME="$test_home" XDG_STATE_HOME="$test_state" "$root/install.sh" --restore latest >/dev/null
if [[ -e $test_home/.config/nvim || -L $test_home/.config/nvim ]]; then
  printf 'rollback left the Neovim workbench link installed\n' >&2
  exit 1
fi
if [[ -e $test_workbench/after/plugin/underlight-transparent.lua || -L $test_workbench/after/plugin/underlight-transparent.lua ]]; then
  printf 'rollback left the Neovim overlay installed\n' >&2
  exit 1
fi
if [[ -e $test_home/.local/bin/underlight-doctor || -L $test_home/.local/bin/underlight-doctor ]]; then
  printf 'rollback left the doctor link installed\n' >&2
  exit 1
fi
if [[ -e $test_home/.local/bin/underlight-control || -L $test_home/.local/bin/underlight-control ]]; then
  printf 'rollback left the system-actions link installed\n' >&2
  exit 1
fi

preserve_home="$test_root/preserve-home"
preserve_state="$test_root/preserve-state"
mkdir -p "$preserve_home/.config/nvim" "$preserve_state"
printf '%s\n' '-- existing user config' > "$preserve_home/.config/nvim/init.lua"
HOME="$preserve_home" XDG_STATE_HOME="$preserve_state" \
  UNDERLIGHT_NEOVIM_SOURCE="$test_workbench" "$root/install.sh" >/dev/null
[[ ! -L $preserve_home/.config/nvim ]]
[[ $(<"$preserve_home/.config/nvim/init.lua") == '-- existing user config' ]]
[[ -L $preserve_home/.config/nvim/after/plugin/underlight-transparent.lua ]]
HOME="$preserve_home" XDG_STATE_HOME="$preserve_state" "$root/install.sh" --restore latest >/dev/null
[[ -f $preserve_home/.config/nvim/init.lua ]]
if [[ -e $preserve_home/.config/nvim/after/plugin/underlight-transparent.lua || -L $preserve_home/.config/nvim/after/plugin/underlight-transparent.lua ]]; then
  printf 'rollback left the overlay in an existing Neovim config\n' >&2
  exit 1
fi

printf 'UNDERLIGHT_SMOKE_OK\n'
