"""Preview, save and restore a bounded selection of desktop configuration files."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid

from .common import atomic_write, state_root, write_json

# Never recursively copy a home, vault, AI account directory, or runtime store.
EXACT = {
    '.config/hypr/hyprland.conf', '.config/kitty/kitty.conf',
    '.config/waybar/config.jsonc', '.config/waybar/style.css',
    '.config/wofi/config', '.config/wofi/style.css', '.config/mako/config',
    '.config/underlight/host.conf', '.config/underlight/machine.json',
    '.config/underlight/capture.json', '.config/underlight/luma.json',
    '.config/underlight/privacy.json', '.config/underlight/widgets.css', '.config/underlight/gpu-policy',
    '.config/systemd/user/underlight-wallpaper.service', '.ssh/config',
}
GROUPS = {'.config/hypr/underlight': '.conf', '.ssh/config.d': '.conf',
          '.config/underlight/projects': '.json', '.config/underlight/machines': '.json',
          '.config/nvim/after/plugin': '.lua'}
MAX_FILE = 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
SECRET = re.compile(
    r'-----BEGIN [^-]*PRIVATE KEY-----|'
    r'(?i:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret)\s*["\x27]?\s*[:=]\s*["\x27]?[^\s"\x27,}]+|'
    r'https?://[^/\s:@]+:[^/\s@]+@|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})')


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name:
        return False
    return name in EXACT or (str(path.parent) in GROUPS and path.suffix == GROUPS[str(path.parent)])


def collect(home):
    paths = set(EXACT)
    for directory, suffix in GROUPS.items():
        paths.update(str(p.relative_to(home)) for p in (home / directory).glob('*' + suffix))
    files, skipped = {}, []
    total = 0
    for name in sorted(paths):
        path = home / name
        if not path.exists():
            continue
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            skipped.append(f'{name}: not a small regular file')
            continue
        data = path.read_bytes()
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            skipped.append(f'{name}: binary file')
            continue
        if SECRET.search(text):
            skipped.append(f'{name}: possible credential; excluded')
            continue
        total += len(data)
        if total > MAX_TOTAL:
            raise ValueError('Configuration exceeds the 16 MiB snapshot limit')
        files[name] = {'data': base64.b64encode(data).decode(),
                       'sha256': hashlib.sha256(data).hexdigest()}
    return {'version': 1, 'created': datetime.now(timezone.utc).isoformat(), 'files': files}, skipped


def load_snapshot(path):
    if path.stat().st_size > MAX_TOTAL * 2:
        raise ValueError('Snapshot is too large')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('files'), dict):
        raise ValueError('Unsupported snapshot format')
    files = {}
    total = 0
    for name, entry in value['files'].items():
        if not allowed(name):
            raise ValueError(f'Snapshot contains an unapproved path: {name}')
        if not isinstance(entry, dict):
            raise ValueError(f'Invalid snapshot entry: {name}')
        data = base64.b64decode(entry.get('data', ''), validate=True)
        total += len(data)
        if len(data) > MAX_FILE or total > MAX_TOTAL:
            raise ValueError('Snapshot exceeds size limits')
        if hashlib.sha256(data).hexdigest() != entry.get('sha256'):
            raise ValueError(f'Snapshot checksum mismatch: {name}')
        if SECRET.search(data.decode('utf-8')):
            raise ValueError(f'Snapshot contains a possible credential: {name}')
        files[name] = data
    return files


def plan_restore(home, files):
    changes = []
    for name, data in files.items():
        target = home / name
        if target.is_file() and target.read_bytes() == data:
            continue
        # File symlinks may be replaced, but never write through a directory link
        # into the dotfiles checkout or another user's directory.
        for parent in target.parents:
            if parent == home:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError(f'Restore blocked by parent path {parent}; use --target with a clean staging directory')
        if target.exists() and not target.is_file():
            raise ValueError(f'Restore would replace a non-file: {target}')
        changes.append((name, target, data))
    return changes


def restore(home, files, apply=False):
    changes = plan_restore(home, files)
    for name, target, _ in changes:
        print(f'{"Replace" if target.exists() or target.is_symlink() else "Create"}: {name}')
    if not apply or not changes:
        print(f'{len(changes)} change(s). ' + ('Use --apply to restore.' if changes and not apply else ''))
        return
    backup = state_root() / 'snapshot-rollbacks' / uuid.uuid4().hex
    backup.mkdir(parents=True, mode=0o700)
    applied = []
    try:
        for name, target, data in changes:
            prior = backup / 'files' / name
            existed = target.exists() or target.is_symlink()
            target.parent.mkdir(parents=True, exist_ok=True)
            if existed:
                prior.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, prior)
            applied.append((target, prior, existed))
            atomic_write(target, data)
        write_json(backup / 'manifest.json', {'target': str(home), 'paths': [name for name, _, _ in changes]})
    except Exception:
        for target, prior, existed in reversed(applied):
            target.unlink(missing_ok=True)
            if existed:
                os.replace(prior, target)
        raise
    print(f'Restored {len(changes)} file(s). Previous files and symlinks: {backup}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create', help='preview unless --output is supplied')
    create.add_argument('--home', type=Path, default=Path.home())
    create.add_argument('--output', type=Path)
    listing = sub.add_parser('inspect')
    listing.add_argument('snapshot', type=Path)
    restoring = sub.add_parser('restore', help='preview unless --apply is supplied')
    restoring.add_argument('snapshot', type=Path)
    restoring.add_argument('--target', type=Path, default=Path.home())
    restoring.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'create':
        value, skipped = collect(args.home.expanduser().resolve())
        print('\n'.join(value['files']))
        for item in skipped:
            print('Skipped: ' + item)
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise ValueError('Output already exists; choose a new snapshot filename')
            write_json(args.output, value)
            print(f'Saved {len(value["files"])} file(s): {args.output}')
        else:
            print('Preview only. Add --output FILE.json to save.')
    elif args.command == 'inspect':
        print('\n'.join(load_snapshot(args.snapshot)))
    else:
        restore(args.target.expanduser().resolve(), load_snapshot(args.snapshot), args.apply)
