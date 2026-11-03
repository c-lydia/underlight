"""Named projects with persistent editor, terminal and optional ROS sessions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from urllib.parse import urlencode

from .common import choose, config_root, contained, machine, read_json, valid_name, vault_path, write_json


def project_path(name):
    return config_root() / 'projects' / (valid_name(name) + '.json')


def load_project(name):
    path = project_path(name)
    if not path.is_file():
        raise ValueError(f'Unknown project: {name}; use underlight-project add')
    value = read_json(path)
    directory = Path(value['directory']).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f'Project directory is missing: {directory}')
    value['directory'] = str(directory)
    if value.get('ros_setup') and not Path(value['ros_setup']).is_file():
        raise ValueError(f'ROS setup file is missing: {value["ros_setup"]}')
    if value.get('vault'):
        vault = vault_path(value['vault'])
        if value.get('note'):
            contained(vault, value['note'])
    return value


def session_name(name, directory):
    return 'ul-' + valid_name(name) + '-' + hashlib.sha256(directory.encode()).hexdigest()[:8]


def plan(name, value):
    session = session_name(name, value['directory'])
    setup = value.get('ros_setup')
    shell = 'exec bash -i'
    if setup:
        shell = f'source {shlex.quote(setup)} || exit; exec bash -i'
    editor = ['bash', '-lc', f'source {shlex.quote(setup)} && exec {shlex.quote(value["editor"])}'] if setup else [value['editor']]
    windows = [('editor', editor), ('shell', ['bash', '-lc', shell]), ('logs', ['bash', '-lc', shell])]
    commands = []
    for index, (title, argv) in enumerate(windows):
        action = ['new-session', '-d', '-s', session] if index == 0 else ['new-window', '-t', '=' + session]
        commands.append(['tmux', *action, '-n', title, '-c', value['directory'], shlex.join(argv)])
    return session, commands


def open_project(name, detached=False, preview=False):
    value = load_project(name)
    session, commands = plan(name, value)
    if preview:
        print(json.dumps({'session': session, 'commands': commands, 'vault': value.get('vault'), 'note': value.get('note')}, indent=2))
        return
    for binary in ('tmux', value['editor'], 'bash'):
        if not shutil.which(binary):
            raise ValueError(f'{binary} is not installed')
    existing = subprocess.run(['tmux', 'has-session', '-t', '=' + session], capture_output=True)
    if existing.returncode:
        # Serialize creation so two launcher clicks cannot create duplicate windows.
        import fcntl
        from .common import state_root
        lock = state_root() / 'projects.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            if subprocess.run(['tmux', 'has-session', '-t', '=' + session], capture_output=True).returncode:
                created = False
                try:
                    for command in commands:
                        subprocess.run(command, check=True)
                        created = True
                except Exception:
                    if created:
                        subprocess.run(['tmux', 'kill-session', '-t', '=' + session], capture_output=True)
                    raise
    if detached:
        print(f'Workspace ready: tmux attach-session -t {session}')
        return
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('kitty'):
        subprocess.run(['kitty', '--detach', '--title', f'Project · {name}',
                        '--directory', value['directory'], 'tmux', 'attach-session', '-t', '=' + session], check=True)
        if value.get('vault') and shutil.which('xdg-open'):
            params = {'path': str(contained(Path(value['vault']), value['note']))} if value.get('note') else {'path': value['vault']}
            subprocess.Popen(['xdg-open', 'obsidian://open?' + urlencode(params)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        os.execvp('tmux', ['tmux', 'switch-client' if os.environ.get('TMUX') else 'attach-session', '-t', '=' + session])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('name')
    add.add_argument('directory', type=Path)
    add.add_argument('--vault')
    add.add_argument('--note', help='note path relative to vault')
    add.add_argument('--ros-setup', type=Path, help='explicitly trust and source this file in each new terminal')
    add.add_argument('--editor', default='nvim', help='executable name or path, without arguments')
    sub.add_parser('list')
    sub.add_parser('menu')
    opening = sub.add_parser('open')
    opening.add_argument('name')
    opening.add_argument('--detach', action='store_true')
    opening.add_argument('--preview', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'add':
        path = project_path(args.name)
        if path.exists():
            raise ValueError(f'Project exists; edit {path} to change it')
        directory = args.directory.expanduser()
        if not directory.is_absolute() and machine().get('project_root'):
            directory = Path(machine()['project_root']) / directory
        directory = directory.resolve()
        if not directory.is_dir():
            raise ValueError(f'Not a directory: {directory}')
        value = {'directory': str(directory), 'editor': args.editor}
        if args.ros_setup:
            setup = args.ros_setup.expanduser().resolve()
            if not setup.is_file():
                raise ValueError(f'Not a ROS setup file: {setup}')
            value['ros_setup'] = str(setup)
        vault = args.vault or machine().get('vault')
        if args.note and not vault:
            raise ValueError('--note requires --vault or a machine default vault')
        if vault:
            value['vault'] = str(vault_path(vault))
        if args.note:
            contained(Path(value['vault']), args.note)
            value['note'] = args.note
        write_json(path, value)
        print(f'Saved project {args.name}. Open with: underlight-project open {args.name}')
    elif args.command in ('list', 'menu'):
        names = sorted(path.stem for path in (config_root() / 'projects').glob('*.json'))
        if args.command == 'list':
            print('\n'.join(names))
        elif not names:
            raise ValueError('No saved projects; use underlight-project add NAME DIRECTORY')
        else:
            selected = choose('Project workspace', names)
            if selected:
                open_project(selected)
    else:
        open_project(args.name, args.detach, args.preview)
