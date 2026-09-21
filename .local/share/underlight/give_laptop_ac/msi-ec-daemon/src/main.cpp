#include "dbus_service.h"
#include <csignal>
#include <iostream>

namespace { volatile std::sig_atomic_t stopping = 0; }
void stop(int) { stopping = 1; }

int main(int argc, char* argv[]) {
    bool session = false;
    std::string sysfs_path = "/sys/devices/platform/msi-ec";
    std::string ec_io;
    for (int i = 1; i < argc; ++i) {
        const std::string arg(argv[i]);
        if (arg == "--session") session = true;
        else if (arg == "--sysfs" && i + 1 < argc) sysfs_path = argv[++i];
        else if (arg == "--ec-io" && i + 1 < argc) ec_io = argv[++i];
        else {
            std::cerr << "Usage: msi-ec-daemon [--session] [--sysfs PATH] [--ec-io PATH]\n";
            return arg == "--help" ? 0 : 1;
        }
    }
    auto ec = std::make_shared<msi_ec::SysfsEC>(sysfs_path, ec_io);
    if (!ec->initialize()) {
        std::cerr << "msi-ec sysfs interface unavailable at " << sysfs_path << '\n';
        return 1;
    }
    auto manager = std::make_shared<msi_ec::FanCurveManager>(ec);
    manager->detect_model(ec->read_firmware_version().value_or(""));
    msi_ec::DBusService bus(manager);
    if (!bus.register_service(session)) return 1;
    std::signal(SIGINT, stop);
    std::signal(SIGTERM, stop);
    std::cout << "MSI EC service ready on " << (session ? "session" : "system") << " bus\n" << std::flush;
    while (!stopping) {
        const int result = bus.process();
        if (result < 0) { std::cerr << "D-Bus connection lost\n"; return 1; }
        if (result == 0) bus.wait();
    }
    return 0;
}
