"""Ensure the optional native plugin is never loaded without its guards."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / '.local/bin/underlight-glass'
COMMIT = 'dd220efe7b1e292415bd0ea7161f63df9c95bfd3'


class GlassGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        self.log = self.root / 'calls'
        for name, source in {
            'uname': '#!/bin/sh\necho x86_64\n',
            'hyprctl': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$GLASS_TEST_LOG"\n'
                       'if [ "$1" = version ]; then echo "$GLASS_TEST_VERSION"; fi\n',
        }.items():
            path = bin_dir / name
            path.write_text(source)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}',
                        XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_STATE_HOME=str(self.root / 'state'),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        GLASS_TEST_LOG=str(self.log), GLASS_TEST_VERSION=COMMIT)

    def run_helper(self, mode):
        return subprocess.run([str(SCRIPT), mode], env=self.env,
                              text=True, capture_output=True)

    def test_disabled_restore_never_contacts_compositor(self):
        self.assertEqual(self.run_helper('restore').returncode, 0)
        self.assertFalse(self.log.exists())

    def test_mismatched_version_never_loads_plugin(self):
        self.env['GLASS_TEST_VERSION'] = 'different-hyprland-commit'
        self.assertNotEqual(self.run_helper('enable').returncode, 0)
        self.assertEqual(self.log.read_text().splitlines(), ['version'])

    def test_unverified_binary_never_loads_or_enables(self):
        binary = self.root / 'data/underlight/plugins/hyprglass-0.2.1/hyprglass.so'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'not the approved release')
        self.assertNotEqual(self.run_helper('enable').returncode, 0)
        self.assertEqual(self.log.read_text().splitlines(), ['version'])
        self.assertFalse((self.root / 'state/underlight-glass/enabled').exists())


if __name__ == '__main__':
    unittest.main()
