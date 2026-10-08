# shellcheck shell=sh
# Source from Bash or Zsh. Explicit SDK locations take precedence.
_underlight_prepend_path() {
    [ -d "$1" ] || return 0
    case :${PATH-}: in
        *:"$1":*) ;;
        *) export PATH="$1${PATH:+:$PATH}" ;;
    esac
}

_underlight_android_environment() {
# Keep unmatched discovery globs literal when this file is sourced in Zsh.
if [ -n "${ZSH_VERSION:-}" ]; then setopt local_options nonomatch; fi
if [ -z "${ANDROID_HOME:-}" ]; then
    if [ -n "${ANDROID_SDK_ROOT:-}" ]; then
        ANDROID_HOME=$ANDROID_SDK_ROOT
    elif [ -d "$HOME/Android/Sdk" ]; then
        ANDROID_HOME=$HOME/Android/Sdk
    elif [ -d /opt/android-sdk ]; then
        ANDROID_HOME=/opt/android-sdk
    fi
fi
if [ -n "${ANDROID_HOME:-}" ]; then
    export ANDROID_HOME
    # ANDROID_SDK_ROOT is deprecated; keep it consistent if already set.
    if [ -n "${ANDROID_SDK_ROOT:-}" ]; then export ANDROID_SDK_ROOT="$ANDROID_HOME"; fi
    _underlight_prepend_path "$ANDROID_HOME/cmdline-tools/latest/bin"
    _underlight_prepend_path "$ANDROID_HOME/emulator"
    _underlight_prepend_path "$ANDROID_HOME/platform-tools"
fi

if [ -z "${ANDROID_STUDIO_HOME:-}" ]; then
    for _underlight_dir in "$HOME/.local/share/underlight/android-studio" \
        /opt/android-studio /usr/share/android-studio "$HOME/android-studio" \
        "$HOME"/android-studio*/android-studio "$HOME"/android-studio*; do
        if [ -x "$_underlight_dir/bin/studio" ] || [ -x "$_underlight_dir/bin/studio.sh" ]; then
            ANDROID_STUDIO_HOME=$_underlight_dir
            break
        fi
    done
fi
if [ -n "${ANDROID_STUDIO_HOME:-}" ]; then export ANDROID_STUDIO_HOME; fi

if [ -z "${FLUTTER_ROOT:-}" ] && ! command -v flutter >/dev/null 2>&1; then
    for _underlight_dir in "$HOME/develop/flutter" "$HOME/flutter" \
        "$HOME/projects/flutter" "$HOME/.local/share/underlight/flutter"; do
        if [ -x "$_underlight_dir/bin/flutter" ]; then
            FLUTTER_ROOT=$_underlight_dir
            break
        fi
    done
fi
if [ -n "${FLUTTER_ROOT:-}" ]; then
    export FLUTTER_ROOT
    _underlight_prepend_path "$FLUTTER_ROOT/bin"
fi
unset _underlight_dir
}
_underlight_android_environment
unset -f _underlight_android_environment _underlight_prepend_path
