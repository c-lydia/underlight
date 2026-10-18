import os
from pathlib import Path
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[4] / "bin/underlight-laptop"


class LauncherTests(unittest.TestCase):
    def test_bundled_updates_take_precedence_and_explicit_override_is_respected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bundled = home / "data/underlight/give_laptop_ac"
            legacy = home / "projects/give_laptop_ac"
            for project in (bundled, legacy):
                project.mkdir(parents=True)
                (project / "main.py").write_text("# fixture")
            python = legacy / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$1" "${PYTHONPATH-unset}"\n')
            python.chmod(0o755)
            env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
                   "PYTHONPATH": "/unrelated/ros", "GIVE_LAPTOP_AC_HOME": ""}
            def launch():
                return subprocess.check_output(["bash", str(LAUNCHER), "--inline"], env=env, text=True).splitlines()
            self.assertEqual(launch(), [str(bundled / "main.py"), "unset"])
            env["GIVE_LAPTOP_AC_HOME"] = str(legacy)
            self.assertEqual(launch(), [str(legacy / "main.py"), "unset"])
