#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo to install the system-bus service." >&2
    exit 1
fi
if [ ! -x build/msi-ec-daemon ] || [ ! -f build/msi-ec-daemon.service ]; then
    echo "Build first: ./build.sh Release" >&2
    exit 1
fi

start_service=false
enable_curves=false
for option in "$@"; do
    case "$option" in
        --start) start_service=true ;;
        --enable-curves) enable_curves=true ;;
        *) echo "Unknown option: $option" >&2; exit 1 ;;
    esac
done
if $enable_curves; then
    if [ "$(cat /sys/devices/platform/msi-ec/fw_version)" != "15K1IMS1.113" ]; then
        echo "Curve setup currently supports only firmware 15K1IMS1.113." >&2
        exit 1
    fi
    modprobe ec_sys write_support=1
    # Support an already loaded module without unloading another application's driver.
    if [ "$(cat /sys/module/ec_sys/parameters/write_support)" != Y ]; then
        printf 'Y' > /sys/module/ec_sys/parameters/write_support
    fi
    install -d /etc/modules-load.d /etc/modprobe.d
    printf 'ec_sys\n' > /etc/modules-load.d/give-laptop-ac-curves.conf
    printf 'options ec_sys write_support=1\n' > /etc/modprobe.d/give-laptop-ac-curves.conf
fi

getent group msi-ec >/dev/null || groupadd --system msi-ec
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    usermod -a -G msi-ec "$SUDO_USER"
fi
# CMake generates the service with the same prefix used to install the binary.
cmake --install build
install -Dm644 build/msi-ec-daemon.service /etc/systemd/system/msi-ec-daemon.service
install -Dm644 systemd/com.msi_ec.FanControl.conf /etc/dbus-1/system.d/com.msi_ec.FanControl.conf
systemctl daemon-reload
if $start_service; then
    systemctl enable msi-ec-daemon.service
    systemctl restart msi-ec-daemon.service
fi

echo "Installed. Start with: sudo systemctl enable --now msi-ec-daemon"
echo "After joining msi-ec, log out and back in. Open Controls and select Reconnect."
