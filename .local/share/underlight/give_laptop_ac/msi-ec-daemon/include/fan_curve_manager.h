#pragma once

#include "ec_interface.h"
#include <string>
#include <unordered_map>
#include <vector>
#include <optional>
#include <memory>

namespace msi_ec {

struct ModelFanCurveConfig {
    std::string model_id;
    std::string firmware_pattern;
    uint16_t curve_base_addr = 0;
    uint8_t num_points = 10;
    uint16_t fan_mode_addr = 0;
    uint8_t fan_mode_advanced_val = 0;
    uint16_t cpu_temp_addr = 0;
    uint16_t gpu_temp_addr = 0;
    uint16_t cpu_fan_addr = 0;
    uint16_t gpu_fan_addr = 0;
    bool dual_fan = true;
    // Only enable after the layout has been validated for this exact firmware.
    bool curve_layout_verified = false;
    uint16_t temperature_base_addr = 0;
    uint16_t speed_base_addr = 0;
    bool fixed_temperatures = false;
};

class ModelDatabase {
public:
    static ModelDatabase& instance();

    bool load_from_json(const std::string& path);
    bool load_builtin();

    std::optional<ModelFanCurveConfig> find_by_firmware(const std::string& fw_version) const;
    std::optional<ModelFanCurveConfig> find_by_model_id(const std::string& model_id) const;
    const std::vector<ModelFanCurveConfig>& all_configs() const { return configs_; }

private:
    ModelDatabase() = default;
    std::vector<ModelFanCurveConfig> configs_;

    void add_builtin_configs();
};

class FanCurveManager {
public:
    explicit FanCurveManager(std::shared_ptr<ECInterface> ec);
    ~FanCurveManager();

    bool detect_model(const std::string& fw_version);
    bool set_model_config(const ModelFanCurveConfig& config);

    std::optional<FanCurve> read_curve();
    bool write_curve(const FanCurve& curve);
    bool reset_to_default();
    bool apply_curve(const FanCurve& curve);
    std::optional<FanCurve> preset_for_hardware(const std::string& preset);
    std::string curve_unavailable_reason() const;
    const std::string& last_error() const { return last_error_; }

    std::optional<FanMode> read_fan_mode();
    bool write_fan_mode(FanMode mode);
    bool set_advanced_mode();

    ThermalData read_thermal_data();

    const ModelFanCurveConfig* current_config() const { return current_config_.has_value() ? &*current_config_ : nullptr; }
    std::string current_model_id() const { return current_config_ ? current_config_->model_id : "unknown"; }
    std::shared_ptr<ECInterface> get_ec_interface() const { return ec_; }

    static FanCurve create_default_curve();
    static FanCurve create_performance_curve();
    static FanCurve create_silent_curve();
    static FanCurve create_balanced_curve();
    static FanCurve create_max_cooling_curve();

    bool validate_curve(const FanCurve& curve) const;
    FanCurve interpolate_curve(const FanCurve& curve) const;

private:
    std::shared_ptr<ECInterface> ec_;
    std::optional<ModelFanCurveConfig> current_config_;
    FanCurve cached_curve_;
    bool cache_valid_ = false;
    std::string last_error_;

    uint16_t curve_point_addr(size_t index) const;
    bool read_curve_point(size_t index, FanCurvePoint& point);
    bool write_curve_point(size_t index, const FanCurvePoint& point);
};

class ECScanner {
public:
    explicit ECScanner(std::shared_ptr<ECInterface> ec);

    void dump_full_ec(const std::string& output_file);
    std::vector<uint8_t> read_full_ec();
    std::vector<ECAddress> find_fan_curve_candidates();
    void diff_snapshots(const std::string& before_file, const std::string& after_file);

private:
    std::shared_ptr<ECInterface> ec_;
};

} // namespace msi_ec
