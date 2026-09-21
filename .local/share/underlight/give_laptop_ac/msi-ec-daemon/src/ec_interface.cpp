#include "ec_interface.h"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <unistd.h>
#include <fcntl.h>
#include <sys/io.h>
#include <linux/fs.h>
#include <cstring>

namespace msi_ec {

std::vector<ECAddress> ECInterface::scan_addresses(uint16_t start, uint16_t end) {
    std::vector<ECAddress> result;
    for (uint16_t addr = start; addr <= end; ++addr) {
        if (auto val = read_byte(addr)) {
            result.push_back({addr, "0x" + std::to_string(addr), "EC register"});
        }
    }
    return result;
}

std::vector<ECAddress> ECInterface::find_changed_addresses(const std::vector<uint8_t>& before,
                                                            const std::vector<uint8_t>& after) {
    std::vector<ECAddress> changed;
    size_t len = std::min(before.size(), after.size());
    for (size_t i = 0; i < len; ++i) {
        if (before[i] != after[i]) {
            changed.push_back({static_cast<uint16_t>(i), "0x" + std::to_string(i), "Changed"});
        }
    }
    return changed;
}

SysfsEC::SysfsEC(const std::filesystem::path& sysfs_path, const std::filesystem::path& ec_io)
    : sysfs_path_(sysfs_path), ec_io_(ec_io) {
    if (ec_io_.empty() && sysfs_path_ == "/sys/devices/platform/msi-ec")
        ec_io_ = "/sys/kernel/debug/ec/ec0/io";
}

SysfsEC::~SysfsEC() { shutdown(); }

bool SysfsEC::initialize() {
    if (!std::filesystem::exists(sysfs_path_)) {
        return false;
    }
    if (!std::filesystem::exists(sysfs_path_ / "fan_mode")) {
        return false;
    }
    initialized_ = true;
    has_debug_ = std::filesystem::exists(sysfs_path_ / "debug" / "ec_get");
    return true;
}

void SysfsEC::shutdown() { initialized_ = false; }

bool SysfsEC::is_available() const { return initialized_; }

bool SysfsEC::has_debug_interface() const { return has_debug_; }

bool SysfsEC::raw_firmware_matches() const {
    if (ec_io_.empty()) return false;
    std::ifstream firmware_file(sysfs_path_ / "fw_version");
    std::string firmware;
    std::getline(firmware_file, firmware);
    if (firmware.size() != 12) return false;
    const int fd = open(ec_io_.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    char raw[12];
    const auto count = pread(fd, raw, sizeof(raw), 0xa0);
    close(fd);
    return count == sizeof(raw) && std::string(raw, sizeof(raw)) == firmware;
}

bool SysfsEC::supports_raw_ec() const {
    return has_debug_ || raw_firmware_matches();
}

bool SysfsEC::raw_ec_writable() const {
    if (has_debug_) return access((sysfs_path_ / "debug/ec_set").c_str(), W_OK) == 0;
    if (!raw_firmware_matches() || access(ec_io_.c_str(), W_OK) != 0) return false;
    if (ec_io_ == "/sys/kernel/debug/ec/ec0/io") {
        std::ifstream parameter("/sys/module/ec_sys/parameters/write_support");
        std::string enabled;
        parameter >> enabled;
        return enabled == "Y" || enabled == "1";
    }
    return true; // Explicit alternate path is used by the isolated integration tests.
}

std::optional<std::string> SysfsEC::read_string_attr(const std::string& attr) {
    if (!initialized_) return std::nullopt;
    std::ifstream file(sysfs_path_ / attr);
    if (!file) return std::nullopt;
    std::string value;
    std::getline(file, value);
    return value;
}

bool SysfsEC::write_string_attr(const std::string& attr, const std::string& value) {
    if (!initialized_) return false;
    // Never create a missing attribute; check close and readback as well as write.
    const int fd = open((sysfs_path_ / attr).c_str(), O_WRONLY | O_TRUNC | O_CLOEXEC);
    if (fd < 0) return false;
    const bool written = ::write(fd, value.data(), value.size()) == static_cast<ssize_t>(value.size());
    const bool closed = close(fd) == 0;
    return written && closed && read_string_attr(attr) == value;
}

std::vector<std::string> SysfsEC::available_values(const std::string& attr) {
    std::ifstream file(sysfs_path_ / attr);
    std::vector<std::string> values;
    for (std::string value; file >> value;) values.push_back(value);
    return values;
}

bool SysfsEC::apply_controls(const std::map<std::string, std::string>& changes, std::string& error) {
    error.clear();
    std::map<std::string, std::string> before;
    for (const auto& [attr, value] : changes) {
        std::vector<std::string> allowed;
        if (attr == "fan_mode") allowed = available_values("available_fan_modes");
        else if (attr == "shift_mode") allowed = available_values("available_shift_modes");
        else if (attr == "cooler_boost" || attr == "super_battery" || attr == "webcam") allowed = {"on", "off"};
        else if (attr == "fn_key" || attr == "win_key") allowed = {"left", "right"};
        // An allowlist prevents D-Bus callers from accessing arbitrary paths/registers.
        if (std::find(allowed.begin(), allowed.end(), value) == allowed.end()) {
            error = "Unsupported control or value: " + attr;
            return false;
        }
        auto old = read_string_attr(attr);
        if (!old) { error = "Cannot read " + attr; return false; }
        before[attr] = *old;
    }
    std::vector<std::string> attempted;
    for (const auto& [attr, value] : changes) {
        if (before[attr] == value) continue;
        attempted.push_back(attr);
        if (!write_string_attr(attr, value)) { error = "Write or verification failed: " + attr; break; }
    }
    if (error.empty()) {
        for (const auto& [attr, value] : changes) {
            if (read_string_attr(attr) != value) { error = "Final verification failed: " + attr; break; }
        }
    }
    if (error.empty()) return true;
    for (auto it = attempted.rbegin(); it != attempted.rend(); ++it) write_string_attr(*it, before[*it]);
    bool restored = true;
    for (const auto& [attr, value] : before) restored &= read_string_attr(attr) == value;
    error += restored ? "; previous values restored" : "; rollback failed, check hardware state";
    return false;
}

std::vector<std::string> SysfsEC::list_attributes() {
    std::vector<std::string> attrs;
    if (!initialized_) return attrs;
    for (const auto& entry : std::filesystem::directory_iterator(sysfs_path_)) {
        if (entry.is_regular_file()) {
            attrs.push_back(entry.path().filename().string());
        }
    }
    return attrs;
}

std::optional<std::string> SysfsEC::read_firmware_version() {
    return read_string_attr("fw_version");
}

std::optional<std::string> SysfsEC::read_fan_mode_str() {
    return read_string_attr("fan_mode");
}

bool SysfsEC::write_fan_mode_str(const std::string& mode) {
    return write_string_attr("fan_mode", mode);
}

std::optional<std::string> SysfsEC::read_shift_mode_str() {
    return read_string_attr("shift_mode");
}

bool SysfsEC::write_shift_mode_str(const std::string& mode) {
    return write_string_attr("shift_mode", mode);
}

std::optional<uint8_t> SysfsEC::read_cpu_temp() {
    if (auto val = read_string_attr("cpu/realtime_temperature")) {
        try { return static_cast<uint8_t>(std::stoi(*val)); } catch (...) {}
    }
    return std::nullopt;
}

std::optional<uint8_t> SysfsEC::read_cpu_fan() {
    if (auto val = read_string_attr("cpu/realtime_fan_speed")) {
        try { return static_cast<uint8_t>(std::stoi(*val)); } catch (...) {}
    }
    return std::nullopt;
}

std::optional<uint8_t> SysfsEC::read_gpu_temp() {
    if (auto val = read_string_attr("gpu/realtime_temperature")) {
        try { return static_cast<uint8_t>(std::stoi(*val)); } catch (...) {}
    }
    return std::nullopt;
}

std::optional<uint8_t> SysfsEC::read_gpu_fan() {
    if (auto val = read_string_attr("gpu/realtime_fan_speed")) {
        try { return static_cast<uint8_t>(std::stoi(*val)); } catch (...) {}
    }
    return std::nullopt;
}

std::optional<uint8_t> SysfsEC::read_byte(uint16_t addr) {
    if (!initialized_) return std::nullopt;

    // Try known sysfs attributes first for common registers
    switch (addr) {
        case 0xa0: case 0xa1: case 0xa2: case 0xa3: case 0xa4: case 0xa5:
        case 0xa6: case 0xa7: case 0xa8: case 0xa9: case 0xaa: case 0xab: {
            if (auto fw = read_firmware_version()) {
                if (addr - 0xa0 < fw->size()) {
                    return static_cast<uint8_t>((*fw)[addr - 0xa0]);
                }
            }
            break;
        }
        case 0x68: return read_cpu_temp();
        case 0x71: return read_cpu_fan();
        case 0x80: return read_gpu_temp();
        case 0x89: return read_gpu_fan();
        case 0xf4: case 0xd4: {
            if (auto mode = read_fan_mode_str()) {
                if (*mode == "auto") return 0x0d;
                if (*mode == "silent") return 0x1d;
                if (*mode == "basic") return 0x4d;
                if (*mode == "advanced") return 0x8d;
            }
            break;
        }
        case 0xf2: case 0xd2: {
            if (auto mode = read_shift_mode_str()) {
                if (*mode == "turbo") return 0xc4;
                if (*mode == "eco") return 0xc2;
                if (*mode == "comfort") return 0xc1;
                if (*mode == "sport") return 0xc0;
            }
            break;
        }
    }

    if (!has_debug_ && !ec_io_.empty()) {
        const int fd = open(ec_io_.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd >= 0) {
            uint8_t value;
            const auto count = addr <= 0xff ? pread(fd, &value, 1, addr) : -1;
            close(fd);
            return count == 1 ? std::optional<uint8_t>(value) : std::nullopt;
        }
    }

    // Fall back to debug interface if available
    if (!has_debug_) return std::nullopt;

    auto debug_get = sysfs_path_ / "debug" / "ec_get";
    std::ofstream set_file(debug_get);
    if (!set_file) return std::nullopt;
    set_file << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(addr);
    set_file.flush();
    if (!set_file.good()) return std::nullopt;
    set_file.close();

    std::ifstream get_file(debug_get);
    if (!get_file) return std::nullopt;

    std::string line;
    if (!std::getline(get_file, line)) return std::nullopt;

    try {
        return static_cast<uint8_t>(std::stoul(line, nullptr, 16));
    } catch (...) {
        return std::nullopt;
    }
}

bool SysfsEC::write_byte(uint16_t addr, uint8_t value) {
    if (!initialized_) return false;

    // Handle known registers via sysfs
    switch (addr) {
        case 0xf4: case 0xd4: {
            switch (value) {
                case 0x0d: case 0x0c: return write_fan_mode_str("auto");
                case 0x1d: return write_fan_mode_str("silent");
                case 0x4d: case 0x4c: return write_fan_mode_str("basic");
                case 0x8d: case 0x8c: return write_fan_mode_str("advanced");
            }
            break;
        }
        case 0xf2: case 0xd2: {
            switch (value) {
                case 0xc4: return write_shift_mode_str("turbo");
                case 0xc2: return write_shift_mode_str("eco");
                case 0xc1: return write_shift_mode_str("comfort");
                case 0xc0: return write_shift_mode_str("sport");
            }
            break;
        }
    }

    if (!has_debug_ && !ec_io_.empty() && raw_ec_writable()) {
        const int fd = open(ec_io_.c_str(), O_WRONLY | O_CLOEXEC);
        if (fd < 0) return false;
        const auto count = addr <= 0xff ? pwrite(fd, &value, 1, addr) : -1;
        const bool closed = close(fd) == 0;
        return count == 1 && closed && read_byte(addr) == value;
    }

    // Fall back to debug interface
    if (!has_debug_) return false;

    auto debug_set = sysfs_path_ / "debug" / "ec_set";
    std::ofstream set_file(debug_set);
    if (!set_file) return false;

    set_file << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(addr)
             << "=" << std::setw(2) << std::setfill('0') << static_cast<int>(value);
    return set_file.good();
}

bool SysfsEC::read_block(uint16_t addr, uint8_t* buffer, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (auto val = read_byte(addr + i)) {
            buffer[i] = *val;
        } else {
            return false;
        }
    }
    return true;
}

bool SysfsEC::write_block(uint16_t addr, const uint8_t* buffer, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (!write_byte(addr + i, buffer[i])) {
            return false;
        }
    }
    return true;
}

