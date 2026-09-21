#include "ec_interface.h"
#include "fan_curve_manager.h"
#include <iostream>
#include <iomanip>
#include <vector>
#include <string>
#include <cstdlib>
#include <charconv>

namespace msi_ec {

void print_usage(const char* prog) {
    std::cout << "Usage: " << prog << " <command> [args...]\n\n";
    std::cout << "Commands:\n";
    std::cout << "  info                    Show model info and current status\n";
    std::cout << "  curve read              Read current fan curve\n";
    std::cout << "  curve write <preset>    Write preset curve (default/performance/silent/balanced/max_cooling)\n";
    std::cout << "  curve set <t1> <f1> [t2 f2 ...]  Set custom curve points\n";
    std::cout << "  curve reset             Restore firmware automatic fan control\n";
    std::cout << "  mode get                Get current fan mode\n";
    std::cout << "  mode set <auto|silent|basic|advanced>  Set fan mode\n";
    std::cout << "  thermal                 Show current temperatures and fan speeds\n";
    std::cout << "  shift get               Get current shift mode\n";
    std::cout << "  shift set <eco|comfort|sport|turbo>  Set shift mode\n";
    std::cout << "  scan                    Scan EC memory for fan curve addresses\n";
    std::cout << "  dump <file>             Dump full EC memory to CSV\n";
    std::cout << "  models                  List supported models\n";
}

int cmd_info(std::shared_ptr<FanCurveManager> mgr) {
    std::cout << "Model: " << mgr->current_model_id() << "\n";
    if (auto cfg = mgr->current_config()) {
        std::cout << "Curve base: 0x" << std::hex << cfg->curve_base_addr << std::dec << "\n";
        std::cout << "Points: " << static_cast<int>(cfg->num_points) << "\n";
        std::cout << "Fan mode addr: 0x" << std::hex << cfg->fan_mode_addr << std::dec << "\n";
        std::cout << "CPU temp: 0x" << std::hex << cfg->cpu_temp_addr << std::dec << "\n";
        std::cout << "GPU temp: 0x" << std::hex << cfg->gpu_temp_addr << std::dec << "\n";
    }
    std::cout << "Fan curves: " << mgr->curve_unavailable_reason() << "\n";
    auto thermal = mgr->read_thermal_data();
    std::cout << "CPU: " << static_cast<int>(thermal.cpu_temp) << "°C, Fan: " << static_cast<int>(thermal.cpu_fan_pct) << "%\n";
    std::cout << "GPU: " << static_cast<int>(thermal.gpu_temp) << "°C, Fan: " << static_cast<int>(thermal.gpu_fan_pct) << "%\n";
    if (auto mode = mgr->read_fan_mode()) {
        std::cout << "Fan mode: ";
        switch (*mode) {
            case FanMode::AUTO: std::cout << "auto"; break;
            case FanMode::SILENT: std::cout << "silent"; break;
            case FanMode::BASIC: std::cout << "basic"; break;
            case FanMode::ADVANCED: std::cout << "advanced"; break;
            default: std::cout << "unknown";
        }
        std::cout << "\n";
    }
    return 0;
}

int cmd_curve_read(std::shared_ptr<FanCurveManager> mgr) {
    if (auto curve = mgr->read_curve()) {
        std::cout << "Current fan curve:\n";
        std::cout << "  Temp(°C)  Fan(%)\n";
        for (const auto& p : curve->points) {
            std::cout << "    " << std::setw(3) << static_cast<int>(p.temp_c)
                      << "      " << std::setw(3) << static_cast<int>(p.fan_pct) << "\n";
        }
    } else {
        std::cerr << mgr->last_error() << "\n";
        return 1;
    }
    return 0;
}

int cmd_curve_write(std::shared_ptr<FanCurveManager> mgr, const std::string& preset) {
    auto curve = mgr->preset_for_hardware(preset);
    if (!curve) {
        std::cerr << mgr->last_error() << "\n";
        return 1;
    }

    if (mgr->apply_curve(*curve)) {
        std::cout << "Applied " << preset << " curve and set advanced mode\n";
        return 0;
    }
    std::cerr << mgr->last_error() << "\n";
    return 1;
}

int cmd_curve_set(std::shared_ptr<FanCurveManager> mgr, int argc, char* argv[]) {
    if (argc % 2 != 0) {
        std::cerr << "Need pairs of temp fan values\n";
        return 1;
    }

    FanCurve curve;
    for (int i = 0; i < argc; i += 2) {
        int temp = -1, fan = -1;
        auto parse = [](const char* text, int& value) {
            const auto end = text + std::char_traits<char>::length(text);
            const auto result = std::from_chars(text, end, value);
            return result.ec == std::errc{} && result.ptr == end;
        };
        if (!parse(argv[i], temp) || !parse(argv[i+1], fan)) {
            std::cerr << "Curve values must be integers\n";
            return 1;
        }
        if (temp < 0 || temp > 100 || fan < 0 || fan > 100) {
            std::cerr << "Values must be 0-100\n";
            return 1;
        }
        curve.points.push_back({static_cast<uint8_t>(temp), static_cast<uint8_t>(fan)});
    }
    curve.valid = true;

    if (!mgr->validate_curve(curve)) {
        std::cerr << "Invalid curve: temps must be strictly increasing\n";
        return 1;
    }

    if (mgr->apply_curve(curve)) {
        std::cout << "Applied custom curve and set advanced mode\n";
        return 0;
    }
    std::cerr << mgr->last_error() << "\n";
    return 1;
}

int cmd_curve_reset(std::shared_ptr<FanCurveManager> mgr) {
    if (mgr->reset_to_default()) {
        std::cout << "Firmware automatic fan control restored and verified\n";
        return 0;
    }
    std::cerr << "Failed to reset curve\n";
    return 1;
}

int cmd_mode_get(std::shared_ptr<FanCurveManager> mgr) {
    if (auto mode = mgr->read_fan_mode()) {
        switch (*mode) {
            case FanMode::AUTO: std::cout << "auto\n"; break;
            case FanMode::SILENT: std::cout << "silent\n"; break;
            case FanMode::BASIC: std::cout << "basic\n"; break;
            case FanMode::ADVANCED: std::cout << "advanced\n"; break;
            default: std::cout << "unknown\n";
        }
    }
    return 0;
}

int cmd_mode_set(std::shared_ptr<FanCurveManager> mgr, const std::string& mode) {
    FanMode fm;
    if (mode == "auto") fm = FanMode::AUTO;
    else if (mode == "silent") fm = FanMode::SILENT;
    else if (mode == "basic") fm = FanMode::BASIC;
    else if (mode == "advanced") fm = FanMode::ADVANCED;
    else {
        std::cerr << "Invalid mode: " << mode << "\n";
        return 1;
    }

    if (mgr->write_fan_mode(fm)) {
        std::cout << "Set fan mode to " << mode << "\n";
        return 0;
    }
    std::cerr << "Failed to set mode\n";
    return 1;
}

int cmd_thermal(std::shared_ptr<FanCurveManager> mgr) {
    auto data = mgr->read_thermal_data();
    std::cout << "CPU: " << static_cast<int>(data.cpu_temp) << "°C (" << static_cast<int>(data.cpu_fan_pct) << "%)\n";
    std::cout << "GPU: " << static_cast<int>(data.gpu_temp) << "°C (" << static_cast<int>(data.gpu_fan_pct) << "%)\n";
    return 0;
}

int cmd_shift_get(std::shared_ptr<FanCurveManager> mgr) {
    auto ec = std::dynamic_pointer_cast<SysfsEC>(mgr->get_ec_interface());
    if (!ec) return 1;
    if (auto val = ec->read_shift_mode_str()) {
        std::cout << *val << "\n";
        return 0;
    }
    std::cerr << "Cannot read shift mode\n";
    return 1;
}

int cmd_shift_set(std::shared_ptr<FanCurveManager> mgr, const std::string& value) {
    auto ec = std::dynamic_pointer_cast<SysfsEC>(mgr->get_ec_interface());
    std::string error;
    if (ec && ec->apply_controls({{"shift_mode", value}}, error)) {
        std::cout << "Shift mode verified: " << value << "\n";
        return 0;
    }
    std::cerr << "Shift mode failed: " << error << "\n";
    return 1;
}

int cmd_scan(std::shared_ptr<FanCurveManager> mgr) {
    if (!mgr->current_config()) return 1;
    auto ec = mgr->get_ec_interface();
    if (!ec) return 1;
    ECScanner scanner(ec);
    auto candidates = scanner.find_fan_curve_candidates();
    std::cout << "Possible fan curve addresses:\n";
    for (const auto& c : candidates) {
        std::cout << "  " << c.addr << " (" << c.name << "): " << c.description << "\n";
    }
    return 0;
}

int cmd_dump(std::shared_ptr<FanCurveManager> mgr, const std::string& file) {
    if (!mgr->current_config()) return 1;
    auto ec = mgr->get_ec_interface();
    if (!ec) return 1;
    ECScanner scanner(ec);
    scanner.dump_full_ec(file);
    std::cout << "Dumped EC memory to " << file << "\n";
    return 0;
}

int cmd_models() {
    auto& db = ModelDatabase::instance();
    db.load_builtin();
    std::cout << "Known firmware entries (fan-curve layouts are unverified):\n";
    for (const auto& cfg : db.all_configs()) {
        std::cout << "  " << cfg.model_id << " (FW: " << cfg.firmware_pattern << ")\n";
    }
    return 0;
}

} // namespace msi_ec

