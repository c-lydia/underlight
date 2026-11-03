import importlib
import subprocess
import sys
from .common import notify


def main(name):
    try:
        importlib.import_module('workflows.' + name).main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f'underlight-{name}: {exc}', file=sys.stderr)
        notify('Underlight ' + name, str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
