"""Behavior and safety checks for Underlight's portable workflows."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/share/underlight'))
from workflows import capture, common, machine, privacy, project, shortcuts, snapshot


class Workflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir()
        env = patch.dict(os.environ, {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / '.config'),
                                      'XDG_STATE_HOME': str(self.home / '.local/state'), 'WAYLAND_DISPLAY': ''})
        env.start()
        self.addCleanup(env.stop)
        self.privacy_override = os.environ.pop('UNDERLIGHT_PRIVACY', None)
        if self.privacy_override is not None:
            self.addCleanup(os.environ.__setitem__, 'UNDERLIGHT_PRIVACY', self.privacy_override)
        self.vault = self.home / 'Notes with spaces'
        (self.vault / '.obsidian').mkdir(parents=True)

    def write(self, name, data='original'):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path

    def test_snapshot_excludes_credentials_notes_and_runtime_data(self):
        self.write('.config/kitty/kitty.conf', 'font_size 12')
        self.write('.config/underlight/luma.json', '{"api_key":"secret-value"}')
        self.write('.ssh/id_ed25519', 'private key')
        self.write('.ssh/config.d/secret.conf', '-----BEGIN OPENSSH PRIVATE KEY-----')
        self.write('.config/opencode/auth.json', 'credentials')
        self.write('.local/share/underlight/rag-store/private', 'note chunks')
        self.write('Documents/note.md', 'notes')
        value, skipped = snapshot.collect(self.home)
        self.assertEqual(set(value['files']), {'.config/kitty/kitty.conf'})
        self.assertEqual(len(skipped), 2)
        self.assertNotIn('secret-value', str(value))

    def test_snapshot_preview_restore_and_backup_of_file_symlink(self):
        path = self.write('.config/kitty/kitty.conf', 'old')
        source = self.write('checkout/kitty.conf', 'repository stays unchanged')
        path.unlink()
        path.symlink_to(source)
        data = {'.config/kitty/kitty.conf': b'new settings'}
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot.restore(self.home, data)
            self.assertTrue(path.is_symlink())
            snapshot.restore(self.home, data, apply=True)
        self.assertEqual(path.read_text(), 'new settings')
        self.assertEqual(source.read_text(), 'repository stays unchanged')
        backups = list(common.state_root().glob('snapshot-rollbacks/*/files/.config/kitty/kitty.conf'))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_restore_rejects_parent_symlink_before_any_writes(self):
        outside = self.home / 'checkout'
        outside.mkdir()
        folder = self.home / '.config/hypr'
        folder.mkdir(parents=True)
        (folder / 'underlight').symlink_to(outside)
        files = {'.config/kitty/kitty.conf': b'new', '.config/hypr/underlight/colors.conf': b'new'}
        with self.assertRaisesRegex(ValueError, 'parent path'):
            snapshot.restore(self.home, files, apply=True)
        self.assertFalse((self.home / '.config/kitty/kitty.conf').exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_unchanged_linked_config_directory_needs_no_restore(self):
        outside = self.home / 'checkout'
        outside.mkdir()
        (outside / 'colors.conf').write_text('same')
        folder = self.home / '.config/hypr'
        folder.mkdir(parents=True)
        (folder / 'underlight').symlink_to(outside)
        self.assertEqual(snapshot.plan_restore(self.home, {'.config/hypr/underlight/colors.conf': b'same'}), [])

    def test_restore_rolls_back_on_write_failure(self):
        first = self.write('.config/kitty/kitty.conf', 'first')
        second = self.write('.config/wofi/config', 'second')
        real = snapshot.atomic_write
        def write(path, data):
            if path == second:
                raise OSError('disk full')
            return real(path, data)
        with patch.object(snapshot, 'atomic_write', side_effect=write), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(OSError, 'disk full'):
                snapshot.restore(self.home, {'.config/kitty/kitty.conf': b'new', '.config/wofi/config': b'new'}, True)
        self.assertEqual(first.read_text(), 'first')
        self.assertEqual(second.read_text(), 'second')

    def test_snapshot_import_rejects_traversal_unknown_paths_and_corruption(self):
        data = b'hello'
        entry = {'data': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}
        path = self.home / 'snapshot.json'
        for name in ('../escape', '/tmp/escape', '.ssh/id_rsa', '.config/hypr/underlight/../../escape'):
            common.write_json(path, {'version': 1, 'files': {name: entry}})
            with self.assertRaises(ValueError):
                snapshot.load_snapshot(path)
        common.write_json(path, {'version': 1, 'files': {'.ssh/config': {**entry, 'sha256': 'bad'}}})
        with self.assertRaisesRegex(ValueError, 'checksum'):
            snapshot.load_snapshot(path)

    def test_snapshot_roundtrip(self):
        self.write('.config/kitty/kitty.conf', 'font_size 13')
        value, _ = snapshot.collect(self.home)
        path = self.home / 'snapshot.json'
        common.write_json(path, value)
        self.assertEqual(snapshot.load_snapshot(path), {'.config/kitty/kitty.conf': b'font_size 13'})

    def test_capture_keeps_existing_notes_and_unique_names(self):
        existing = self.vault / 'existing.md'
        existing.write_text('keep me')
        first = capture.save_capture(self.vault, 'thought')
        second = capture.save_capture(self.vault, 'another thought')
        self.assertNotEqual(first, second)
        self.assertIn('thought', first.read_text())
        self.assertEqual(existing.read_text(), 'keep me')

    def test_capture_stores_image_and_usable_markdown_link(self):
        png = b'\x89PNG\r\n\x1a\nimage'
        note = capture.save_capture(self.vault, '', image=png)
        self.assertIn('../90%20Attachments/Captures/', note.read_text())
        self.assertEqual(next((self.vault / '90 Attachments/Captures').iterdir()).read_bytes(), png)

    def test_capture_rejects_symlink_escape_and_invalid_png(self):
        outside = self.home / 'outside'
        outside.mkdir()
        (self.vault / '00 Inbox').symlink_to(outside)
        with self.assertRaises(ValueError):
            capture.save_capture(self.vault, 'private note')
        (self.vault / '00 Inbox').unlink()
        with self.assertRaisesRegex(ValueError, 'PNG'):
            capture.save_capture(self.vault, '', image=b'not a png')
        self.assertEqual(list(self.vault.rglob('*.md')), [])

    def test_capture_cancellation_does_not_create_files(self):
        with patch.object(capture.subprocess, 'run', return_value=Mock(returncode=1, stdout='')):
            capture.main(['--vault', str(self.vault), 'screenshot'])
        self.assertEqual(list(self.vault.iterdir()), [self.vault / '.obsidian'])

    def test_capture_setup_and_link_validation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            capture.main(['setup', str(self.vault)])
            capture.main(['link', 'https://example.org/page'])
        self.assertEqual(common.vault_path(), self.vault)
        with self.assertRaisesRegex(ValueError, 'complete http'):
            capture.main(['link', 'javascript:alert(1)'])

    def test_privacy_defaults_to_local_and_persisted_modes_control_exports(self):
        self.assertEqual(privacy.mode(), 'local')
        with self.assertRaises(ValueError):
            privacy.check_client('hermes')
        privacy.check_client('qwen')
        for selected, raw_allowed, answer_allowed in [('local', False, False), ('local-answer', False, True), ('cloud-context', True, True)]:
            common.write_json(common.config_root() / 'privacy.json', {'mode': selected})
            for raw, allowed in ((True, raw_allowed), (False, answer_allowed)):
                if allowed:
                    self.assertEqual(privacy.check_export(raw), selected)
                else:
                    with self.assertRaises(ValueError):
                        privacy.check_export(raw)

    def test_session_privacy_override_and_invalid_mode_fail_closed(self):
        common.write_json(common.config_root() / 'privacy.json', {'mode': 'cloud-context'})
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'local'}):
            with self.assertRaises(ValueError):
                privacy.check_export(True)
        with patch.dict(os.environ, {'UNDERLIGHT_PRIVACY': 'typo'}):
            with self.assertRaises(ValueError):
                privacy.check_client('hermes')

    def test_local_inference_rejects_remote_endpoints_and_cloud_models(self):
        for endpoint in ('http://localhost:11434', 'http://127.0.0.1:11434', 'http://[::1]:11434'):
            privacy.check_ollama(endpoint, 'qwen3:4b')
        for endpoint in ('https://example.org', 'http://localhost.evil', 'http://localhost@evil', 'file:///tmp/model'):
            with self.assertRaises(ValueError):
                privacy.check_ollama(endpoint, 'qwen3:4b')
        with self.assertRaises(ValueError):
            privacy.check_ollama('http://localhost:11434', 'model:cloud')

    def test_machine_preview_apply_and_no_automatic_host_commands(self):
        with contextlib.redirect_stdout(io.StringIO()):
            machine.main(['create', 'laptop', '--kind', 'laptop', '--gpu', 'integrated',
                          '--monitor', 'eDP-1,preferred,auto,1', '--vault', str(self.vault)])
            machine.activate('laptop', preview=True)
            self.assertFalse((common.config_root() / 'host.conf').exists())
            machine.activate('laptop')
        self.assertEqual(common.machine()['name'], 'laptop')
        with patch.object(machine.subprocess, 'run') as run:
            machine.restore_monitors()
            self.assertEqual(run.call_args.args[0], ['hyprctl', 'keyword', 'monitor', 'eDP-1,preferred,auto,1'])
        self.assertEqual((common.config_root() / 'gpu-policy').read_text(), 'integrated\n')
        self.assertEqual(common.vault_path(), self.vault)

    def test_missing_machine_profile_never_contacts_compositor(self):
        with patch.object(machine.subprocess, 'run') as run:
            machine.restore_monitors()
            run.assert_not_called()

    def test_machine_rejects_config_injection(self):
        for monitor in ('eDP-1,preferred\nexec = touch /tmp/no', 'eDP-1,$(command)', 'eDP-1,foo # comment'):
            with self.assertRaises(ValueError):
                machine.render({'kind': 'laptop', 'distro': 'ubuntu', 'gpu': 'auto', 'monitors': [monitor]})
        with self.assertRaises(ValueError):
            machine.profile_path('../escape')

    def test_project_register_preview_and_literal_ros_setup_path(self):
        directory = self.home / 'project $(literal)'
        directory.mkdir()
        setup = self.write("ros setup '$(literal).bash", 'export ROS_DISTRO=test')
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(['add', 'robot', str(directory), '--ros-setup', str(setup), '--vault', str(self.vault), '--note', 'Robot.md'])
        value = project.load_project('robot')
        name, commands = project.plan('robot', value)
        self.assertTrue(name.startswith('ul-robot-'))
        self.assertEqual(commands[0][-2], str(directory))
        import shlex
        shell = shlex.split(commands[1][-1])[-1]
        self.assertIn(shlex.quote(str(setup)), shell)
        with patch.object(project.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            project.open_project('robot', preview=True)
            run.assert_not_called()

    def test_project_reuses_sessions_and_rolls_back_failed_creation(self):
        with contextlib.redirect_stdout(io.StringIO()):
            project.main(['add', 'test', str(self.home)])
        with patch.object(project.shutil, 'which', return_value='/bin/true'), \
                patch.object(project.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            project.open_project('test', detached=True)
            self.assertEqual(run.call_count, 1)
        calls = []
        def fail_window(command, **kwargs):
            calls.append(command)
            if command[1] == 'has-session':
                return Mock(returncode=1)
            if command[1] == 'new-window':
                raise subprocess.CalledProcessError(1, command)
            return Mock(returncode=0)
        with patch.object(project.shutil, 'which', return_value='/bin/true'), \
                patch.object(project.subprocess, 'run', side_effect=fail_window):
            with self.assertRaises(subprocess.CalledProcessError):
                project.open_project('test', detached=True)
        self.assertEqual(calls[-1][1], 'kill-session')

    def test_shortcuts_match_configuration_and_expand_variables(self):
        rows = shortcuts.bindings(ROOT / '.config/hypr/underlight/bindings.conf')
        self.assertGreater(len(rows), 70)
        command = next(command for label, command in rows if label == 'Super+Return — kitty')
        self.assertEqual(command, ['hyprctl', 'dispatch', 'exec', 'kitty'])
        self.assertTrue(any('Super+Alt+N' in label and 'capture' in label for label, _ in rows))
        self.assertFalse(any('$mainMod' in label for label, _ in rows))

    def test_all_commands_have_help_without_creating_state(self):
        for name in ('snapshot', 'shortcuts', 'project', 'privacy', 'capture', 'machine'):
            result = subprocess.run([str(ROOT / '.local/bin' / ('underlight-' + name)), '--help'],
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage:', result.stdout)
        self.assertFalse((self.home / '.config').exists())


if __name__ == '__main__':
    unittest.main()
