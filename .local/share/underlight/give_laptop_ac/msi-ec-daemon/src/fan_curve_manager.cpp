#include "fan_curve_manager.h"
#include <fstream>
#include <sstream>
#include <algorithm>
#include <iostream>

namespace msi_ec {

ModelDatabase& ModelDatabase::instance() {
    static ModelDatabase db;
    return db;
}

void ModelDatabase::add_builtin_configs() {
    configs_.clear();

    configs_.push_back({
        "GE66_10SF", "1541EMS1.113",
        0x50, 10, 0xf4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "GP66_11UG", "1543EMS1.108",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "GS66_11UG", "16V4EMS1.115",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "GE76_11UH", "17K3EMS1.113",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Creator_15_A10SD", "16V2EMS1.104",
        0x50, 10, 0xf4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Prestige_14_A10SC", "14C1EMS1.012",
        0x50, 10, 0xf4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Prestige_15_A11SC", "16S6EMS1.114",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Stealth_14_A13VF", "14K1EMS1.108",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Katana_GF66_11UE", "1581EMS1.107",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "GF63_Thin_11UC", "16R6EMS1.107",
        0x50, 10, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, false
    });

    configs_.push_back({
        "Raider_GE68_HX", "15M1IMS1.110",
        0x50, 12, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Titan_GT77_HX", "17Q2IMS1.107",
        0x50, 12, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Vector_GP68_HX", "15M1IMS1.113",
        0x50, 12, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, true
    });

    configs_.push_back({
        "Cyborg_15", "15K1IMS1.113",
        // Six speed steps, separate from read-only temperature thresholds.
        // See docs/cyborg-fan-layout.md for the firmware dump and register sources.
        0, 6, 0xd4, 0x8d,
        0x68, 0x80, 0x71, 0x89, false, true, 0x6a, 0x72, true
    });
}

bool ModelDatabase::load_builtin() {
    add_builtin_configs();
    return !configs_.empty();
}

bool ModelDatabase::load_from_json(const std::string& path) {
    (void)path;
    // JSON parsing disabled - use load_builtin() instead
    return false;
}

std::optional<ModelFanCurveConfig> ModelDatabase::find_by_firmware(const std::string& fw_version) const {
    for (const auto& cfg : configs_) {
        if (!fw_version.empty() && fw_version == cfg.firmware_pattern) {
            return cfg;
        }
    }
    return std::nullopt;
}

std::optional<ModelFanCurveConfig> ModelDatabase::find_by_model_id(const std::string& model_id) const {
    for (const auto& cfg : configs_) {
        if (cfg.model_id == model_id) return cfg;
    }
    return std::nullopt;
}

FanCurveManager::FanCurveManager(std::shared_ptr<ECInterface> ec) : ec_(std::move(ec)) {
    ModelDatabase::instance().load_builtin();
}

FanCurveManager::~FanCurveManager() = default;

bool FanCurveManager::detect_model(const std::string& fw_version) {
    current_config_.reset();
    cache_valid_ = false;
    auto& db = ModelDatabase::instance();
    if (auto cfg = db.find_by_firmware(fw_version)) {
        return set_model_config(*cfg);
    }
    return false;
}

bool FanCurveManager::set_model_config(const ModelFanCurveConfig& config) {
    if (config.num_points < 2 || config.num_points > FanCurve::MAX_POINTS ||
        config.curve_base_addr + config.num_points * 2 > 256) return false;
    current_config_ = config;
    cache_valid_ = false;
    return true;
}

uint16_t FanCurveManager::curve_point_addr(size_t index) const {
    if (!current_config_) return 0;
    return current_config_->curve_base_addr + index * 2;
}

bool FanCurveManager::read_curve_point(size_t index, FanCurvePoint& point) {
    if (!current_config_ || index >= current_config_->num_points) return false;

    uint16_t addr = current_config_->temperature_base_addr
        ? current_config_->temperature_base_addr + index : curve_point_addr(index);
    uint16_t fan_addr = current_config_->speed_base_addr
        ? current_config_->speed_base_addr + index : addr + 1;
    uint8_t temp, fan;

    if (auto val = ec_->read_byte(addr)) temp = *val;
    else return false;

    if (auto val = ec_->read_byte(fan_addr)) fan = *val;
    else return false;

    point.temp_c = temp;
    point.fan_pct = fan;
    return true;
}

bool FanCurveManager::write_curve_point(size_t index, const FanCurvePoint& point) {
    if (!current_config_ || index >= current_config_->num_points) return false;
    if (current_config_->fixed_temperatures) {
        return ec_->read_byte(current_config_->temperature_base_addr + index) == point.temp_c &&
               ec_->write_byte(current_config_->speed_base_addr + index, point.fan_pct);
    }

    uint16_t addr = curve_point_addr(index);
    return ec_->write_byte(addr, point.temp_c) && ec_->write_byte(addr + 1, point.fan_pct);
}

std::optional<FanCurve> FanCurveManager::read_curve() {
    last_error_ = curve_unavailable_reason();
    if (!last_error_.empty()) return std::nullopt;

    FanCurve curve;
    curve.points.reserve(current_config_->num_points);

    for (size_t i = 0; i < current_config_->num_points; ++i) {
        FanCurvePoint point;
        if (read_curve_point(i, point)) {
            curve.points.push_back(point);
        } else {
            last_error_ = "Cannot read fan curve; check driver access";
            return std::nullopt;
        }
    }
    if (!validate_curve(curve)) {
        last_error_ = "Hardware returned an invalid curve";
        return std::nullopt;
    }
    curve.valid = true;
    cached_curve_ = curve;
    cache_valid_ = true;
    return curve;
}

bool FanCurveManager::write_curve(const FanCurve& curve) {
    last_error_ = curve_unavailable_reason();
    if (!last_error_.empty()) return false;
    if (curve.points.size() != current_config_->num_points || !validate_curve(curve)) {
        last_error_ = "Invalid fan curve or point count";
        return false;
    }
    auto before = read_curve();
    if (!before) return false;
    if (!ec_->raw_ec_writable()) {
        last_error_ = "EC interface is read-only; enable ec_sys write_support=1";
        return false;
    }
    if (current_config_->fixed_temperatures) {
        for (size_t i = 0; i < curve.points.size(); ++i) {
            if (curve.points[i].temp_c != before->points[i].temp_c) {
                last_error_ = "This firmware uses fixed temperature steps";
                return false;
            }
        }
        if (curve.points.back().fan_pct != 100) {
            last_error_ = "The hottest fan step must remain at 100%";
            return false;
        }
    }

    bool ok = true;
    for (size_t i = 0; i < curve.points.size(); ++i) {
        if (!write_curve_point(i, curve.points[i])) { ok = false; break; }
    }
    auto matches = [this](const FanCurve& expected) {
        auto actual = read_curve();
        if (!actual || actual->points.size() != expected.points.size()) return false;
        for (size_t i = 0; i < expected.points.size(); ++i) {
            if (actual->points[i].temp_c != expected.points[i].temp_c ||
                actual->points[i].fan_pct != expected.points[i].fan_pct) return false;
        }
        return true;
    };
    if (!ok || !matches(curve)) {
        for (size_t i = 0; i < before->points.size(); ++i) write_curve_point(i, before->points[i]);
        const bool restored = matches(*before);
        last_error_ = restored ? "Curve write failed; previous curve restored" : "Curve write failed; rollback failed, check hardware state";
        return false;
    }
    cached_curve_ = curve;
    cache_valid_ = true;
    return true;
}

bool FanCurveManager::reset_to_default() {
    // Returning control to firmware is a reset; a fabricated curve is not.
    return write_fan_mode(FanMode::AUTO);
}

std::string FanCurveManager::curve_unavailable_reason() const {
    if (!ec_->supports_raw_ec()) return "Fan-curve driver unavailable; enable ec_sys (see Setup)";
    if (!current_config_ || !current_config_->curve_layout_verified)
        return "No verified fan-curve layout for this firmware";
    return {};
}

std::optional<FanCurve> FanCurveManager::preset_for_hardware(const std::string& preset) {
    FanCurve source;
    if (preset == "performance") source = create_performance_curve();
    else if (preset == "silent") source = create_silent_curve();
    else if (preset == "balanced") source = create_balanced_curve();
    else if (preset == "default") source = create_default_curve();
    else if (preset == "max_cooling") source = create_max_cooling_curve();
    else { last_error_ = "Unknown curve preset"; return std::nullopt; }
    if (!current_config_ || !current_config_->fixed_temperatures) return source;
    auto curve = read_curve();
    if (!curve) return std::nullopt;
    for (auto& point : curve->points) {
        point.fan_pct = source.points.back().fan_pct;
        if (point.temp_c <= source.points.front().temp_c) point.fan_pct = source.points.front().fan_pct;
        else for (size_t i = 1; i < source.points.size(); ++i) {
            const auto a = source.points[i-1], b = source.points[i];
            if (point.temp_c <= b.temp_c) {
                point.fan_pct = a.fan_pct + (b.fan_pct - a.fan_pct) * (point.temp_c - a.temp_c) / (b.temp_c - a.temp_c);
                break;
            }
        }
    }
    curve->points.back().fan_pct = 100;
    return curve;
}

bool FanCurveManager::apply_curve(const FanCurve& curve) {
    auto before = read_curve();
    auto mode = read_fan_mode();
    if (!before || !mode || *mode == FanMode::UNKNOWN) {
        if (last_error_.empty()) last_error_ = "Cannot read current curve and fan mode";
        return false;
    }
    if (!write_curve(curve)) return false;
    if (set_advanced_mode()) return true;
    const bool curve_restored = write_curve(*before);
    const bool mode_restored = write_fan_mode(*mode);
    last_error_ = curve_restored && mode_restored
        ? "Advanced mode failed; previous curve and mode restored"
        : "Advanced mode failed; rollback failed, check hardware state";
    return false;
}

std::optional<FanMode> FanCurveManager::read_fan_mode() {
    if (auto sysfs = std::dynamic_pointer_cast<SysfsEC>(ec_)) {
        auto mode = sysfs->read_fan_mode_str();
        if (!mode) return std::nullopt;
        if (*mode == "auto") return FanMode::AUTO;
        if (*mode == "silent") return FanMode::SILENT;
        if (*mode == "basic") return FanMode::BASIC;
        if (*mode == "advanced") return FanMode::ADVANCED;
        return FanMode::UNKNOWN;
    }
    if (!current_config_) return std::nullopt;

    if (auto val = ec_->read_byte(current_config_->fan_mode_addr)) {
        switch (*val) {
            case 0x0d: case 0x0c: return FanMode::AUTO;
            case 0x1d: return FanMode::SILENT;
            case 0x4d: case 0x4c: return FanMode::BASIC;
            case 0x8d: case 0x8c: return FanMode::ADVANCED;
            default: return FanMode::UNKNOWN;
        }
    }
    return std::nullopt;
}

bool FanCurveManager::write_fan_mode(FanMode mode) {
    if (auto sysfs = std::dynamic_pointer_cast<SysfsEC>(ec_)) {
        const std::map<FanMode, std::string> modes = {{FanMode::AUTO,"auto"}, {FanMode::SILENT,"silent"}, {FanMode::BASIC,"basic"}, {FanMode::ADVANCED,"advanced"}};
        auto it = modes.find(mode);
        if (it == modes.end()) return false;
        last_error_.clear();
        return sysfs->apply_controls({{"fan_mode", it->second}}, last_error_);
    }
    if (!current_config_) return false;

    uint8_t value = 0;
    switch (mode) {
        case FanMode::AUTO: value = 0x0d; break;
        case FanMode::SILENT: value = 0x1d; break;
        case FanMode::BASIC: value = 0x4d; break;
        case FanMode::ADVANCED: value = current_config_->fan_mode_advanced_val; break;
        default: return false;
    }
    return ec_->write_byte(current_config_->fan_mode_addr, value) && read_fan_mode() == mode;
}

bool FanCurveManager::set_advanced_mode() {
    return write_fan_mode(FanMode::ADVANCED);
}

ThermalData FanCurveManager::read_thermal_data() {
    ThermalData data;
    if (!current_config_) return data;

    if (auto val = ec_->read_byte(current_config_->cpu_temp_addr)) data.cpu_temp = *val;
    if (auto val = ec_->read_byte(current_config_->gpu_temp_addr)) data.gpu_temp = *val;
    if (auto val = ec_->read_byte(current_config_->cpu_fan_addr)) data.cpu_fan_pct = *val;
    if (auto val = ec_->read_byte(current_config_->gpu_fan_addr)) data.gpu_fan_pct = *val;
    return data;
}

bool FanCurveManager::validate_curve(const FanCurve& curve) const {
    if (curve.points.size() < 2 || curve.points.size() > FanCurve::MAX_POINTS) return false;

    for (size_t i = 0; i < curve.points.size(); ++i) {
        if (i && curve.points[i].temp_c <= curve.points[i-1].temp_c) return false;
        if (i && curve.points[i].fan_pct < curve.points[i-1].fan_pct) return false;
        if (curve.points[i].fan_pct > 100) return false;
        if (curve.points[i].temp_c > 100) return false;
    }
    return true;
}

FanCurve FanCurveManager::interpolate_curve(const FanCurve& curve) const {
    FanCurve result = curve;
    if (curve.points.size() < 2) return result;

    for (size_t i = 1; i < curve.points.size(); ++i) {
        auto& prev = result.points[i-1];
        auto& curr = result.points[i];
        int temp_diff = curr.temp_c - prev.temp_c;
        int fan_diff = curr.fan_pct - prev.fan_pct;

        if (temp_diff > 1) {
            for (int t = 1; t < temp_diff; ++t) {
                uint8_t interp_fan = prev.fan_pct + (fan_diff * t) / temp_diff;
                result.points.insert(result.points.begin() + i, {static_cast<uint8_t>(prev.temp_c + t), interp_fan});
            }
        }
    }
    result.valid = true;
    return result;
}

FanCurve FanCurveManager::create_default_curve() {
    FanCurve curve;
    curve.points = {
        {30, 0}, {35, 15}, {40, 25}, {45, 35}, {50, 45},
        {55, 55}, {60, 65}, {65, 75}, {70, 85}, {75, 100}
    };
    curve.valid = true;
    return curve;
}

FanCurve FanCurveManager::create_performance_curve() {
    FanCurve curve;
    curve.points = {
        {30, 20}, {35, 30}, {40, 40}, {45, 50}, {50, 60},
        {55, 70}, {60, 80}, {65, 90}, {70, 100}, {75, 100}
    };
    curve.valid = true;
    return curve;
}

FanCurve FanCurveManager::create_silent_curve() {
    FanCurve curve;
    curve.points = {
        {30, 0}, {40, 0}, {45, 10}, {50, 20}, {55, 30},
        {60, 40}, {65, 50}, {70, 60}, {75, 70}, {80, 100}
    };
    curve.valid = true;
    return curve;
}

FanCurve FanCurveManager::create_balanced_curve() {
    FanCurve curve;
    curve.points = {
        {30, 0}, {35, 10}, {40, 20}, {45, 30}, {50, 40},
        {55, 50}, {60, 60}, {65, 70}, {70, 80}, {75, 90}
    };
    curve.valid = true;
    return curve;
}

FanCurve FanCurveManager::create_max_cooling_curve() {
    FanCurve curve;
    curve.points = {
        {30, 60}, {35, 70}, {40, 80}, {45, 90}, {50, 100},
        {55, 100}, {60, 100}, {65, 100}, {70, 100}, {75, 100}
    };
    curve.valid = true;
    return curve;
}

ECScanner::ECScanner(std::shared_ptr<ECInterface> ec) : ec_(std::move(ec)) {}

void ECScanner::dump_full_ec(const std::string& output_file) {
    auto data = read_full_ec();
    std::ofstream out(output_file);
    out << "Address,Value,ASCII\n";
    for (size_t i = 0; i < data.size(); ++i) {
        char c = (data[i] >= 32 && data[i] <= 126) ? static_cast<char>(data[i]) : '.';
        out << "0x" << std::hex << std::setw(2) << std::setfill('0') << i
            << "," << std::dec << static_cast<int>(data[i]) << "," << c << "\n";
    }
}

std::vector<uint8_t> ECScanner::read_full_ec() {
    std::vector<uint8_t> data(256);
    ec_->read_block(0, data.data(), 256);
    return data;
}

std::vector<ECAddress> ECScanner::find_fan_curve_candidates() {
    auto data = read_full_ec();
    std::vector<ECAddress> candidates;

    for (size_t i = 0; i < data.size() - 1; ++i) {
        if (data[i] > 0 && data[i] <= 100 && data[i+1] > 0 && data[i+1] <= 100) {
            candidates.push_back({static_cast<uint16_t>(i), "0x" + std::to_string(i), "Possible curve point"});
        }
    }
    return candidates;
}

void ECScanner::diff_snapshots(const std::string& before_file, const std::string& after_file) {
    std::vector<uint8_t> before(256), after(256);
    // Implementation would read CSV files and compare
}

} // namespace msi_ec
