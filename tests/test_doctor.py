"""Exercise diagnostic failures without accessing the host desktop or services."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / '.local/bin/underlight-doctor'


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.home = self.root / 'home'
        self.config = self.root / 'custom config'
        self.data = self.root / 'data'
        self.log = self.root / 'calls'
        self.env = {
            'HOME': str(self.home), 'PATH': str(self.bin),
            'XDG_CONFIG_HOME': str(self.config), 'XDG_DATA_HOME': str(self.data),
            'HYPRLAND_INSTANCE_SIGNATURE': 'test-session',
            'UNDERLIGHT_DOCTOR_TIMEOUT': '0.1', 'DOCTOR_TEST_LOG': str(self.log),
        }
        for command in ('bash', 'timeout', 'awk', 'cat'):
            (self.bin / command).symlink_to(shutil.which(command))
        for command in ('Hyprland', 'hyprctl', 'waybar', 'kitty', 'wofi',
                        'hyprpaper', 'hypridle', 'powerprofilesctl', 'nvcc',
                        'ollama', 'opencode', 'hermes', 'underlight-android',
                        'adb', 'flutter', 'emulator', 'sdkmanager', 'nvim',
                        'screen', 'ssh', 'jq', 'find'):
            self.stub(command)
        self.stub('nvidia-smi', 'echo "NVIDIA test, 123, 8192 MiB"')
        self.stub('switcherooctl', 'echo NVIDIA')
        self.stub('systemctl', 'echo active')
        for path in ('hypr/hyprland.conf', 'kitty/kitty.conf', 'waybar/config.jsonc',
                     'systemd/user/underlight-wallpaper.service'):
            self.write(self.config / path)
        for path in ('.ssh/config', '.ssh/config.d/underlight.conf'):
            self.write(self.home / path)

    def write(self, path, content='test\n'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def stub(self, name, body='exit 0'):
        path = self.bin / name
        path.write_text('#!/bin/sh\nprintf "%s\\n" "${0##*/} $*" >> "$DOCTOR_TEST_LOG"\n' + body + '\n')
        path.chmod(0o755)

    def run_doctor(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, text=True,
                              capture_output=True, timeout=8)

    def test_help_and_invalid_arguments_do_not_run_checks_or_source_config(self):
        self.write(self.config / 'underlight/android.sh', 'echo sourced >> "$DOCTOR_TEST_LOG"\n')
        result = self.run_doctor('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Usage:', result.stdout)
        for args in (('--unknown',), ('--help', 'extra')):
            self.assertEqual(self.run_doctor(*args).returncode, 2)
        self.assertFalse(self.log.exists())

    def test_invalid_timeout_is_rejected(self):
        for value in ('0', '0.0', '-1', 'forever', '1s'):
            self.env['UNDERLIGHT_DOCTOR_TIMEOUT'] = value
            self.assertEqual(self.run_doctor().returncode, 2, value)
        self.assertFalse(self.log.exists())

    def test_missing_timeout_explains_dependency_without_running_probes(self):
        (self.bin / 'timeout').unlink()
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn('install coreutils', result.stderr)
        self.assertFalse(self.log.exists())

    def test_missing_json_validator_is_not_reported_as_invalid_config(self):
        (self.bin / 'jq').unlink()
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0)
        self.assertIn('JSON validation unavailable; install jq', result.stdout)

    def test_healthy_checks_respect_xdg_paths_and_only_query_services(self):
        self.write(self.data / 'underlight/give_laptop_ac/main.py')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('bundled copy present', result.stdout)
        calls = self.log.read_text().splitlines()
        self.assertIn(f'Hyprland --verify-config --config {self.config}/hypr/hyprland.conf', calls)
        self.assertEqual([line for line in calls if line.startswith('systemctl ')], [
            'systemctl --user show underlight-wallpaper.service --property=ActiveState --value'])
        self.assertFalse(any(line.startswith('ssh ') for line in calls))

    def test_broken_configuration_link_is_a_failure_with_repair_guidance(self):
        path = self.config / 'kitty/kitty.conf'
        path.unlink()
        path.symlink_to(self.root / 'missing-checkout')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn('broken link:', result.stdout)
        self.assertIn('rerun ./install.sh', result.stdout)

    def test_missing_hyprland_is_a_warning_not_a_parse_failure(self):
        (self.bin / 'Hyprland').unlink()
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('verification unavailable', result.stdout)
        self.assertNotIn('verification failed', result.stdout)

    def test_invalid_hyprland_config_is_a_failure(self):
        self.stub('Hyprland', 'exit 1')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn('verification failed; run:', result.stdout)

    def test_live_config_errors_and_failed_wallpaper_are_failures(self):
        self.stub('hyprctl', 'echo "Config error: unknown option"')
        self.stub('systemctl', 'echo failed')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn('compositor reports errors', result.stdout)
        self.assertIn('journalctl --user -u underlight-wallpaper.service -b', result.stdout)
        self.assertIn('2 failure(s)', result.stdout)

    def test_unavailable_session_bus_is_a_warning(self):
        self.stub('systemctl', 'exit 1')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0)
        self.assertIn('user service manager unavailable', result.stdout)

    def test_outside_hyprland_skips_live_probes(self):
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0)
        self.assertIn('not in a Hyprland session', result.stdout)
        calls = self.log.read_text().splitlines()
        self.assertFalse(any(line.startswith(('hyprctl ', 'systemctl ')) for line in calls))

    def test_stalled_probes_time_out_and_report_still_finishes(self):
        for command in ('Hyprland', 'hyprctl', 'systemctl', 'nvidia-smi', 'switcherooctl', 'ollama'):
            self.stub(command, 'exec /bin/sleep 10')
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('timed out after 0.1s'), 6)
        self.assertIn('Summary:', result.stdout)


if __name__ == '__main__':
    unittest.main()
