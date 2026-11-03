"""Shared launcher and RAG disclosure policy. This is not a network sandbox."""
import argparse
import ipaddress
import os
from urllib.parse import urlsplit

from .common import choose, config_root, read_json, write_json

MODES = {
    'local': 'Local tools only; RAG results cannot be returned to external clients.',
    'local-answer': 'External clients allowed; RAG shares answers and source metadata, not raw chunks.',
    'cloud-context': 'External clients allowed; RAG may share raw note and code excerpts.',
}


def mode():
    selected = os.environ.get('UNDERLIGHT_PRIVACY')
    if selected is None:
        selected = read_json(config_root() / 'privacy.json').get('mode', 'local')
    if selected not in MODES:
        raise ValueError('Invalid privacy mode; use underlight-privacy set local')
    return selected


def check_client(agent):
    selected = mode()
    if selected == 'local' and agent not in ('ollama', 'qwen', 'rag'):
        raise ValueError(f'{agent} may use cloud providers. Local mode blocks this launch. '
                         'Choose underlight-privacy set local-answer or cloud-context explicitly.')
    return selected


def check_export(raw=False):
    selected = mode()
    if selected == 'local' or (raw and selected != 'cloud-context'):
        required = 'cloud-context' if raw else 'local-answer'
        raise ValueError(f'Privacy mode {selected} blocks this RAG result. '
                         f'Use underlight-privacy set {required} to allow it, '
                         'or underlight-rag ask for a local terminal answer.')
    return selected


def check_ollama(base, model):
    # RAG's local-answer contract also requires local inference in cloud-context.
    parsed = urlsplit(base if '://' in base else 'http://' + base)
    host = parsed.hostname
    try:
        loopback = host == 'localhost' or ipaddress.ip_address(host or '').is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme not in ('http', 'https') or not loopback or parsed.username or parsed.password:
        raise ValueError('Local inference requires a loopback Ollama URL (localhost, 127.0.0.1 or ::1)')
    if 'cloud' in model.lower():
        raise ValueError('Cloud Ollama models are not allowed for local inference; choose a downloaded local model')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('status')
    sub.add_parser('menu')
    setting = sub.add_parser('set')
    setting.add_argument('mode', choices=MODES)
    check = sub.add_parser('check-client')
    check.add_argument('agent')
    ollama = sub.add_parser('check-ollama')
    ollama.add_argument('model')
    ollama.add_argument('url', nargs='?', default=os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434'))
    args = parser.parse_args(argv)
    if args.command == 'check-client':
        check_client(args.agent)
        return
    if args.command == 'check-ollama':
        check_ollama(args.url, args.model)
        return
    if args.command == 'menu':
        labels = {f'{key} — {text}': key for key, text in MODES.items()}
        chosen = choose('AI privacy', list(labels))
        if chosen is None:
            return
        args.mode = labels[chosen]
    if args.command in ('set', 'menu'):
        write_json(config_root() / 'privacy.json', {'mode': args.mode})
        if os.environ.get('UNDERLIGHT_PRIVACY'):
            print('This shell still has an UNDERLIGHT_PRIVACY override; unset it to use the saved mode.')
    selected = mode()
    print(f'{selected}: {MODES[selected]}')
    print('Applies to new Underlight launches and RAG requests. Already-running clients keep their own access.')
