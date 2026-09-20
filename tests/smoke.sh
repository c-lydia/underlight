#!/usr/bin/env bash

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scripts=(
  "$root/install.sh"
  "$root/.local/bin/underlight-ai"
  "$root/.local/bin/underlight-doctor"
  "$root/.local/bin/underlight-gpu-check"
  "$root/.local/bin/underlight-gpu-menu"
  "$root/.local/bin/underlight-gpu-run"
  "$root/.local/bin/underlight-health-notify"
  "$root/.local/bin/underlight-install-extras"
  "$root/.local/bin/underlight-laptop"
  "$root/.local/bin/underlight-profile"
  "$root/.local/bin/underlight-sensor"
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
HOME="$test_home" XDG_STATE_HOME="$test_state" "$root/install.sh" >/dev/null
[[ -L $test_home/.local/bin/underlight-doctor ]]
HOME="$test_home" XDG_STATE_HOME="$test_state" "$root/install.sh" --restore latest >/dev/null
if [[ -e $test_home/.local/bin/underlight-doctor || -L $test_home/.local/bin/underlight-doctor ]]; then
  printf 'rollback left the doctor link installed\n' >&2
  exit 1
fi

printf 'UNDERLIGHT_SMOKE_OK\n'
