import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

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
    def test_tui_filter_run_history_help_and_cancel_without_network(self):
        class Screen:
            def __init__(self):
                self.rows, self.frames = {}, []
                self.keys = iter([ord('/'), 10, 9, 10, ord('['), ord('?'), ord('?'),
                                  27, ord('/'), 10, ord('q')])
                self.input = iter([*'overview', '\n', '\x15', *'dns', '\n', '\x1b'])

            def getmaxyx(self): return (24, 80)
            def erase(self): self.rows = {}
            def addstr(self, y, x, text, attr): self.rows[y, x] = text
            def refresh(self): self.frames.append('\n'.join(self.rows.values()))
            def getch(self): return next(self.keys)
            def get_wch(self): return next(self.input)
            def move(self, *args): pass
            def clrtoeol(self): pass
            def timeout(self, value): pass
            def keypad(self, value): pass

        class Executor:
            def __init__(self, **kwargs): pass
            def submit(self, operation, *args):
                future = lab.concurrent.futures.Future()
                future.set_result(operation(*args))
                return future
            def shutdown(self, **kwargs): pass

        screen = Screen()
        with patch.object(lab.curses, 'curs_set'), patch.object(lab.curses, 'noecho'), \
             patch.object(lab.curses, 'has_colors', return_value=False), \
             patch.object(lab.concurrent.futures, 'ThreadPoolExecutor', Executor), \
             patch.object(lab, 'status', side_effect=['FIRST SNAPSHOT', 'SECOND SNAPSHOT']) as overview, \
             patch.object(lab, 'dns') as lookup:
            lab.tui(screen)
        self.assertEqual(overview.call_count, 2)
        lookup.assert_not_called()
        self.assertTrue(any('KEYBOARD GUIDE' in frame for frame in screen.frames))
        self.assertTrue(any('FIRST SNAPSHOT' in frame and '1/2' in frame for frame in screen.frames))
        self.assertIn('Cancelled. Nothing was run.', screen.frames[-1])

    def test_editable_prompt_validates_and_escape_cancels(self):
        screen = Mock()
        screen.getmaxyx.return_value = (24, 28)
        with patch.object(lab.curses, 'noecho'), patch.object(lab.curses, 'curs_set'):
            screen.get_wch.side_effect = ['\x1b']
            self.assertIsNone(lab.prompt(screen, 'Port', '55555', lab.port))
            screen.get_wch.side_effect = ['\x15', '0', '\n', '\x15', '4', '4', '3', '\n']
            self.assertEqual(lab.prompt(screen, 'Port', '55555', lab.port), '443')
            rendered = ' '.join(str(call) for call in screen.addstr.call_args_list)
            self.assertIn('Port must be between', rendered)
            screen.get_wch.side_effect = [lab.curses.KEY_END, lab.curses.KEY_BACKSPACE, 'x', '\n']
            self.assertEqual(lab.prompt(screen, 'Host', 'long-' * 20 + 'a'), 'long-' * 20 + 'x')

    def test_filter_history_and_terminal_cell_wrapping(self):
        tools = [('Inspect', 'Network overview', 'addresses'), ('Diagnose', 'DNS lookup', 'resolver')]
        self.assertEqual(lab.tool_rows(tools, 'RESOLVER'), [(None, 'DIAGNOSE'), (1, 'DNS lookup')])
        self.assertEqual(lab.tool_rows(tools, 'no-match'), [])
        history = lab.History()
        history.add('Old', 'old result')
        running = history.add('DNS', 'pending', 'Running')
        history.move(-1)
        running.update(text='resolved', state='Finished')
        self.assertEqual(history.current['text'], 'old result')
        history.move(1)
        self.assertEqual(history.current['text'], 'resolved')
        for index in range(25):
            history.add(str(index), 'output')
        self.assertEqual(len(history.entries), 20)
        self.assertEqual(history.current['title'], '24')
        self.assertEqual(lab.fit('界a界', 3), '界a')
        self.assertEqual(lab.wrapped('界a界\n  indented', 3), ['界a', '界', '  i', 'nde', 'nte', 'd'])

    @patch.object(lab, 'run', return_value='connection result')
    def test_tcp_bounds_dns_and_connection_together(self, command):
        self.assertEqual(lab.tcp('example.test', '443'), 'connection result')
        self.assertEqual(command.call_args.args[1], 6)
        self.assertEqual(command.call_args.args[0][-2:], ['example.test', '443'])

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
        for height, width in ((24, 40), (30, 120), (8, 28), (6, 20)):
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
                        if b'Network lab' in output or b'Resize to' in output:
                            break
                self.assertTrue(b'Network lab' in output or b'Resize to' in output, output)
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
