"""Capture text, links, clipboard text and screenshots into an Obsidian inbox."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
from urllib.parse import quote
import uuid

from .common import choose, config_root, contained, notify, read_json, vault_path, write_json


def save_capture(vault, text, title='Quick capture', image=None, inbox='00 Inbox'):
    folder = contained(vault, inbox)
    folder.mkdir(parents=True, exist_ok=True)
    title = ' '.join(title.split())[:160] or 'Quick capture'
    stamp = datetime.now().astimezone()
    identifier = stamp.strftime('%Y-%m-%d_%H-%M-%S') + '_' + uuid.uuid4().hex[:8]
    path = folder / f'{identifier}.md'
    attachment = None
    if image is not None:
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Screenshot did not produce a PNG image')
        attachments = contained(vault, '90 Attachments/Captures')
        attachments.mkdir(parents=True, exist_ok=True)
        attachment = attachments / f'{identifier}.png'
        with attachment.open('xb') as stream:
            stream.write(image)
        os.chmod(attachment, 0o600)
        text += f'\n\n![Screenshot]({quote(os.path.relpath(attachment, folder))})'
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(f'# {title}\n\nCaptured: {stamp.isoformat(timespec="seconds")}\n\n{text.strip()}\n')
        os.chmod(path, 0o600)
    except Exception:
        if attachment:
            attachment.unlink(missing_ok=True)
        raise
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', help='override the saved vault for this capture')
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('setup')
    setup.add_argument('directory')
    setup.add_argument('--inbox', default='00 Inbox')
    sub.add_parser('menu')
    sub.add_parser('clipboard')
    sub.add_parser('screenshot')
    text = sub.add_parser('text')
    text.add_argument('text', nargs='?', help='omit to read stdin')
    text.add_argument('--title', default='Quick capture')
    link = sub.add_parser('link')
    link.add_argument('url')
    args = parser.parse_args(argv)
    if args.command == 'setup':
        vault = vault_path(args.directory)
        contained(vault, args.inbox)
        write_json(config_root() / 'capture.json', {'vault': str(vault), 'inbox': args.inbox})
        print(f'Quick capture: {vault / args.inbox}')
        return
    vault = vault_path(args.vault)
    settings = read_json(config_root() / 'capture.json')
    command = args.command
    if command == 'menu':
        selected = choose('Capture to Obsidian', ['Thought', 'Link', 'Clipboard text', 'Screenshot'])
        if not selected:
            return
        command = {'Thought': 'text', 'Link': 'link', 'Clipboard text': 'clipboard', 'Screenshot': 'screenshot'}[selected]
        if command in ('text', 'link'):
            value = choose('Thought' if command == 'text' else 'URL')
            if not value:
                return
            args.text = args.url = value
    image = None
    if command == 'screenshot':
        selection = subprocess.run(['slurp'], capture_output=True, text=True)
        if selection.returncode or not selection.stdout.strip():
            return
        import time
        time.sleep(0.2)
        image = subprocess.run(['grim', '-g', selection.stdout.strip(), '-'], check=True, capture_output=True).stdout
        content = ''
    elif command == 'clipboard':
        content = subprocess.run(['wl-paste', '--no-newline', '--type', 'text'], check=True,
                                 capture_output=True, text=True, timeout=5).stdout
    elif command == 'link':
        from urllib.parse import urlsplit
        if urlsplit(args.url).scheme not in ('http', 'https') or not urlsplit(args.url).netloc:
            raise ValueError('Use a complete http:// or https:// link')
        content = args.url
    else:
        import sys
        content = args.text if args.text is not None else sys.stdin.read()
    if not content.strip() and image is None:
        raise ValueError('Nothing to capture')
    path = save_capture(vault, content, getattr(args, 'title', 'Quick capture'), image,
                        settings.get('inbox', '00 Inbox'))
    print(path)
    notify('Saved to Obsidian inbox', str(path))
