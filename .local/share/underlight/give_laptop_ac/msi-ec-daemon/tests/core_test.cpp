#include "fan_curve_manager.h"
#include <array>
#include <iostream>
#include <stdexcept>
#include <unistd.h>
#include <fstream>

using namespace msi_ec;
void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }

class FakeEC : public ECInterface {
public:
    std::array<uint8_t, 256> bytes{};
    int fail_addr = -1;
    bool persistent_failure = false;
    int writes = 0;
    bool initialize() override { return true; }
    void shutdown() override {}
    bool is_available() const override { return true; }
    bool supports_raw_ec() const override { return true; }
    std::string get_backend_name() const override { return "test"; }
    std::optional<uint8_t> read_byte(uint16_t a) override { return bytes.at(a); }
    bool write_byte(uint16_t a, uint8_t v) override {
        ++writes;
        if (a == fail_addr) {
            if (!persistent_failure) fail_addr = -1;
            bytes.at(a) = 255; // partial write plus failed verification
            return false;
        }
        bytes.at(a) = v;
        return true;
    }
    bool read_block(uint16_t, uint8_t*, size_t) override { return false; }
    bool write_block(uint16_t, const uint8_t*, size_t) override { return false; }
};

int main() {
    try {
        auto ec = std::make_shared<FakeEC>();
        FanCurveManager manager(ec);
        manager.detect_model("1541EMS1.113");
        require(!manager.read_curve(), "unverified model must not expose a curve");
        require(!manager.write_curve(FanCurveManager::create_performance_curve()), "unverified model must reject writes");
        require(ec->writes == 0, "unverified config wrote EC");
        require(!ModelDatabase::instance().find_by_firmware(""), "empty firmware matched");
        require(!ModelDatabase::instance().find_by_firmware("15K1"), "partial firmware matched");

        ModelFanCurveConfig cfg{"test", "test", 0x50, 10, 0xd4, 0x8d, 0x68, 0x80, 0x71, 0x89, true, true};
        manager.set_model_config(cfg);
        auto initial = FanCurveManager::create_default_curve();
        for (size_t i = 0; i < initial.points.size(); ++i) {
            ec->bytes[0x50 + i*2] = initial.points[i].temp_c;
            ec->bytes[0x51 + i*2] = initial.points[i].fan_pct;
        }
        ec->bytes[0xd4] = 0x0d;
        const auto original = ec->bytes;
        auto bad = initial;
        bad.points[0].fan_pct = 200;
        require(!manager.write_curve(bad), "first point not validated");
        require(ec->writes == 0, "invalid curve wrote EC");
        ec->fail_addr = 0x55;
        require(!manager.apply_curve(FanCurveManager::create_performance_curve()), "partial write accepted");
        require(ec->bytes == original, "partial curve not restored");
        ec->fail_addr = 0xd4;
        require(!manager.apply_curve(FanCurveManager::create_performance_curve()), "mode failure accepted");
        require(ec->bytes == original, "curve or mode not restored");
        require(manager.apply_curve(FanCurveManager::create_performance_curve()), "valid curve rejected");
        require(manager.read_fan_mode() == FanMode::ADVANCED, "advanced mode not set");
        require(manager.reset_to_default(), "auto reset failed");
        require(manager.read_fan_mode() == FanMode::AUTO, "reset did not return to auto");
        ec->fail_addr = 0x55;
        ec->persistent_failure = true;
        require(!manager.apply_curve(initial), "permanent failure accepted");
        require(manager.last_error().find("rollback failed") != std::string::npos, "rollback failure hidden");

        auto cyborg = std::make_shared<FakeEC>();
        FanCurveManager cyborg_manager(cyborg);
        cyborg_manager.detect_model("15K1IMS1.113");
        const std::array<uint8_t, 6> temperatures{51,58,65,73,78,83};
        const std::array<uint8_t, 6> speeds{20,40,55,70,90,100};
        for (size_t i = 0; i < 6; ++i) {
            cyborg->bytes[0x6a+i] = temperatures[i];
            cyborg->bytes[0x72+i] = speeds[i];
        }
        cyborg->bytes[0xd4] = 0x0d;
        cyborg->bytes[0x78] = 78;
        auto baseline = cyborg->bytes;
        auto cyborg_curve = cyborg_manager.read_curve();
        require(cyborg_curve && cyborg_curve->points.size() == 6, "separate curve tables not read");
        auto performance = cyborg_manager.preset_for_hardware("performance");
        require(performance.has_value(), "hardware preset missing");
        require(cyborg_manager.apply_curve(*performance), "Cyborg preset failed");
        for (size_t addr = 0; addr < 256; ++addr) {
            if ((addr >= 0x72 && addr <= 0x77) || addr == 0xd4) continue;
            require(cyborg->bytes[addr] == baseline[addr], "write escaped the fan-speed registers");
        }
        require(cyborg->bytes[0x77] == 100, "hottest speed was lowered");
        auto altered = *performance;
        altered.points[0].temp_c = 50;
        auto writes = cyborg->writes;
        require(!cyborg_manager.apply_curve(altered), "temperature change accepted");
        require(cyborg->writes == writes, "temperature change wrote hardware");
        baseline = cyborg->bytes;
        cyborg->fail_addr = 0x74;
        auto silent = cyborg_manager.preset_for_hardware("silent");
        require(!cyborg_manager.apply_curve(*silent), "failed speed write accepted");
        require(cyborg->bytes == baseline, "Cyborg speeds not restored");

        char pattern[] = "/tmp/msi-ec-core-XXXXXX";
        const auto root = std::filesystem::path(mkdtemp(pattern));
        struct Cleanup { std::filesystem::path root; ~Cleanup() { std::filesystem::remove_all(root); } } cleanup{root};
        auto file = [&](const std::string& name, const std::string& value) { std::ofstream(root / name) << value; };
        file("fan_mode", "auto");
        file("shift_mode", "comfort");
        file("available_fan_modes", "auto\nsilent\nadvanced\n");
        file("available_shift_modes", "eco\ncomfort\nturbo\n");
        SysfsEC sysfs(root);
        require(sysfs.initialize(), "fake sysfs init failed");
        std::string error;
        require(sysfs.apply_controls({{"fan_mode","silent"}, {"shift_mode","eco"}}, error), "sysfs transaction failed");
        require(sysfs.read_string_attr("fan_mode") == "silent", "readback incorrect");
        require(!sysfs.apply_controls({{"../outside", "on"}}, error), "path traversal accepted");
        require(!sysfs.write_string_attr("missing", "on"), "missing attribute created");
        require(!std::filesystem::exists(root / "missing"), "created missing file");
        std::cout << "Core checks passed: validation, firmware matching, readback, rollback and sysfs controls\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
