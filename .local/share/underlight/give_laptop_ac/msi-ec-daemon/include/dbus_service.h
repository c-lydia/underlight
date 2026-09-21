#pragma once

#include "fan_curve_manager.h"
#include <systemd/sd-bus.h>

namespace msi_ec {

class DBusService {
public:
    explicit DBusService(std::shared_ptr<FanCurveManager> manager);
    ~DBusService();
    bool register_service(bool session = false);
    int process();
    void wait();

private:
    std::shared_ptr<FanCurveManager> manager_;
    std::shared_ptr<SysfsEC> sysfs_;
    sd_bus* bus_ = nullptr;
    sd_bus_slot* slot_ = nullptr;
    static int dispatch(sd_bus_message* message, void* userdata, sd_bus_error* error);
    int handle(sd_bus_message* message, sd_bus_error* error);
};

} // namespace msi_ec
