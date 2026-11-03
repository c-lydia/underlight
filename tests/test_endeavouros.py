"""Exercise the Arch bootstrap with fake package/services and real staged links."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'install-endeavouros.sh'
WORKFLOWS = ('snapshot', 'shortcuts', 'project', 'privacy', 'capture', 'machine')


class EndeavourOSInstall(unittest.TestCase):
    def test_package_preview_covers_workflow_dependencies_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(INSTALLER), '--print-packages'],
                                    env={**os.environ, 'HOME': directory},
                                    capture_output=True, text=True, check=True)
            packages = result.stdout.splitlines()
            required = {'python', 'tmux', 'neovim', 'kitty', 'wofi', 'grim', 'slurp',
                        'wl-clipboard', 'xdg-utils', 'coreutils', 'libnotify',
                        'python-gobject', 'python-cairo', 'gtk-layer-shell', 'python-yaml'}
            self.assertTrue(required <= set(packages), required - set(packages))
            self.assertEqual(len(packages), len(set(packages)))
            self.assertNotIn('ollama', packages)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_rag_package_preview_implies_ai(self):
        result = subprocess.run([str(INSTALLER), '--with-rag', '--print-packages'],
                                capture_output=True, text=True, check=True)
        self.assertTrue({'ollama', 'opencode'} <= set(result.stdout.splitlines()))

    @unittest.skipIf(os.geteuid() == 0, 'bootstrap deliberately refuses root; staged integration needs a normal user')
    def test_staged_default_and_rag_installs_preserve_settings_and_repeat_safely(self):
        for flags in ([], ['--with-rag']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                home, binaries, log = base / 'home', base / 'bin', base / 'calls.jsonl'
                binaries.mkdir()
                checkout = home / '.local/share/underlight/neovim_config'
                (checkout / '.git').mkdir(parents=True)
                (checkout / 'init.lua').write_text('-- existing workbench\n')
                config = home / '.config/underlight'
                config.mkdir(parents=True)
                privacy = config / 'privacy.json'
                privacy.write_text('{"mode":"local-answer"}\n')
                machine = config / 'machine.json'
                machine.write_text('{"name":"existing-laptop"}\n')
                mock = binaries / 'mock-command'
                mock.write_text(f'#!{sys.executable}\n' + '''import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['INSTALL_TEST_LOG'], 'a') as stream:
    stream.write(json.dumps([name, *args]) + '\\n')
if name == 'sudo':
    assert args[0] in ('pacman', 'systemctl'), args
elif name in ('python', 'python3'):
    if args[:2] == ['-m', 'venv']:
        target = pathlib.Path(args[2]) / 'bin'
        target.mkdir(parents=True, exist_ok=True)
        link = target / 'python'
        if not link.exists(): link.symlink_to(os.environ['INSTALL_TEST_MOCK'])
    elif args[:2] == ['-m', 'pip']:
        pass
    else:
        os.execv(sys.executable, [sys.executable, *args])
elif name == 'git':
    raise SystemExit('Unexpected network operation: ' + repr(args))
''')
                mock.chmod(0o755)
                for name in ('sudo', 'pacman', 'git', 'python', 'python3', 'nvim', 'screen'):
                    (binaries / name).symlink_to(mock)
                # Only the test shell substitutes distribution identification.
                # The real installer retains its /etc/os-release guard.
                env_file = base / 'bash-env'
                env_file.write_text('''source() {
  if [[ $1 == /etc/os-release ]]; then
    ID=endeavouros; ID_LIKE=arch; PRETTY_NAME=EndeavourOS
  else
    builtin source "$@"
  fi
}
''')
                env = {**os.environ, 'HOME': str(home), 'PATH': f'{binaries}:/usr/bin:/bin',
                       'XDG_CONFIG_HOME': str(home / '.config'), 'XDG_DATA_HOME': str(home / '.local/share'),
                       'XDG_STATE_HOME': str(home / '.local/state'), 'BASH_ENV': str(env_file),
                       'INSTALL_TEST_LOG': str(log), 'INSTALL_TEST_MOCK': str(mock),
                       'UNDERLIGHT_PROFILE': 'minimal', 'UNDERLIGHT_SKIP_NEOVIM': '0',
                       'UNDERLIGHT_WITH_RAG': '0', 'UNDERLIGHT_NEOVIM_SOURCE': str(checkout)}
                for _ in range(2):
                    result = subprocess.run([str(INSTALLER), *flags], env=env,
                                            text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for name in WORKFLOWS:
                        self.assertEqual((home / '.local/bin' / ('underlight-' + name)).resolve(),
                                         ROOT / '.local/bin' / ('underlight-' + name))
                    self.assertEqual(privacy.read_text(), '{"mode":"local-answer"}\n')
                    self.assertEqual(machine.read_text(), '{"name":"existing-laptop"}\n')
                self.assertTrue((home / '.local/share/underlight/workflows').is_symlink())
                bindings = (home / '.config/hypr/underlight/bindings.conf').read_text()
                for name in ('shortcuts', 'project', 'capture'):
                    self.assertIn('~/.local/bin/underlight-' + name, bindings)
                self.assertNotIn('host.conf', (home / '.config/hypr/hyprland.conf').read_text())
                self.assertTrue((home / '.local/share/underlight/obsidian/luma-plugin/main.js').is_file())
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                installed = next(call for call in calls if call[:2] == ['sudo', 'pacman'])
                self.assertIn('xdg-utils', installed)
                self.assertIn('tmux', installed)
                self.assertEqual('ollama' in installed, bool(flags))
                self.assertEqual((config / 'rag.yaml').is_file(), bool(flags))
                self.assertEqual(['sudo', 'systemctl', 'enable', '--now', 'ollama.service'] in calls, bool(flags))


if __name__ == '__main__':
    unittest.main()
