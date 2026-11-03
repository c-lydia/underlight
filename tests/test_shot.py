"""Exercise screenshot ordering and failures without accessing the desktop."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(os.environ.get('UNDERLIGHT_SHOT_TEST_SCRIPT',
              Path(__file__).resolve().parents[1] / '.local/bin/underlight-shot'))


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls'
        # An isolated PATH prevents tests from invoking real desktop tools.
        for name in ('bash', 'mkdir', 'mktemp', 'rm', 'cat'):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = dict(os.environ, HOME=str(self.root), PATH=str(self.bin),
                        SHOT_LOG=str(self.log), XDG_PICTURES_DIR=str(self.root / 'pictures'))
        self.stub('date', "printf 'Screenshot_2026-11-03_12-00-00\\n'")
        self.stub('slurp', "printf '10,20 300x200\\n'")
        self.stub('sleep', ':')
        self.stub('grim', 'printf image > "${@: -1}"')
        self.stub('wl-copy', 'cat > "$HOME/clipboard"')
        self.stub('notify-send', ':')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$SHOT_LOG"\n' + body + '\n')
        path.chmod(0o755)

    def run_shot(self, *args):
        return subprocess.run(['/bin/bash', str(SCRIPT), *args], env=self.env,
                              text=True, capture_output=True, timeout=5)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def images(self):
        return list(self.root.glob('**/*.png'))

    def test_area_waits_after_selection_before_capture_and_copies(self):
        result = self.run_shot('area')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        select = next(i for i, x in enumerate(calls) if x.startswith('slurp '))
        wait = calls.index('sleep 0.2')
        capture = next(i for i, x in enumerate(calls) if x.startswith('grim -g 10,20 300x200 '))
        self.assertLess(select, wait)
        self.assertLess(wait, capture)
        self.assertEqual((self.root / 'clipboard').read_text(), 'image')
        self.assertEqual(len(self.images()), 1)

    def test_screen_does_not_select_or_wait(self):
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertFalse(any(x.startswith(('slurp ', 'sleep ')) for x in self.calls()))

    def test_failed_capture_has_no_success_notification_or_clipboard(self):
        self.stub('grim', 'printf partial > "${@: -1}"; exit 1')
        self.assertNotEqual(self.run_shot('area').returncode, 0)
        self.assertEqual(self.images(), [])
        self.assertFalse(any(x.startswith(('wl-copy ', 'notify-send Screenshot saved')) for x in self.calls()))

    def test_empty_capture_is_failure(self):
        self.stub('grim', ':')
        self.assertNotEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(self.images(), [])

    def test_cancel_is_quiet_and_never_captures(self):
        self.stub('slurp', 'exit 1')
        self.assertEqual(self.run_shot('area').returncode, 0)
        self.assertEqual(self.calls(), ['slurp '])
        self.assertEqual(self.images(), [])

    def test_empty_selection_never_captures(self):
        self.stub('slurp', ':')
        self.assertEqual(self.run_shot('area').returncode, 0)
        self.assertEqual(self.calls(), ['slurp '])

    def test_missing_selector_does_not_capture_whole_screen(self):
        (self.bin / 'slurp').unlink()
        self.assertNotEqual(self.run_shot('area').returncode, 0)
        self.assertFalse(any(x.startswith('grim ') for x in self.calls()))

    def test_clipboard_failure_keeps_file_and_reports_partial_success(self):
        self.stub('wl-copy', 'exit 1')
        result = self.run_shot('screen')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.images()), 1)
        self.assertIn('clipboard copy failed', result.stderr)
        self.assertTrue(any('Screenshot saved; clipboard failed' in x for x in self.calls()))

    def test_missing_optional_tools_does_not_fail_capture(self):
        (self.bin / 'wl-copy').unlink()
        (self.bin / 'notify-send').unlink()
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(len(self.images()), 1)

    def test_notification_failure_does_not_fail_capture(self):
        self.stub('notify-send', 'exit 1')
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(len(self.images()), 1)

    def test_rapid_captures_have_distinct_names(self):
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(len(self.images()), 2)

    def test_invalid_mode_does_not_capture(self):
        self.assertEqual(self.run_shot('typo').returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_help_does_not_capture(self):
        self.assertEqual(self.run_shot('--help').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_xdg_pictures_directory_with_spaces(self):
        self.env.pop('XDG_PICTURES_DIR')
        self.stub('xdg-user-dir', 'printf "%s\\n" "$HOME/My Pictures"')
        self.assertEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(self.images()[0].parent, self.root / 'My Pictures/Screenshots')

    def test_unwritable_destination_stops_before_capture(self):
        dest = self.root / 'pictures'
        dest.write_text('not a directory')
        self.assertNotEqual(self.run_shot('screen').returncode, 0)
        self.assertFalse(any(x.startswith('grim ') for x in self.calls()))

    def test_fallback_backend_preserves_requested_mode(self):
        (self.bin / 'grim').unlink()
        self.stub('gnome-screenshot', 'printf image > "${@: -1}"')
        self.assertEqual(self.run_shot('area').returncode, 0)
        self.assertTrue(any(x.startswith('gnome-screenshot -a -f ') for x in self.calls()))

    def test_no_backend_reports_failure(self):
        (self.bin / 'grim').unlink()
        self.assertNotEqual(self.run_shot('screen').returncode, 0)
        self.assertEqual(self.images(), [])


if __name__ == '__main__':
    unittest.main()
