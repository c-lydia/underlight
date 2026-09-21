#include "dbus_service.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>

namespace msi_ec {
namespace {
constexpr auto service = "com.msi_ec.FanControl";
constexpr auto object = "/com/msi_ec/FanControl";

void check(int result) {
    if (result < 0) throw std::runtime_error(strerror(-result));
}

using Message = std::unique_ptr<sd_bus_message, decltype(&sd_bus_message_unref)>;
Message reply_to(sd_bus_message* call) {
    sd_bus_message* reply = nullptr;
    check(sd_bus_message_new_method_return(call, &reply));
    return Message(reply, sd_bus_message_unref);
}

int string_map(sd_bus_message* call, const std::map<std::string, std::string>& values) {
    auto reply = reply_to(call);
    check(sd_bus_message_open_container(reply.get(), 'a', "{ss}"));
    for (const auto& [key, value] : values)
        check(sd_bus_message_append(reply.get(), "{ss}", key.c_str(), value.c_str()));
    check(sd_bus_message_close_container(reply.get()));
    return sd_bus_send(nullptr, reply.get(), nullptr);
}

int strings(sd_bus_message* call, const std::vector<std::string>& values) {
    auto reply = reply_to(call);
    check(sd_bus_message_open_container(reply.get(), 'a', "s"));
    for (const auto& value : values) check(sd_bus_message_append(reply.get(), "s", value.c_str()));
    check(sd_bus_message_close_container(reply.get()));
    return sd_bus_send(nullptr, reply.get(), nullptr);
}
} // namespace

DBusService::DBusService(std::shared_ptr<FanCurveManager> manager)
    : manager_(std::move(manager)), sysfs_(std::dynamic_pointer_cast<SysfsEC>(manager_->get_ec_interface())) {}

DBusService::~DBusService() {
    sd_bus_slot_unref(slot_);
    sd_bus_flush_close_unref(bus_);
}

bool DBusService::register_service(bool session) {
    // The system-bus policy restricts writes to root and the msi-ec group.
    static const sd_bus_vtable vtable[] = {
        SD_BUS_VTABLE_START(0),
        SD_BUS_METHOD("GetCapabilities", "", "a{ss}", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("GetFirmwareVersion", "", "s", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("GetModelId", "", "s", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ListFanModes", "", "as", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ListShiftModes", "", "as", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ReadFanMode", "", "s", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ReadShiftMode", "", "s", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ReadControl", "s", "s", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("WriteFanMode", "s", "b", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("WriteShiftMode", "s", "b", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ApplyControls", "a{ss}", "b", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("ReadCurve", "", "a(yy)", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("WriteCurve", "a(yy)", "b", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_METHOD("SetCurvePreset", "s", "b", dispatch, SD_BUS_VTABLE_UNPRIVILEGED),
        SD_BUS_VTABLE_END
    };
    try {
        if (!sysfs_) throw std::runtime_error("The service requires the msi-ec sysfs backend");
        check(session ? sd_bus_open_user(&bus_) : sd_bus_open_system(&bus_));
        check(sd_bus_add_object_vtable(bus_, &slot_, object, service, vtable, this));
        check(sd_bus_request_name(bus_, service, 0));
        return true;
    } catch (const std::exception& e) {
        std::cerr << "D-Bus: " << e.what() << '\n';
        return false;
    }
}

int DBusService::process() { return sd_bus_process(bus_, nullptr); }
void DBusService::wait() { sd_bus_wait(bus_, 500000); }

int DBusService::dispatch(sd_bus_message* call, void* userdata, sd_bus_error* error) {
    try { return static_cast<DBusService*>(userdata)->handle(call, error); }
    catch (const std::exception& e) {
        return sd_bus_error_setf(error, "com.msi_ec.Error.Failed", "%s", e.what());
    }
}

int DBusService::handle(sd_bus_message* call, sd_bus_error* error) {
    const std::string method = sd_bus_message_get_member(call);
    if (method == "GetCapabilities") {
        std::string reason = manager_->curve_unavailable_reason();
        if (reason.empty() && !manager_->read_curve()) reason = manager_->last_error();
        return string_map(call, {
            {"protocol_version", "1"}, {"backend", "sysfs"},
            {"firmware", sysfs_->read_firmware_version().value_or("unknown")},
            {"curve_read", reason.empty() ? "true" : "false"},
            {"curve_write", reason.empty() && sysfs_->raw_ec_writable() ? "true" : "false"},
            {"curve_reason", reason.empty() && !sysfs_->raw_ec_writable() ? "EC interface is read-only; enable ec_sys write_support=1" : reason},
        });
    }
    if (method == "GetFirmwareVersion")
        return sd_bus_reply_method_return(call, "s", sysfs_->read_firmware_version().value_or("unknown").c_str());
    if (method == "GetModelId")
        return sd_bus_reply_method_return(call, "s", manager_->current_model_id().c_str());
    if (method == "ListFanModes" || method == "ListShiftModes")
        return strings(call, sysfs_->available_values(method == "ListFanModes" ? "available_fan_modes" : "available_shift_modes"));
    if (method == "ReadFanMode" || method == "ReadShiftMode" || method == "ReadControl") {
        const char* attr = method == "ReadFanMode" ? "fan_mode" : "shift_mode";
        if (method == "ReadControl") check(sd_bus_message_read(call, "s", &attr));
        const std::vector<std::string> allowed = {"fan_mode", "shift_mode", "cooler_boost", "super_battery", "webcam", "fn_key", "win_key"};
        if (std::find(allowed.begin(), allowed.end(), attr) == allowed.end())
            return sd_bus_error_set_const(error, SD_BUS_ERROR_INVALID_ARGS, "Unsupported control");
        auto value = sysfs_->read_string_attr(attr);
        if (!value) throw std::runtime_error(std::string("Cannot read ") + attr);
        return sd_bus_reply_method_return(call, "s", value->c_str());
    }
    if (method == "WriteFanMode" || method == "WriteShiftMode" || method == "ApplyControls") {
        std::map<std::string, std::string> changes;
        const char *attr, *value;
        if (method == "ApplyControls") {
            check(sd_bus_message_enter_container(call, 'a', "{ss}"));
            int result;
            while ((result = sd_bus_message_read(call, "{ss}", &attr, &value)) > 0) {
                if (!changes.emplace(attr, value).second || changes.size() > 7)
                    return sd_bus_error_set_const(error, SD_BUS_ERROR_INVALID_ARGS, "Duplicate or too many controls");
            }
            check(result);
            check(sd_bus_message_exit_container(call));
            if (changes.empty()) return sd_bus_error_set_const(error, SD_BUS_ERROR_INVALID_ARGS, "No controls supplied");
        } else {
            check(sd_bus_message_read(call, "s", &value));
            changes[method == "WriteFanMode" ? "fan_mode" : "shift_mode"] = value;
        }
        std::string reason;
        if (!sysfs_->apply_controls(changes, reason)) throw std::runtime_error(reason);
        return sd_bus_reply_method_return(call, "b", 1);
    }
    if (method == "ReadCurve") {
        auto curve = manager_->read_curve();
        if (!curve) return sd_bus_error_setf(error, SD_BUS_ERROR_NOT_SUPPORTED, "%s", manager_->last_error().c_str());
        auto reply = reply_to(call);
        check(sd_bus_message_open_container(reply.get(), 'a', "(yy)"));
        for (const auto& point : curve->points)
            check(sd_bus_message_append(reply.get(), "(yy)", point.temp_c, point.fan_pct));
        check(sd_bus_message_close_container(reply.get()));
        return sd_bus_send(nullptr, reply.get(), nullptr);
    }
    FanCurve curve;
    if (method == "WriteCurve") {
        check(sd_bus_message_enter_container(call, 'a', "(yy)"));
        uint8_t temp, fan;
        int result;
        while ((result = sd_bus_message_read(call, "(yy)", &temp, &fan)) > 0) {
            curve.points.push_back({temp, fan});
            if (curve.points.size() > FanCurve::MAX_POINTS)
                return sd_bus_error_set_const(error, SD_BUS_ERROR_INVALID_ARGS, "Too many curve points");
        }
        check(result);
        check(sd_bus_message_exit_container(call));
    } else if (method == "SetCurvePreset") {
        const char* name;
        check(sd_bus_message_read(call, "s", &name));
        auto preset = manager_->preset_for_hardware(name);
        if (!preset) throw std::runtime_error(manager_->last_error());
        curve = *preset;
    } else return sd_bus_error_set_const(error, SD_BUS_ERROR_UNKNOWN_METHOD, "Unknown method");
    if (!manager_->apply_curve(curve)) throw std::runtime_error(manager_->last_error());
    return sd_bus_reply_method_return(call, "b", 1);
}

} // namespace msi_ec
