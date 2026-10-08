# shellcheck shell=sh
# Shared startup hook for Bash and Zsh.
for _underlight_environment in cuda android; do
    if [ -r "${XDG_CONFIG_HOME:-$HOME/.config}/underlight/$_underlight_environment.sh" ]; then
        # shellcheck disable=SC1090
        . "${XDG_CONFIG_HOME:-$HOME/.config}/underlight/$_underlight_environment.sh"
    fi
done
unset _underlight_environment
