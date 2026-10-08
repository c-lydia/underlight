#!/usr/bin/env bash
# Variables inside shell -c scripts intentionally expand in the child shell.
# shellcheck disable=SC2016
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
mkdir -p "$test_root/toolkit/bin" "$test_root/toolkit/lib64" "$test_root/old/bin" "$test_root/config/underlight"
printf '#!/bin/sh\nprintf "selected-toolkit\\n"\n' > "$test_root/toolkit/bin/nvcc"
printf '#!/bin/sh\nprintf "old-toolkit\\n"\n' > "$test_root/old/bin/nvcc"
chmod +x "$test_root/toolkit/bin/nvcc" "$test_root/old/bin/nvcc"
cp "$root/.config/underlight/cuda.sh" "$test_root/config/underlight/cuda.sh"
for shell in bash sh zsh; do
  command -v "$shell" >/dev/null 2>&1 || continue
  env -u LD_LIBRARY_PATH CUDA_HOME="$test_root/toolkit" PATH="$test_root/old/bin:/usr/bin:/bin" \
    "$shell" -c '
      set -eu
      . "$1"
      [ "$(nvcc)" = selected-toolkit ]
      [ "$CUDA_PATH" = "$CUDA_HOME" ]
      [ "$LD_LIBRARY_PATH" = "$CUDA_HOME/lib64" ]
      before_path=$PATH
      before_lib=$LD_LIBRARY_PATH
      . "$1"
      [ "$PATH" = "$before_path" ]
      [ "$LD_LIBRARY_PATH" = "$before_lib" ]
    ' _ "$root/.config/underlight/cuda.sh"
  env CUDA_HOME="$test_root/missing" LD_LIBRARY_PATH=/existing PATH="$test_root/old/bin:/usr/bin:/bin" \
    "$shell" -c '
      set -eu
      before_path=$PATH
      . "$1"
      [ "$PATH" = "$before_path" ]
      [ "$LD_LIBRARY_PATH" = /existing ]
      [ "$(nvcc)" = old-toolkit ]
    ' _ "$root/.config/underlight/cuda.sh"
  env CUDA_HOME="$test_root/toolkit" LD_LIBRARY_PATH=/existing PATH=/usr/bin:/bin \
    "$shell" -c '
      set -eu
      . "$1"
      . "$1"
      [ "$LD_LIBRARY_PATH" = "$CUDA_HOME/lib64:/existing" ]
    ' _ "$root/.config/underlight/cuda.sh"
done
# Exercise launcher resolution without host switcheroo/D-Bus dependencies.
mkdir -p "$test_root/bin"
ln -s "$(command -v bash)" "$test_root/bin/bash"
printf '#!/bin/sh\nexit 0\n' > "$test_root/bin/switcherooctl"
chmod +x "$test_root/bin/switcherooctl"
output=$(env CUDA_HOME="$test_root/toolkit" XDG_CONFIG_HOME="$test_root/config" \
  PATH="$test_root/bin:$test_root/old/bin" "$root/.local/bin/underlight-gpu-run" nvcc)
[[ $output == selected-toolkit ]]
# A stale loaded module must produce actionable diagnostics.
printf '#!/bin/sh\nprintf "Failed to initialize NVML: Driver/library version mismatch\\n"\nexit 1\n' > "$test_root/bin/nvidia-smi"
chmod +x "$test_root/bin/nvidia-smi"
output=$(PATH="$test_root/bin:/usr/bin:/bin" "$root/.local/bin/underlight-gpu-check")
[[ $output == *'reboot to load the updated NVIDIA kernel module'* ]]
printf 'UNDERLIGHT_CUDA_OK\n'
