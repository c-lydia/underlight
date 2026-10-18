#!/usr/bin/env python3
"""Exercise vault changes and rollback without opening Obsidian."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".local/bin/underlight-obsidian"


class ObsidianSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "Vault with spaces"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.state = self.root / "state"
        self.env = {**os.environ, "XDG_STATE_HOME": str(self.state)}
        self.write("app", {"vimMode": True, "newFileLocation": "root"})
        self.write("appearance", {"enabledCssSnippets": ["my-style"], "cssTheme": "My theme"})
        self.write("core-plugins", {"templates": False, "canvas": False})
        self.write("community-plugins", ["existing-plugin"])
        self.write("hotkeys", {"other-command": [{"modifiers": ["Alt", "Mod"], "key": "D"}]})

    def write(self, name, data):
        (self.vault / f".obsidian/{name}.json").write_text(json.dumps(data))

    def read(self, name):
        return json.loads((self.vault / f".obsidian/{name}.json").read_text())

    def run_helper(self, *args, success=True):
        result = subprocess.run([sys.executable, str(HELPER), *map(str, args)],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return result

    def backups(self):
        return list((self.state / "underlight/obsidian").glob("*/manifest.json"))

    def test_apply_preserves_settings_and_custom_shortcuts(self):
        self.run_helper(self.vault)
        self.assertTrue(self.read("app")["vimMode"])
        self.assertEqual(self.read("app")["newFileFolderPath"], "00 Inbox")
        self.assertEqual(self.read("appearance")["enabledCssSnippets"], ["my-style", "underlight"])
        self.assertEqual(self.read("appearance")["cssTheme"], "My theme")
        self.assertTrue(self.read("core-plugins")["templates"])
        self.assertFalse(self.read("core-plugins")["canvas"])
        self.assertEqual(self.read("community-plugins"), ["existing-plugin"])
        self.assertNotIn("daily-notes", self.read("hotkeys"))
        self.assertIn("insert-template", self.read("hotkeys"))
        self.assertTrue((self.vault / self.read("daily-notes")["template"]).is_file())
        self.assertTrue((self.vault / "91 Attachments").is_dir())

    def test_reapply_preserves_notes_and_is_idempotent(self):
        self.run_helper(self.vault)
        note = self.vault / "90 Templates/Project.md"
        note.write_text("My customized project template")
        self.run_helper(self.vault)
        self.assertEqual(note.read_text(), "My customized project template")
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(len(self.read("bookmarks")["items"]), 1)

    def test_rollback_restores_originals_and_preserves_later_edits(self):
        original = (self.vault / ".obsidian/app.json").read_bytes()
        self.run_helper(self.vault)
        home = self.vault / "Underlight Home.md"
        home.write_text("My edited home")
        self.run_helper("--restore", self.backups()[0].parent)
        self.assertEqual((self.vault / ".obsidian/app.json").read_bytes(), original)
        self.assertEqual(home.read_text(), "My edited home")
        self.assertFalse((self.vault / ".obsidian/snippets/underlight.css").exists())
        self.assertFalse((self.vault / "90 Templates/Daily.md").exists())
        self.assertEqual(self.read("community-plugins"), ["existing-plugin"])

    def test_malformed_config_makes_no_changes(self):
        original = (self.vault / ".obsidian/app.json").read_bytes()
        (self.vault / ".obsidian/appearance.json").write_text("{bad json")
        self.run_helper(self.vault, success=False)
        self.assertEqual((self.vault / ".obsidian/app.json").read_bytes(), original)
        self.assertFalse((self.vault / "00 Inbox").exists())

    def test_symlink_refusal_makes_no_changes(self):
        outside = self.root / "external"
        outside.mkdir()
        (self.vault / "90 Templates").symlink_to(outside, target_is_directory=True)
        self.run_helper(self.vault, success=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.vault / "00 Inbox").exists())

    def test_legacy_core_list_and_existing_command_binding(self):
        self.write("core-plugins", ["canvas"])
        self.write("hotkeys", {"daily-notes": []})
        self.run_helper(self.vault)
        self.assertIn("templates", self.read("core-plugins"))
        self.assertIn("canvas", self.read("core-plugins"))
        self.assertEqual(self.read("hotkeys")["daily-notes"], [])


if __name__ == "__main__":
    unittest.main()
