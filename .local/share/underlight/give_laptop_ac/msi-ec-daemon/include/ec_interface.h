#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <optional>
#include <filesystem>
#include <memory>
#include <map>

namespace msi_ec {

struct ECAddress {
    uint16_t addr;
    std::string name;
    std::string description;
};

struct FanCurvePoint {
    uint8_t temp_c;      // Temperature in Celsius
    uint8_t fan_pct;     // Fan speed percentage (0-100)
};

struct FanCurve {
    static constexpr size_t MAX_POINTS = 12;
    std::vector<FanCurvePoint> points;
    bool valid = false;
};

enum class FanMode {
    AUTO = 0,
    SILENT = 1,
    BASIC = 2,
    ADVANCED = 3,
    UNKNOWN = 255
};

enum class ShiftMode {
    ECO = 0,
    COMFORT = 1,
    SPORT = 2,
    TURBO = 3,
    UNKNOWN = 255
};

struct ThermalData {
    uint8_t cpu_temp = 0;
    uint8_t gpu_temp = 0;
    uint8_t cpu_fan_pct = 0;
    uint8_t gpu_fan_pct = 0;
};

class ECInterface {
public:
    virtual ~ECInterface() = default;

    virtual bool initialize() = 0;
    virtual void shutdown() = 0;
    virtual bool is_available() const = 0;
    virtual std::string get_backend_name() const = 0;

    virtual std::optional<uint8_t> read_byte(uint16_t addr) = 0;
    virtual bool write_byte(uint16_t addr, uint8_t value) = 0;
    virtual bool read_block(uint16_t addr, uint8_t* buffer, size_t len) = 0;
    virtual bool write_block(uint16_t addr, const uint8_t* buffer, size_t len) = 0;
    virtual bool supports_raw_ec() const { return false; }
    virtual bool raw_ec_writable() const { return supports_raw_ec(); }

    std::vector<ECAddress> scan_addresses(uint16_t start = 0x00, uint16_t end = 0xFF);
    std::vector<ECAddress> find_changed_addresses(const std::vector<uint8_t>& before,
                                                   const std::vector<uint8_t>& after);
};

class SysfsEC : public ECInterface {
public:
    explicit SysfsEC(const std::filesystem::path& sysfs_path = "/sys/devices/platform/msi-ec",
                     const std::filesystem::path& ec_io = {});
    ~SysfsEC() override;

    bool initialize() override;
    void shutdown() override;
    bool is_available() const override;
    std::string get_backend_name() const override { return "sysfs"; }

    std::optional<uint8_t> read_byte(uint16_t addr) override;
    bool write_byte(uint16_t addr, uint8_t value) override;
    bool read_block(uint16_t addr, uint8_t* buffer, size_t len) override;
    bool write_block(uint16_t addr, const uint8_t* buffer, size_t len) override;

    std::optional<std::string> read_string_attr(const std::string& attr);
    bool write_string_attr(const std::string& attr, const std::string& value);
    std::vector<std::string> list_attributes();
    bool has_debug_interface() const;
    bool supports_raw_ec() const override;
    bool raw_ec_writable() const override;
    std::optional<std::string> read_firmware_version();
    std::optional<std::string> read_fan_mode_str();
    bool write_fan_mode_str(const std::string& mode);
    std::optional<std::string> read_shift_mode_str();
    bool write_shift_mode_str(const std::string& mode);
    std::optional<uint8_t> read_cpu_temp();
    std::optional<uint8_t> read_cpu_fan();
    std::optional<uint8_t> read_gpu_temp();
    std::optional<uint8_t> read_gpu_fan();
    std::vector<std::string> available_values(const std::string& attr);
    bool apply_controls(const std::map<std::string, std::string>& changes, std::string& error);

private:
    std::filesystem::path sysfs_path_;
    std::filesystem::path ec_io_;
    bool raw_firmware_matches() const;
    bool initialized_ = false;
    bool has_debug_ = false;
};

class PortIOEC : public ECInterface {
public:
    explicit PortIOEC(uint16_t command_port = 0x66, uint16_t data_port = 0x62);
    ~PortIOEC() override;

    bool initialize() override;
    void shutdown() override;
    bool is_available() const override;
    std::string get_backend_name() const override { return "portio"; }

    std::optional<uint8_t> read_byte(uint16_t addr) override;
    bool write_byte(uint16_t addr, uint8_t value) override;
    bool read_block(uint16_t addr, uint8_t* buffer, size_t len) override;
    bool write_block(uint16_t addr, const uint8_t* buffer, size_t len) override;

private:
    uint16_t cmd_port_;
    uint16_t data_port_;
    int mem_fd_ = -1;
    bool initialized_ = false;

    bool wait_ec_ready();
    void ec_write_cmd(uint8_t cmd);
    void ec_write_data(uint8_t data);
    uint8_t ec_read_data();
};

std::unique_ptr<ECInterface> create_best_backend();

} // namespace msi_ec
