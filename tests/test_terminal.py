import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / '.local/bin' / file))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


lab = load('lab', 'underlight-tui')
admin = load('admin', 'underlight-net-admin')


class TerminalTests(unittest.TestCase):
    def test_phone_and_desktop_layouts(self):
        self.assertFalse(lab.layout(24, 40))
        self.assertFalse(lab.layout(10, 120))
        self.assertTrue(lab.layout(30, 120))

    def test_untrusted_terminal_output(self):
        self.assertEqual(lab.clean('\x1b[31mred\x00\x07\n'), 'red\n')

    def test_host_and_port_validation(self):
        for target in ('-oProxyCommand=bad', 'name\noption', '', 'two names'):
            with self.assertRaises(ValueError):
                lab.host(target)
        for number in ('0', '65536', '-1', 'bad'):
            with self.assertRaises(ValueError):
                lab.port(number)
        self.assertEqual(lab.host('user@192.168.1.2'), 'user@192.168.1.2')

    @patch.object(lab.shutil, 'which', return_value=None)
    def test_missing_utilities_do_not_crash_overview(self, _):
        output = lab.status()
        self.assertIn('ip is not installed', output)
        self.assertIn('ss is not installed', output)

    @patch.object(lab.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ip', 3))
    @patch.object(lab.shutil, 'which', return_value='/bin/ip')
    def test_bounded_diagnostics(self, *_):
        self.assertIn('timed out', lab.run(['ip', 'route'], 3))

    def test_nat_scopes_rules_to_interfaces_and_subnet(self):
        commands = admin.plan('eth0', 'wlan0', '192.168.50.0/24')
        self.assertEqual(len(commands), 7)
        self.assertFalse(any('-F' in action for pair in commands for action in pair))
        self.assertIn('192.168.50.0/24', commands[2][0])
        self.assertIn('RELATED,ESTABLISHED', commands[4][0])
        for args in [('eth0', 'eth0', '192.168.0.0/24'), ('eth0', 'wlan0', '0.0.0.0/0'),
                     ('eth0', 'wlan0', '192.168.0.1/24'), ('bad interface', 'wlan0', '192.168.0.0/24')]:
            with self.assertRaises(ValueError):
                admin.plan(*args)

    def test_nat_rolls_back_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            forwarding = state / 'ip_forward'
            forwarding.write_text('1\n')
            real_path = Path

            def paths(value):
                if value == '/proc/sys/net/ipv4/ip_forward':
                    return forwarding
                if value == '/sys/class/net':
                    return state
                return real_path(value)

            (state / 'eth0').mkdir()
            (state / 'wlan0').mkdir()
            commands = []

            def iptables(args):
                commands.append(args)
                if 'MASQUERADE' in args:
                    raise subprocess.CalledProcessError(1, args)

            with patch.object(admin, 'STATE', state), patch.object(admin, 'Path', side_effect=paths), \
                 patch.object(admin, 'iptables', side_effect=iptables), \
                 patch.object(admin.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaises(subprocess.CalledProcessError):
                    admin.start('eth0', 'wlan0', '192.168.50.0/24')
            self.assertEqual(commands[-2:], [['-X', admin.FWD], ['-t', 'nat', '-X', admin.NAT]])
            self.assertFalse((state / 'nat.json').exists())

    def test_stop_only_removes_recorded_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            import json
            inverses = [undo for _, undo in admin.plan('eth0', 'wlan0', '192.168.50.0/24')]
            (state / 'nat.json').write_text(json.dumps({'undo': inverses}))
            with patch.object(admin, 'STATE', state), patch.object(admin, 'iptables') as command:
                admin.stop()
            self.assertEqual([call.args[0] for call in command.call_args_list], list(reversed(inverses)))
            self.assertFalse((state / 'nat.json').exists())

    def test_fake_root_cannot_change_firewall(self):
        with patch.object(admin.os, 'geteuid', return_value=0), patch.object(admin, 'capable', return_value=False), \
             patch.object(admin.sys, 'argv', ['underlight-net-admin', 'nat-start', 'eth0', 'wlan0', '192.168.50.0/24']), \
             patch.object(admin, 'iptables') as command:
            self.assertEqual(admin.main(), 1)
            command.assert_not_called()

    def test_tui_in_real_terminals_and_resize(self):
        import fcntl
        import pty
        import select
        import signal
        import struct
        import termios
        import time
        for height, width in ((24, 40), (30, 120), (6, 20)):
            master, slave = pty.openpty()
            process = None
            try:
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
                process = subprocess.Popen([str(ROOT / '.local/bin/underlight-tui')], stdin=slave, stdout=slave,
                                           stderr=slave, env={**os.environ, 'TERM': 'xterm-256color'})
                output = b''
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        output += os.read(master, 65536)
                        if b'NETWORK LAB' in output or b'Resize to' in output:
                            break
                self.assertTrue(b'NETWORK LAB' in output or b'Resize to' in output, output)
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
                process.send_signal(signal.SIGWINCH)
                os.write(master, b'jq')
                self.assertEqual(process.wait(timeout=3), 0, output)
            finally:
                if process and process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)
                os.close(slave)


if __name__ == '__main__':
    unittest.main()
