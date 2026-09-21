# Cyborg 15: firmware 15K1IMS1.113

The backend uses six CPU fan-speed slots at `0x72` through `0x77` and reads
their temperature steps from `0x6a` through `0x6f`. It preserves all temperature
bytes, the following bytes at `0x78` and above, and the GPU table. A second GPU
fan curve is not inferred from the presence of GPU temperature readings.

Evidence for this layout:

- [Cyborg reverse-engineering notes](https://gist.github.com/heinthanth/7f4d527b54a845facf0c31862cee896d)
  identify six speed settings starting at `0x72` on the 15K1 family.
- [Published dumps of exact firmware 15K1IMS1.113](https://github.com/wygodad/ghostdeck/issues/19)
  show temperatures `[51, 58, 65, 73, 78, 83]` and speeds
  `[20, 40, 55, 70, 90, 100]` in those ranges.
- [MControlCenter's register definitions](https://github.com/dmitry-s93/MControlCenter/blob/main/src/operate.cpp)
  independently identify the CPU temperature and speed table start addresses.
  Its generic seven-speed layout is not applied to this six-slot Cyborg layout.

These sources establish a firmware-specific mapping, not a universal MSI map.
The old generic paired entries at `0x50` remain disabled.

## Connection and checks

Normal modes continue through `msi-ec` sysfs. Curve access uses the kernel's
`ec_sys` file at `/sys/kernel/debug/ec/ec0/io` (or the documented `msi-ec` debug
interface when present). The raw EC firmware string must exactly match sysfs
before this backend enables curve access.

The driver and service must both have write access. The service reads and
validates the current curve before changing anything. Temperatures must remain
fixed, speeds must increase or stay level, and the hottest step must be 100%.
Named presets are sampled at the device's existing temperature steps. Every
write is read back; activation failure attempts to restore both curve and mode.

The checked-in tests use simulated memory to check register boundaries,
read-only access, firmware mismatches, rejected changes, and rollback. They do
not establish physical cooling performance; no preset is applied to live
hardware as part of those tests.

## Enable

From the project directory, after building:

```bash
sudo bash msi-ec-daemon/install.sh --enable-curves --start
```

This explicit option loads `ec_sys` with write support, configures it for future
boots, installs the updated service, and restarts it. It accepts only the exact
firmware above. It enables access; it does not apply a curve. Use **Reconnect**
and **Read Curve** in the TUI before selecting a preset.
