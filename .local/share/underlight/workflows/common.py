import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def config_root():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'underlight'


def state_root():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'underlight'


def read_json(path, default=None):
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return value


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2) + '\n').encode())


def valid_name(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Names must be 1–64 letters, numbers, underscores or dashes, starting with a letter or number')
    return value


def choose(prompt, choices=None):
    command = ['wofi', '--dmenu', '--insensitive', '--prompt', prompt]
    if choices is not None:
        command += ['--no-custom-entry']
    result = subprocess.run(command, input='\n'.join(choices or []), text=True, capture_output=True)
    if result.returncode:
        return None
    value = result.stdout.strip()
    if not value or (choices is not None and value not in choices):
        return None
    return value


def notify(title, message):
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('notify-send'):
        try:
            subprocess.run(['notify-send', title, message], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def machine():
    return read_json(config_root() / 'machine.json')


def vault_path(explicit=None):
    value = explicit or read_json(config_root() / 'capture.json').get('vault')
    value = value or machine().get('vault') or read_json(config_root() / 'luma.json').get('vault')
    if not value:
        raise ValueError('Select a vault first: underlight-capture setup /path/to/vault')
    path = Path(value).expanduser().resolve()
    if not (path / '.obsidian').is_dir():
        raise ValueError(f'Not an existing Obsidian vault: {path}')
    return path


def contained(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or any(p in ('.', '..') for p in relative.parts):
        raise ValueError(f'Expected a relative path inside {root}: {relative}')
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path leaves {root}: {relative}')
    return path
