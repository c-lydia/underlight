from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch

import main
from config import Settings
from hardware import WriteResult, write_verified
from telemetry import TelemetrySnapshot
from fan_backend import BackendError, BackendStatus, FanBackend
from textual.widgets import Button, Collapsible, Footer, Sparkline, TabbedContent


class TUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory()))
        self.ec = self.root / "ec"
        self.battery = self.root / "power/BAT1"
        self.keyboard = self.root / "leds/msiacpi::kbd_backlight"
        for directory in (self.ec, self.battery, self.keyboard):
            directory.mkdir(parents=True)
        for name, value in {
            "shift_mode": "comfort", "fan_mode": "auto", "cooler_boost": "off",
            "super_battery": "off", "webcam": "on", "fn_key": "right", "win_key": "left",
            "available_shift_modes": "eco comfort turbo", "available_fan_modes": "auto silent advanced",
        }.items():
            (self.ec / name).write_text(value)
        (self.battery / "charge_control_start_threshold").write_text("70")
        (self.battery / "charge_control_end_threshold").write_text("80")
        (self.keyboard / "brightness").write_text("2")
        (self.keyboard / "max_brightness").write_text("3")
        self.stack.enter_context(patch.object(main, "MSI_EC", self.ec))
        self.stack.enter_context(patch.object(main, "POWER_SUPPLY", self.root / "power"))
        self.stack.enter_context(patch.object(main, "LEDS", self.root / "leds"))
        self.settings = Settings()
        self.stack.enter_context(patch.object(main, "load_config", return_value=self.settings))
        self.save = self.stack.enter_context(patch.object(main, "save_config", return_value=True))
        self.apply_config_impl = main.GiveLaptopAC._apply_config
        self.stack.enter_context(patch.object(main.GiveLaptopAC, "_apply_config"))
        self.stack.enter_context(patch.object(main.GiveLaptopAC, "_tick_procs"))
        self.backend = Mock(spec=FanBackend)
        self.backend.status = BackendStatus(reason="Service offline (test)")
        self.backend.probe = AsyncMock(side_effect=lambda: self.backend.status)
        self.stack.enter_context(patch.object(main, "FanBackend", return_value=self.backend))
        self.stack.enter_context(patch.object(main.psutil, "cpu_count", return_value=4))
        self.stack.enter_context(patch.object(main.pynvml, "nvmlInit", side_effect=main.pynvml.NVMLError_LibraryNotFound))
        values = dict.fromkeys([
            "cpu_temp", "gpu_temp", "cpu_power", "gpu_power", "cpu_fan", "gpu_fan",
            "ram", "vram", "battery", "cpu_load", "gpu_load", "cpu_frequency",
            "net_up", "net_down", "disk_read", "disk_write", "cpu_voltage", "gpu_voltage",
            "cpu_clock", "gpu_clock",
        ])
        values.update(cpu_temp=55, cpu_fan=35, ram=42, cpu_load=25, battery=80)
        self.sample = TelemetrySnapshot(values, per_core=[10, 20, 30, 40])
        sampler = self.stack.enter_context(patch.object(main, "TelemetrySampler"))
        sampler.return_value.sample.return_value = self.sample

    async def test_rejected_mode_does_not_change_highlight_or_saved_settings(self):
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            with patch.object(main, "ec_write", return_value=WriteResult(False, "driver rejected turbo")):
                app.query_one("#shift-turbo", Button).press()
                await pilot.pause()
            self.assertIn("driver rejected", app.query_one("#status").content)
            self.assertTrue(app.query_one("#shift-comfort").has_class("-on"))
            self.assertFalse(app.query_one("#shift-turbo").has_class("-on"))
            self.assertEqual(self.settings.performance_mode, "comfort")
            self.save.assert_not_called()
            app._tick()
            self.assertIn("driver rejected", app.query_one("#status").content)

    async def test_successful_controls_save_actual_state(self):
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            self.assertTrue(app.query_one("#bcs-70").has_class("-on"))
            for button in ("shift-eco", "kbd-1", "bcs-50", "bce-90"):
                app.query_one(f"#{button}", Button).press()
                await pilot.pause()
            self.assertEqual(self.settings.performance_mode, "eco")
            self.assertEqual(self.settings.last_preset, "")
            self.assertEqual(self.settings.kbd_brightness, 1)
            self.assertEqual(self.settings.battery_start_limit, 50)
            self.assertEqual(self.settings.battery_limit, 90)
            self.assertTrue(app.query_one("#bce-90").has_class("-on"))
            self.assertTrue(app.query_one("#bl-90").has_class("-on"))
            self.assertEqual((self.keyboard / "brightness").read_text(), "1")
            self.assertNotIn("shift", self.settings.__dict__)
            app.query_one("#p-gaming", Button).press()
            await pilot.pause()
            self.assertEqual((self.ec / "shift_mode").read_text(), "turbo")
            self.assertEqual((self.ec / "fan_mode").read_text(), "advanced")
            self.assertEqual((self.ec / "cooler_boost").read_text(), "on")
            self.assertEqual(self.settings.last_preset, "p-gaming")
            self.assertIs(self.settings.cooler_boost, True)

    async def test_failed_preset_rolls_back_without_saving(self):
        def driver(path, value):
            if path.name == "fan_mode" and value == "advanced":
                return WriteResult(False, "fan mode rejected")
            return write_verified(path, value)

        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            with patch("hardware.write_verified", side_effect=driver):
                app.query_one("#p-gaming", Button).press()
                await pilot.pause()
            self.assertEqual((self.ec / "shift_mode").read_text(), "comfort")
            self.assertEqual(self.settings.last_preset, "p-balanced")
            self.assertIn("Preset failed", app.query_one("#status").content)
            self.save.assert_not_called()

    async def test_unavailable_values_controls_colors_and_navigation(self):
        (self.ec / "super_battery").unlink()
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#supbat-btn").disabled)
            self.assertFalse(app.query_one("#supbat-btn").has_class("-on"))
            self.assertTrue(app.query_one("#curve-read").disabled)
            card = app._spark_cards["sc-gp"]
            card.update(25)
            card.update(None)
            self.assertEqual(card._value.content, "N/A")
            self.assertEqual(card.history, [])
            self.assertFalse(card.query_one(Sparkline).display)
            colors = {card.query_one(Sparkline).max_color for card in app._spark_cards.values()}
            self.assertEqual(len(colors), 20)
            self.sample.values["cpu_temp"] = 65
            self.sample.values["cpu_fan"] = None
            app._tick()
            self.assertNotIn("fan stalled", app.query_one("#status").content)
            for size in ((80, 24), (120, 40)):
                await pilot.resize_terminal(*size)
                app.query_one("#dash-details", Collapsible).collapsed = False
                await pilot.press("d", "j", "f")
                await pilot.pause()
                self.assertGreater(app.query_one("#dash-scroll").scroll_y, 0)
                await pilot.press("o")
                await pilot.pause()
                app.query_one("#p-gaming").focus()
                await pilot.pause()
                await pilot.press("p")
                await pilot.pause()
                self.assertEqual(app.query_one("#tabs", TabbedContent).active, "procs")
                self.assertLessEqual(app.query_one("#status").region.bottom, app.query_one(Footer).region.y)

    async def test_backend_controls_curves_and_auto_are_verified_before_saving(self):
        self.backend.status = BackendStatus(True, "test.123", True, True, "", ("auto", "silent", "advanced"))
        points = [[40, 20], [60, 50], [80, 100]]
        self.backend.read_curve = AsyncMock(return_value=points)

        async def controls(changes):
            for name, value in changes.items():
                (self.ec / name).write_text(value)

        async def preset(name):
            (self.ec / "fan_mode").write_text("advanced")
            return points

        self.backend.apply_controls = AsyncMock(side_effect=controls)
        self.backend.set_preset = AsyncMock(side_effect=preset)
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            await app.workers.wait_for_complete()
            self.assertIn("connected", str(app.query_one("#backend-status").content))
            self.assertFalse(app.query_one("#curve-read").disabled)
            for button in ("shift-eco", "p-gaming", "curve-read", "curve-perf", "curve-reset"):
                app.query_one(f"#{button}", Button).press()
                await pilot.pause()
                await app.workers.wait_for_complete()
            self.backend.apply_controls.assert_any_await({"shift_mode": "eco"})
            self.backend.apply_controls.assert_any_await({"shift_mode": "turbo", "fan_mode": "advanced", "cooler_boost": "on"})
            self.backend.set_preset.assert_awaited_once_with("performance")
            self.assertEqual(self.settings.fan_curves["system"].points, points)
            self.assertEqual(self.settings.fan_mode, "auto")
            self.assertIn("40°C", str(app.query_one("#curve-points").content))
            self.assertTrue(app.query_one("#fan-auto").has_class("-on"))

    async def test_backend_failure_does_not_save_or_retry_through_sysfs(self):
        self.backend.status = BackendStatus(True, "test", True, True, "", ("auto", "silent"))
        self.backend.apply_controls = AsyncMock(side_effect=BackendError("access denied"))
        self.backend.set_preset = AsyncMock(side_effect=BackendError("curve rollback failed"))
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            await app.workers.wait_for_complete()
            with patch.object(main, "ec_write") as direct_write:
                app.query_one("#shift-eco", Button).press()
                await pilot.pause()
                await app.workers.wait_for_complete()
                direct_write.assert_not_called()
            self.assertIn("access denied", app.query_one("#status").content)
            self.assertEqual(self.settings.performance_mode, "comfort")
            app.query_one("#curve-perf", Button).press()
            await pilot.pause()
            await app.workers.wait_for_complete()
            self.assertIn("rollback failed", app.query_one("#status").content)
            self.save.assert_not_called()

    async def test_backend_reconnect_reports_curve_limitation_but_allows_auto(self):
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("o")
            await app.workers.wait_for_complete()
            self.assertTrue(app.query_one("#curve-read").disabled)
            self.backend.status = BackendStatus(
                True, "15K1IMS1.113", False, False, "Driver has no raw fan-curve interface", ("auto", "silent"),
            )
            app.query_one("#backend-reconnect", Button).press()
            await pilot.pause()
            await app.workers.wait_for_complete()
            self.assertFalse(app.query_one("#curve-reset").disabled)
            self.assertTrue(app.query_one("#curve-perf").disabled)
            self.assertIn("no raw", str(app.query_one("#backend-status").content))

    async def test_startup_restores_saved_ec_settings_through_connected_backend(self):
        self.backend.status = BackendStatus(True, "test", False, False, "No curves", ("auto", "silent"))
        async def controls(changes):
            for name, value in changes.items():
                (self.ec / name).write_text(value)
        self.backend.apply_controls = AsyncMock(side_effect=controls)
        self.settings.performance_mode = "eco"
        self.settings.fan_mode = "silent"
        app = main.GiveLaptopAC()
        app._apply_config = lambda: self.apply_config_impl(app)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            self.backend.apply_controls.assert_awaited_once_with({
                "shift_mode": "eco", "fan_mode": "silent", "cooler_boost": "off",
            })
            self.assertEqual((self.ec / "fan_mode").read_text(), "silent")
            await pilot.press("r")
            await app.workers.wait_for_complete()
            self.backend.apply_controls.assert_awaited_once()

    async def test_overview_fits_and_details_remain_accessible(self):
        app = main.GiveLaptopAC()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#dash-details", Collapsible).collapsed)
            self.assertIn("25%", str(app.query_one("#overview-cpu .overview-value").content))
            self.assertIn("55°C", str(app.query_one("#overview-cpu .overview-detail").content))
            for size, columns in (((80, 24), 2), ((120, 40), 4), ((50, 24), 1)):
                await pilot.resize_terminal(*size)
                await pilot.pause()
                cards = list(app.query(main.OverviewCard))
                self.assertEqual(len({card.region.x for card in cards}), columns)
                viewport = app.query_one("#dash-scroll").region
                self.assertTrue(all(card.region.right <= viewport.right for card in cards))
                if columns > 1:
                    self.assertTrue(all(card.region.bottom <= viewport.bottom for card in cards))
            await pilot.press("v")
            await pilot.pause()
            self.assertFalse(app.query_one("#dash-details", Collapsible).collapsed)
            await pilot.press("v")
            self.assertTrue(app.query_one("#dash-details", Collapsible).collapsed)


if __name__ == "__main__":
    unittest.main()
