# shellcheck shell=sh
# Shared CUDA environment for Bash, Zsh, and Underlight GPU launches.
# Respect an explicitly selected toolkit; otherwise use the system alternative.
# Machines without this toolkit keep their distribution-provided PATH.
if [ -x "${CUDA_HOME:-/usr/local/cuda}/bin/nvcc" ]; then
    export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
    export CUDA_PATH="$CUDA_HOME"
    case ${PATH-} in
        "$CUDA_HOME/bin"|"$CUDA_HOME/bin":*) ;;
        *) export PATH="$CUDA_HOME/bin${PATH:+:$PATH}" ;;
    esac
    # Never add lib64/stubs: those libraries cannot drive a real GPU.
    if [ -d "$CUDA_HOME/lib64" ]; then
        case ${LD_LIBRARY_PATH-} in
            "$CUDA_HOME/lib64"|"$CUDA_HOME/lib64":*) ;;
            *) export LD_LIBRARY_PATH="$CUDA_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;;
        esac
    fi
fi
