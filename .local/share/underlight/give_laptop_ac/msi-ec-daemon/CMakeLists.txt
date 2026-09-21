cmake_minimum_required(VERSION 3.16)
project(msi-ec-daemon VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(CMAKE_BUILD_TYPE STREQUAL "")
    set(CMAKE_BUILD_TYPE Release)
endif()

option(BUILD_SYSTEMD "Install systemd service" ON)
option(BUILD_DBUS "Enable DBus service (requires libsystemd)" ON)
option(BUILD_CLI "Build CLI tool" ON)

find_package(PkgConfig REQUIRED)

if(BUILD_DBUS)
    pkg_check_modules(SYSTEMD REQUIRED IMPORTED_TARGET libsystemd)
endif()

add_library(msi_ec_core
    src/ec_interface.cpp
    src/fan_curve_manager.cpp
)

target_include_directories(msi_ec_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

if(BUILD_CLI)
    add_executable(msi-ec-cli src/cli.cpp)
    target_link_libraries(msi-ec-cli msi_ec_core)
endif()

if(BUILD_DBUS)
    add_executable(msi-ec-daemon src/main.cpp src/dbus_service.cpp)
    target_link_libraries(msi-ec-daemon msi_ec_core PkgConfig::SYSTEMD)
endif()

install(TARGETS msi_ec_core
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    INCLUDES DESTINATION include
)

if(BUILD_CLI)
    install(TARGETS msi-ec-cli DESTINATION bin)
endif()

if(BUILD_DBUS)
    install(TARGETS msi-ec-daemon DESTINATION bin)
endif()

install(DIRECTORY include/ DESTINATION include/msi-ec
    FILES_MATCHING PATTERN "*.h"
)

if(BUILD_SYSTEMD AND BUILD_DBUS)
    configure_file(systemd/msi-ec-daemon.service.in msi-ec-daemon.service @ONLY)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/msi-ec-daemon.service DESTINATION lib/systemd/system)
    install(FILES systemd/com.msi_ec.FanControl.conf DESTINATION share/dbus-1/system.d)
endif()

install(FILES config/models.json DESTINATION share/msi-ec-daemon)
install(FILES config/presets.json DESTINATION share/msi-ec-daemon)

include(CTest)
if(BUILD_TESTING)
    add_executable(msi-ec-core-tests tests/core_test.cpp)
    target_link_libraries(msi-ec-core-tests msi_ec_core)
    add_test(NAME core COMMAND msi-ec-core-tests)
endif()