int main(int argc, char* argv[]) {
    if (argc < 2) {
        msi_ec::print_usage(argv[0]);
        return 1;
    }

    if (std::string(argv[1]) == "models") return msi_ec::cmd_models();
    if (std::string(argv[1]) == "--help") { msi_ec::print_usage(argv[0]); return 0; }

    auto ec_ptr = msi_ec::create_best_backend();
    if (!ec_ptr) {
        std::cerr << "No EC backend available. Run as root or load msi-ec kernel module.\n";
        return 1;
    }

    auto ec = std::shared_ptr<msi_ec::ECInterface>(ec_ptr.release());
    auto mgr = std::make_shared<msi_ec::FanCurveManager>(ec);

    // Try to detect model
    std::string fw;
    for (int i = 0; i < 12; ++i) {
        if (auto val = ec->read_byte(0xa0 + i)) {
            if (*val == 0) break;
            fw += static_cast<char>(*val);
        }
    }
    if (!fw.empty()) {
        mgr->detect_model(fw);
    }

    std::string cmd = argv[1];

    if (cmd == "info") return msi_ec::cmd_info(mgr);
    if (cmd == "curve") {
        if (argc < 3) { msi_ec::print_usage(argv[0]); return 1; }
        std::string sub = argv[2];
        if (sub == "read") return msi_ec::cmd_curve_read(mgr);
        if (sub == "write") return msi_ec::cmd_curve_write(mgr, argc > 3 ? argv[3] : "default");
        if (sub == "set") return msi_ec::cmd_curve_set(mgr, argc - 3, argv + 3);
        if (sub == "reset") return msi_ec::cmd_curve_reset(mgr);
    }
    if (cmd == "mode") {
        if (argc < 3) { msi_ec::print_usage(argv[0]); return 1; }
        std::string sub = argv[2];
        if (sub == "get") return msi_ec::cmd_mode_get(mgr);
        if (sub == "set") return msi_ec::cmd_mode_set(mgr, argc > 3 ? argv[3] : "");
    }
    if (cmd == "thermal") return msi_ec::cmd_thermal(mgr);
    if (cmd == "shift") {
        if (argc < 3) { msi_ec::print_usage(argv[0]); return 1; }
        std::string sub = argv[2];
        if (sub == "get") return msi_ec::cmd_shift_get(mgr);
        if (sub == "set" && argc > 3) return msi_ec::cmd_shift_set(mgr, argv[3]);
    }
    if (cmd == "scan") return msi_ec::cmd_scan(mgr);
    if (cmd == "dump") return msi_ec::cmd_dump(mgr, argc > 2 ? argv[2] : "/tmp/ec_dump.csv");
    if (cmd == "models") return msi_ec::cmd_models();

    msi_ec::print_usage(argv[0]);
    return 1;
}
