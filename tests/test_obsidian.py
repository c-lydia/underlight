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

    def prepare_ai(self):
        for plugin in ("copilot", "github-copilot"):
            (self.vault / ".obsidian/plugins" / plugin).mkdir(parents=True)
        self.write("plugins/copilot/manifest", {"version": "4.0.15"})
        self.write("plugins/github-copilot/data", {"nodePath": "default", "chatSettings": {"accessToken": "keep-me"}})
        self.write("plugins/copilot/data", {
            "agentMode": {"deviceProfiles": {"this-device": {"opencode": {
                "binaryPath": sys.executable, "binarySource": "managed",
                "envOverrides": {"KEEP": "yes"}}}}},
            "providers": {"native": {"origin": {"kind": "agent", "agentType": "opencode"}}},
        })
        self.rag = self.root / "rag.yaml"
        self.rag.write_text(json.dumps({"home": {"root": "/original"},
            "store": {"dir": "/existing/store", "tables": {"home": "idx_home", "projects": "idx_projects"}},
            "assistant": {}, "embedder": {}, "ollama": {"base_url": "http://localhost:11434"}, "chat": {}, "chunking": {}}))
        return [self.vault, "--ai", "--node-path", sys.executable,
                "--rag-config", self.rag, "--model", "github-copilot/example"]

    def test_ai_preserves_credentials_and_profiles_with_idempotent_rollback(self):
        args = self.prepare_ai()
        original = (self.vault / ".obsidian/plugins/copilot/data.json").read_bytes()
        self.run_helper(*args)
        data = self.read("plugins/copilot/data")
        profile = data["agentMode"]["deviceProfiles"]["this-device"]["opencode"]
        self.assertEqual(profile["envOverrides"]["KEEP"], "yes")
        self.assertEqual(profile["binarySource"], "managed")
        self.assertEqual(self.read("plugins/github-copilot/data")["chatSettings"]["accessToken"], "keep-me")
        self.assertEqual(self.read("app")["newFileLocation"], "root")
        self.assertEqual(self.read("community-plugins"), ["existing-plugin"])
        self.assertIn("underlight_rag", self.read("underlight-opencode")["mcp"]["servers"])
        self.run_helper(*args)
        self.assertEqual(len(self.backups()), 1)
        self.run_helper("--restore", self.backups()[0].parent)
        self.assertEqual((self.vault / ".obsidian/plugins/copilot/data.json").read_bytes(), original)
        self.assertFalse((self.vault / ".obsidian/underlight-rag.yaml").exists())

    def test_ai_keeps_project_store_and_isolates_vault_table(self):
        import yaml
        self.run_helper(*self.prepare_ai())
        cfg = yaml.safe_load((self.vault / ".obsidian/underlight-rag.yaml").read_text())
        self.assertEqual(cfg["store"]["dir"], "/existing/store")
        self.assertEqual(cfg["store"]["tables"]["projects"], "idx_projects")
        self.assertTrue(cfg["store"]["tables"]["home"].startswith("idx_obsidian_"))
        self.assertEqual(cfg["home"]["root"], str(self.vault))
        self.assertIn(".obsidian", cfg["home"]["exclude"])

    def test_ai_enables_alternative_models_without_changing_default(self):
        self.run_helper(*self.prepare_ai(), "--enable-model", "ollama/example", "--cpu-embeddings")
        data = self.read("plugins/copilot/data")
        self.assertEqual(data["agentMode"]["backends"]["opencode"]["defaultModel"]["baseModelId"],
                         "github-copilot/example")
        enabled = set(data["backends"]["opencode"]["enabledModels"])
        self.assertEqual({m["info"]["id"] for m in data["configuredModels"] if m["configuredModelId"] in enabled},
                         {"github-copilot/example", "ollama/example"})
        import yaml
        cfg = yaml.safe_load((self.vault / ".obsidian/underlight-rag.yaml").read_text())
        self.assertEqual(cfg["embedder"]["ollama_options"], {"num_gpu": 0, "num_thread": 4})

    def test_ai_keeps_auto_declared_during_async_provider_discovery(self):
        args = self.prepare_ai()
        args[-1] = "opencode/big-pickle"
        args.extend(["--enable-model", "github-copilot/auto"])
        self.run_helper(*args)
        self.assertEqual(self.read("underlight-opencode")["providers"]["github-copilot"]["models"],
                         {"auto": {}})
        before = self.read("plugins/copilot/data")
        self.run_helper(*args)
        after = self.read("plugins/copilot/data")
        self.assertEqual(before["configuredModels"], after["configuredModels"])
        self.assertEqual(after["backends"]["opencode"]["enabledModels"],
                         [m["configuredModelId"] for m in after["configuredModels"]])
        self.assertEqual(after["agentMode"]["backends"]["opencode"]["defaultModel"]["baseModelId"],
                         "opencode/big-pickle")

    def test_luma_install_preserves_plugins_and_rolls_back(self):
        self.run_helper(self.vault, '--luma')
        self.assertEqual(self.read('community-plugins'), ['existing-plugin', 'underlight-luma'])
        self.assertEqual(self.read('plugins/underlight-luma/manifest')['id'], 'underlight-luma')
        self.run_helper(self.vault, '--luma')
        self.assertEqual(len(self.backups()), 1)
        self.run_helper('--restore', self.backups()[0].parent)
        self.assertEqual(self.read('community-plugins'), ['existing-plugin'])
        self.assertFalse((self.vault / '.obsidian/plugins/underlight-luma/main.js').exists())

    def test_agent_connections_preserve_existing_settings_and_are_idempotent(self):
        plugin = self.vault / ".obsidian/plugins/agent-client"
        plugin.mkdir(parents=True)
        self.write("plugins/agent-client/manifest", {"id": "agent-client"})
        self.write("plugins/agent-client/data", {"customAgents": [{"id": "mine", "command": "custom"}],
                                               "defaultAgentId": "mine", "autoAllowPermissions": False})
        args = [self.vault, "--cursor", "--antigravity"]
        self.run_helper(*args)
        data = self.read("plugins/agent-client/data")
        self.assertEqual(data["defaultAgentId"], "mine")
        self.assertEqual(data["customAgents"][0], {"id": "mine", "command": "custom"})
        self.assertEqual([a["id"] for a in data["customAgents"]],
                         ["mine", "underlight-cursor", "underlight-antigravity"])
        self.assertFalse(data["autoAllowPermissions"])
        self.run_helper(*args)
        self.assertEqual(len(self.backups()), 1)
        self.run_helper("--restore", self.backups()[0].parent)
        self.assertEqual(len(self.read("plugins/agent-client/data")["customAgents"]), 1)

    def test_copilot_repair_rejects_unknown_bundle_without_changing_it(self):
        self.prepare_ai()
        path = self.vault / ".obsidian/plugins/copilot/main.js"
        path.write_text("different bundle")
        self.run_helper(self.vault, "--repair-copilot-view", success=False)
        self.assertEqual(path.read_text(), "different bundle")
        self.assertFalse(self.backups())

    def test_gpu_qwen_preserves_cpu_embedding_settings(self):
        import yaml
        self.run_helper(*self.prepare_ai(), "--gpu-qwen", "--cpu-embeddings")
        cfg = yaml.safe_load((self.vault / ".obsidian/underlight-rag.yaml").read_text())
        self.assertEqual(cfg["ollama"]["options"]["num_gpu"], 99)
        self.assertTrue(cfg["ollama"]["think"])
        self.assertEqual(cfg["embedder"]["ollama_options"]["num_gpu"], 0)
        self.assertEqual(self.read('underlight-opencode')['providers']['ollama']['models']['qwen3:4b']['limit'],
                         {'context': 6144, 'output': 2048})

    def test_native_rag_bridge_uses_host_install_inside_isolated_opencode(self):
        home = self.root / 'fake-home'
        (home / '.local/bin').mkdir(parents=True)
        fake = home / '.local/bin/underlight-rag'
        fake.write_text('#!/bin/sh\nprintf "%s\\n%s\\n%s\\n" "$XDG_DATA_HOME" "$RAG_CONFIG" "$1"\n')
        fake.chmod(0o755)
        config = self.root / 'vault rag.yaml'; config.write_text('test')
        env = {**self.env, 'HOME': str(home), 'XDG_DATA_HOME': '/isolated/opencode',
               'UNDERLIGHT_HOST_XDG_DATA_HOME': str(home / '.local/share')}
        result = subprocess.run([str(ROOT / '.local/bin/underlight-obsidian-rag'), str(config)],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), [str(home / '.local/share'), str(config), 'mcp'])

    def test_notebooklm_repair_is_guarded_idempotent_and_reversible(self):
        plugin = self.vault / '.obsidian/plugins/star-notebooklm'; plugin.mkdir(parents=True)
        self.write('plugins/star-notebooklm/manifest', {'version': '1.2.4'})
        script = plugin / 'main.js'
        original = 'const url="https://notebooklm.google.com";\n      this.webview.addEventListener("dom-ready", () => {\n});'
        script.write_text(original)
        args = [self.vault, '--repair-notebooklm']
        self.run_helper(*args); self.run_helper(*args)
        self.assertEqual(len(self.backups()), 1)
        self.assertIn('https://notebook.google.com', script.read_text())
        self.assertIn('did-fail-load', script.read_text())
        self.run_helper('--restore', self.backups()[0].parent)
        self.assertEqual(script.read_text(), original)

    def test_ai_refuses_to_replace_another_opencode_config(self):
        args = self.prepare_ai()
        data = self.read("plugins/copilot/data")
        data["agentMode"]["deviceProfiles"]["this-device"]["opencode"]["envOverrides"]["OPENCODE_CONFIG"] = "/custom/config.json"
        self.write("plugins/copilot/data", data)
        self.run_helper(*args, success=False)
        self.assertEqual(self.read("plugins/github-copilot/data")["nodePath"], "default")
        self.assertFalse((self.vault / ".obsidian/underlight-opencode.json").exists())


if __name__ == "__main__":
    unittest.main()
