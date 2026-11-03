"""Exercise launcher failures without starting graphical apps or changing profiles."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_terminal import load, ROOT

luma = load('luma', 'underlight-luma')


class LumaTests(unittest.TestCase):
    def test_panel_keeps_natural_height_and_scrolls_on_short_displays(self):
        self.assertEqual(luma.panel_size(1920, 1080, 640), (360, 640))
        self.assertEqual(luma.panel_size(1280, 720, 640), (360, 517))
        self.assertEqual(luma.panel_size(320, 480, 640), (284, 277))
        self.assertEqual(luma.panel_size(20, 100, 640), (1, 1))

    def test_missing_working_folder_is_reported_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(luma.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'Working folder does not exist'):
                    luma.LaunchJob(luma.AGENTS[0], {'vault': directory + '/missing'})
                spawn.assert_not_called()

    def test_failed_launcher_keeps_error_output(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            helper = home / '.local/bin/underlight-ai'
            helper.parent.mkdir(parents=True)
            helper.write_text('#!/bin/sh\nprintf "test client is not installed\\n" >&2\nexit 7\n')
            helper.chmod(0o755)
            with patch.object(luma.Path, 'home', return_value=home):
                job = luma.LaunchJob(luma.AGENTS[0], {})
            try:
                self.assertEqual(job.process.wait(timeout=3), 7)
                message = job.failure(7)
                self.assertIn('OpenCode could not open (exit 7)', message)
                self.assertIn('test client is not installed', message)
            finally:
                job.log.close()

    def test_failed_profile_does_not_block_client_and_argv_stays_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            local = home / '.local/bin'
            local.mkdir(parents=True)
            opencode = home / '.opencode/bin'
            opencode.mkdir(parents=True)
            for path, source in [
                (local / 'underlight-profile', '#!/bin/sh\nexit 23\n'),
                (local / 'kitty', '#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n'),
                (opencode / 'opencode', '#!/bin/sh\nprintf "client failed\\n" >&2\nexit 19\n'),
            ]:
                path.write_text(source)
                path.chmod(0o755)
            project = home / 'project with $(literal) spaces'
            project.mkdir()
            env = {**os.environ, 'HOME': str(home), 'PATH': '/usr/bin:/bin', 'UNDERLIGHT_PRIVACY': 'cloud-context'}
            result = subprocess.run([str(ROOT / '.local/bin/underlight-ai'), 'opencode', str(project)],
                                    env=env, capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('continuing with the current power profile', result.stderr)
            argv = json.loads(result.stdout)
            self.assertEqual(argv[5], str(project))
            self.assertEqual(argv[-2:], ['opencode', str(project)])
            # The terminal's child wrapper leaves a failed client readable.
            env['PATH'] = f'{opencode}:/usr/bin:/bin'
            child = subprocess.run(argv[6:], env=env, input='\n', capture_output=True, text=True, timeout=3)
            self.assertEqual(child.returncode, 19)
            self.assertIn('Press Enter to close', child.stdout)
            self.assertIn('client failed', child.stderr)


if __name__ == '__main__':
    unittest.main()