PortIOEC::PortIOEC(uint16_t command_port, uint16_t data_port)
    : cmd_port_(command_port), data_port_(data_port) {}

PortIOEC::~PortIOEC() { shutdown(); }

bool PortIOEC::initialize() {
    if (ioperm(cmd_port_, 2, 1) != 0) return false;
    if (ioperm(data_port_, 1, 1) != 0) return false;

    mem_fd_ = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd_ < 0) return false;

    initialized_ = true;
    return true;
}

void PortIOEC::shutdown() {
    if (mem_fd_ >= 0) close(mem_fd_);
    mem_fd_ = -1;
    ioperm(cmd_port_, 2, 0);
    ioperm(data_port_, 1, 0);
    initialized_ = false;
}

bool PortIOEC::is_available() const { return initialized_; }

bool PortIOEC::wait_ec_ready() {
    for (int i = 0; i < 1000; ++i) {
        uint8_t status = inb(cmd_port_);
        if (!(status & 0x02)) return true;
        usleep(100);
    }
    return false;
}

void PortIOEC::ec_write_cmd(uint8_t cmd) {
    wait_ec_ready();
    outb(cmd, cmd_port_);
}

void PortIOEC::ec_write_data(uint8_t data) {
    wait_ec_ready();
    outb(data, data_port_);
}

