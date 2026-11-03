"""Search installed Hyprland shortcuts and launch the selected action."""
import argparse
import os
from pathlib import Path
import re
import subprocess

from .common import choose

LABELS = {
    'killactive': 'Close active window', 'togglefloating': 'Toggle floating window',
    'fullscreen': 'Toggle fullscreen', 'movefocus': 'Move focus',
    'movewindow': 'Move window', 'resizeactive': 'Resize window',
    'workspace': 'Switch workspace', 'movetoworkspace': 'Move window to workspace',
    'layoutmsg': 'Change window layout', 'togglespecialworkspace': 'Show hidden shelf',
}
EXTRA = [
    ('Luma AI companion', ['underlight-luma', '--menu']),
    ('Android & Flutter', ['underlight-android', 'menu']),
    ('Snapshot preview', ['kitty', '--hold', '--title', 'Underlight snapshot', 'underlight-snapshot', 'create']),
    ('AI privacy controls', ['underlight-privacy', 'menu']),
    ('Project workspaces', ['underlight-project', 'menu']),
    ('Obsidian quick capture', ['underlight-capture', 'menu']),
    ('Audio mixer', ['underlight-control', 'audio']),
    ('Wi-Fi', ['underlight-network']),
    ('Desktop widgets', ['underlight-widgets-toggle']),
    ('Power profiles', ['underlight-profile', 'menu']),
    ('Network lab', ['kitty', '--title', 'Underlight network lab', 'underlight-tui']),
    ('System diagnostics', ['underlight-doctor', '--terminal']),
    ('Machine profiles', ['underlight-machine', 'menu']),
]


def bindings(path):
    variables, rows = {}, []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('$') and '=' in line:
            key, value = line.split('=', 1)
            variables[key.strip()] = value.strip()
            continue
        if not re.match(r'bind[elm]*\s*=', line):
            continue
        for key in sorted(variables, key=len, reverse=True):
            line = line.replace(key, variables[key])
        fields = [part.strip() for part in line.split('=', 1)[1].split(',', 3)]
        if len(fields) < 3:
            continue
        mods, key, dispatcher = fields[:3]
        argument = fields[3] if len(fields) == 4 else ''
        keys = '+'.join([*mods.title().split(), key.title()])
        if dispatcher == 'exec':
            label = argument.replace('~/.local/bin/', '').replace('underlight-', '').replace('-', ' ')
        else:
            label = LABELS.get(dispatcher, dispatcher) + (' · ' + argument if argument else '')
        rows.append((f'{keys} — {label}', ['hyprctl', 'dispatch', dispatcher, argument]))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='print without opening a menu')
    parser.add_argument('--search', default='', help='filter keys and action names')
    args = parser.parse_args(argv)
    path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'hypr/underlight/bindings.conf'
    if not path.is_file():
        path = Path(__file__).resolve().parents[4] / '.config/hypr/underlight/bindings.conf'
    rows = bindings(path)
    rows.extend((f'Menu — {label}', command) for label, command in EXTRA)
    rows = [(label, command) for label, command in rows if args.search.lower() in label.lower()]
    if args.list:
        print('\n'.join(label for label, _ in rows))
        return
    choices = dict(rows)
    selected = choose('Underlight shortcuts', list(choices))
    if selected:
        subprocess.run(choices[selected], check=True)
