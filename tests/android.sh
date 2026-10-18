#!/usr/bin/env bash
# shellcheck disable=SC2016
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
mkdir -p "$test_root/home/Android/Sdk/platform-tools" "$test_root/home/Android/Sdk/emulator" \
  "$test_root/home/Android/Sdk/cmdline-tools/latest/bin" "$test_root/home/projects/flutter/bin" \
  "$test_root/home/android-studio-release/android-studio/bin" "$test_root/config/underlight"
for tool in 'Android/Sdk/platform-tools/adb' 'Android/Sdk/emulator/emulator' \
  'Android/Sdk/cmdline-tools/latest/bin/sdkmanager' 'projects/flutter/bin/flutter' \
  'android-studio-release/android-studio/bin/studio'; do
  printf '#!/bin/sh\nprintf "tool:%%s\\n" "$0"\nprintf "arg:%%s\\n" "$@"\n' > "$test_root/home/$tool"
  chmod +x "$test_root/home/$tool"
done
cp "$root/.config/underlight/android.sh" "$test_root/config/underlight/android.sh"
for shell in bash sh zsh; do
  command -v "$shell" >/dev/null 2>&1 || continue
  env -u ANDROID_HOME -u ANDROID_SDK_ROOT -u ANDROID_STUDIO_HOME -u FLUTTER_ROOT \
    HOME="$test_root/home" PATH=/usr/bin:/bin "$shell" -c '
      set -eu
      . "$1"
      [ "$ANDROID_HOME" = "$HOME/Android/Sdk" ]
      [ "$ANDROID_STUDIO_HOME" = "$HOME/android-studio-release/android-studio" ]
      [ "$(command -v adb)" = "$ANDROID_HOME/platform-tools/adb" ]
      [ "$(command -v emulator)" = "$ANDROID_HOME/emulator/emulator" ]
      [ "$(command -v sdkmanager)" = "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" ]
      [ "$(command -v flutter)" = "$HOME/projects/flutter/bin/flutter" ]
      before=$PATH
      . "$1"
      [ "$PATH" = "$before" ]
    ' _ "$root/.config/underlight/android.sh"
  mkdir -p "$test_root/empty"
  env -u ANDROID_HOME -u ANDROID_SDK_ROOT -u ANDROID_STUDIO_HOME -u FLUTTER_ROOT \
    HOME="$test_root/empty" PATH=/usr/bin:/bin "$shell" -c 'set -eu; . "$1"' _ "$root/.config/underlight/android.sh"
done
output=$(env -u ANDROID_HOME -u ANDROID_SDK_ROOT -u ANDROID_STUDIO_HOME -u FLUTTER_ROOT HOME="$test_root/home" \
  PATH=/usr/bin:/bin XDG_CONFIG_HOME="$test_root/config" "$root/.local/bin/underlight-android" studio '/tmp/project with spaces')
[[ $output == *'arg:/tmp/project with spaces'* ]]
output=$(env -u ANDROID_HOME -u ANDROID_SDK_ROOT -u ANDROID_STUDIO_HOME -u FLUTTER_ROOT \
  HOME="$test_root/home" PATH=/usr/bin:/bin XDG_CONFIG_HOME="$test_root/config" \
  "$root/.local/bin/underlight-android" emulator test_avd -gpu software)
[[ $output == *$'arg:-avd\narg:test_avd\narg:-gpu\narg:software'* ]]
printf 'UNDERLIGHT_ANDROID_OK\n'