uint8_t PortIOEC::ec_read_data() {
    wait_ec_ready();
    return inb(data_port_);
}

std::optional<uint8_t> PortIOEC::read_byte(uint16_t addr) {
    if (!initialized_) return std::nullopt;

    ec_write_cmd(0x80);
    ec_write_data(static_cast<uint8_t>(addr >> 8));
    ec_write_data(static_cast<uint8_t>(addr & 0xFF));
    ec_write_cmd(0x81);
    return ec_read_data();
}

bool PortIOEC::write_byte(uint16_t addr, uint8_t value) {
    if (!initialized_) return false;

    ec_write_cmd(0x80);
    ec_write_data(static_cast<uint8_t>(addr >> 8));
    ec_write_data(static_cast<uint8_t>(addr & 0xFF));
    ec_write_data(value);
    return true;
}

bool PortIOEC::read_block(uint16_t addr, uint8_t* buffer, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (auto val = read_byte(addr + i)) {
            buffer[i] = *val;
        } else {
            return false;
        }
    }
    return true;
}

bool PortIOEC::write_block(uint16_t addr, const uint8_t* buffer, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (!write_byte(addr + i, buffer[i])) {
            return false;
        }
    }
    return true;
}

std::unique_ptr<ECInterface> create_best_backend() {
    auto sysfs = std::make_unique<SysfsEC>();
    if (sysfs->initialize()) {
        return sysfs;
    }

    // No automatic raw port I/O fallback. Use the kernel's supported interface.
    return nullptr;
}

} // namespace msi_ec
