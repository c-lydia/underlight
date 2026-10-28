# Obsidian in Underlight

## Copilot, OpenCode, and local RAG

`underlight-obsidian --ai` configures the installed **Copilot for Obsidian V4**
and **GitHub Copilot** plugins. It preserves sign-ins, unrelated settings,
existing models, and the selected OpenCode binary unless `--opencode-path` is
specified. Close Obsidian before applying; the command prints a guarded rollback
backup, as the appearance installer does.

For Flatpak, allow the host bridge once:

```bash
flatpak override --user --talk-name=org.freedesktop.Flatpak md.obsidian.Obsidian
```

This allows Obsidian to launch host commands. The RAG bridge uses it to run the
existing host Python environment, rather than Flatpak's different Python and
XDG directories. Choose an installed Node 22+ executable accessible under your
home directory for the GitHub Copilot plugin.

```bash
underlight-obsidian /path/to/vault --ai \
  --node-path "$HOME/.nvm/versions/node/v22.23.3/bin/node" \
  --model github-copilot/auto \
  --enable-model ollama/qwen3:4b \
  --enable-model opencode/big-pickle \
  --cpu-embeddings
RAG_CONFIG=/path/to/vault/.obsidian/underlight-rag.yaml underlight-rag index --table home
```

Use only model IDs supported by your account and OpenCode version. Repeat
`--enable-model` to add alternatives to the Copilot chat picker; `--model` sets
the default. Switching models in that picker retains the same RAG tools.
The generated OpenCode configuration uses the **OpenCode 2** `mcp.servers`
schema. Its three tools search local knowledge, answer through local Ollama,
and report index status. Retrieved excerpts may be sent to the model selected
in the chat.

Notes are indexed into a separate `idx_obsidian_<vault-hash>` table in the
existing RAG store. Markdown/text notes are included; `.obsidian`, `.git`,
`.trash`, Copilot conversations, and `node_modules` are excluded. Project
indices are preserved. Repeat the index command after editing notes; unchanged
chunks are cached. `--cpu-embeddings` sets Ollama `num_gpu=0` and `num_thread=4`
for this vault, useful when GPU embedding stalls. Changing embedding settings
on an existing vault table requires adding `--rebuild` once.

### GitHub Student accounts

Use the account's live model catalog and verify requests before enabling a
model. Student access can differ between clients: in the tested account the
Copilot CLI exposed Auto, while OpenCode also successfully used GPT-4.1.
Other requested models returned `model_not_supported`; listing a model in
configuration does not grant access. See
[GitHub's model-access policy](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/configure-access-to-ai-models).

OpenCode 2.0.22 does not implement that Auto route. The upstream fix is
[PR #55960](https://github.com/anomalyco/opencode/pull/55960). The optional
`underlight-obsidian-opencode` launcher expects a Student-compatible executable
at `~/.local/share/underlight/opencode-student/bin/opencode` and isolates its
config, database, cache, and state under
`~/.local/share/underlight/obsidian-opencode/`. The normal installer only links
the launcher; it does not download a build or copy credentials.

When using that executable, add
`--opencode-path ~/.local/bin/underlight-obsidian-opencode` to the AI setup
command. Authenticate it inside the same Flatpak environment as Obsidian, or
import an existing OpenCode credential export through stdin without saving it
in a vault or repository. This keeps the normal terminal OpenCode and the
plugin-managed database intact for rollback.

The tested local build uses upstream commit
`5fd70f6f1d4631092ed2e503fba74770fb808d14` on `copilot-student`, Bun `1.4.4`,
and version `2.1.4-student.5fd70f6`. Build from that checkout with:

```bash
bun install --frozen-lockfile --filter '@opencode/cli' --filter '@opencode/script'
cd packages/cli
OPENCODE_CHANNEL=underlight-student OPENCODE_VERSION=2.1.4-student.5fd70f6 \
  bun run script/build.ts --single --skip-install --skip-web-ui
install -Dm755 dist/cli-linux-x64/bin/opencode \
  "$HOME/.local/share/underlight/opencode-student/bin/opencode"
```

This is an upstream development build, not a stable release. Its web UI is
omitted; Obsidian uses ACP. Keep the managed build available for rollback.
If the inherited `opencode-see-image` plugin stalls startup, add
`"plugins": ["-opencode-see-image"]` to the vault's
`.obsidian/underlight-opencode.json`. Reapplying AI setup preserves this setting.
After changing backends, create a new **Copilot Agent Chat**. Ensure
`github-copilot/auto` is enabled in Copilot's OpenCode model list before choosing
it; the backend catalogue and the chat's enabled-model list are separate.
The helper also declares an empty `providers.github-copilot.models.auto`
override. This keeps Auto in the initial catalogue while GitHub discovery is
still loading, so Copilot cannot remove and recreate its saved enabled-model
ID on restart. The native provider still supplies routing and model metadata.

## Appearance and workflow

The desktop installer links `.local/bin/underlight-obsidian` and
`.local/share/underlight/obsidian`. It does not install Obsidian or automatically
modify your vaults. The helper requires Python 3 and an existing vault with a
`.obsidian` directory; it works with both Flatpak and native installations.

Close Obsidian before applying settings, then run:

```sh
underlight-obsidian /path/to/vault
```

Reopen that vault and open **Underlight Home** from Bookmarks or the quick
switcher (`Ctrl+O`). Configuration files are copied and merged into the vault,
not symlinked, so Obsidian can save settings normally. Reapply after updating
Underlight to refresh the settings and CSS. Existing notes and templates are
never replaced; newly shipped notes/templates are added if absent.

## Included

- Dark navy surfaces with cyan and pink accents matching Kitty and Waybar.
- Ubuntu Sans text, Noto Sans Mono code, readable line width, and folding.
- New notes in `00 Inbox`; attachments in `91 Attachments`; automatic link updates.
- Daily notes in `01 Daily`, with planning, a work log, learning, and reflection.
- Project, experiment, research, concept, journal, and weekly review templates.
- A home note with native Obsidian searches for tasks, inbox, projects, and research.
- `Ctrl+Alt+D` for today's note and `Ctrl+Alt+T` for inserting a template,
  unless an existing custom binding occupies that combination or command.

Core Daily notes, Templates, Bookmarks, Outline, Backlinks, Search, and File
recovery are enabled in an existing core-plugin configuration. A new vault
without that file uses Obsidian's defaults. Community plugin settings, sync,
Git automation, other CSS snippets, open tabs, and existing notes remain intact.
No new plugins, network requests, or JavaScript queries are needed.

Assets live under `.local/share/underlight/obsidian/` in this repository.
`settings.json` contains the settings reapplied by the helper; `underlight.css`
contains the style; `vault/` holds the starter notes and templates. The built-in
Templates plugin handles `{{date}}`, `{{time}}`, and `{{title}}`; Templater is not
required. Disable the `underlight` CSS snippet in Appearance to disable its style.

## Backup and rollback

Each apply that changes files creates a private backup directory below
`${XDG_STATE_HOME:-~/.local/state}/underlight/obsidian/` and prints its path.
The backup contains the original changed files and a manifest. Close Obsidian,
then use the printed command:

```sh
underlight-obsidian --restore /path/to/backup
```

Rollback restores original files and removes new files only when their content
still matches the version installed by that apply. Later edits are preserved
and reported. Compare a skipped file with `original/` in the backup to restore
selected settings manually. Roll back multiple applies in reverse order.
Empty workflow folders and backups remain. Vault symlinks at managed paths are
rejected to avoid changing files outside the vault. The helper validates all
planned files before writing and detects concurrent saves during application;
close Obsidian first to prevent settings being overwritten by its running copy.

The normal `install.sh --restore` removes the helper/asset links; use the vault
backup command above before removing the helper to undo a vault configuration.

## Verification

```sh
python3 tests/test_obsidian.py
./tests/smoke.sh
```

The tests cover settings preservation, repeat application, custom hotkey
conflicts, edited notes, guarded rollback, malformed JSON, and symlink refusal.

Official references: [CSS snippets](https://obsidian.md/help/snippets),
[Daily notes](https://obsidian.md/help/Plugins/Daily%2Bnotes), and
[Templates](https://obsidian.md/help/plugins/templates).

## Host agents: Hermes, Copilot CLI, Cursor, Antigravity

Install the Agent Client community plugin, close Obsidian, then connect the
installed host agents using any combination of these flags:

```sh
underlight-obsidian /path/to/vault --hermes --copilot-cli --cursor --antigravity
```

The launchers use `flatpak-spawn --host` when needed. Credentials stay with
native applications. Agent Client keeps permission prompts enabled. Cursor and
Antigravity are separate agents in its agent selector, not entries in Copilot's
OpenCode model selector. Underlight's AI menu also launches their native CLIs.
The normal dotfile installer links wrappers and desktop entries; it does not
download proprietary runtimes or subscribe to plans.

- Cursor: install from `https://cursor.com/install`, then `cursor-agent login`.
  ACP uses `cursor-agent acp`. Free usage has limits; available models depend
  on the account. [Official ACP documentation](https://cursor.com/docs/cli/acp).
- Antigravity: install the CLI from `https://antigravity.google/cli/install.sh`.
  Obsidian uses Google's separate official ACP runtime, pinned to 1.4.3 under
  `~/.local/share/underlight/antigravity-acp/1.4.3/`. Obtain its archive and
  SHA-256 from the [ACP registry](https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json),
  verify the download, and extract both runtime files there. ACP sign-in is
  separate from CLI sign-in. The Individual plan is free with limits.
- Hermes: shares `~/.hermes/config.yaml` and its host login. Nous free models
  change over time: use its live recommended-models catalog and test a request.
  On 2026-10-28 Solar Mini 4 Free, Laguna XS/S 2.1 Free, and Step 3.7 Flash Free
  worked; Solar Pro 4's free period had ended. No paid fallback is configured.
- Copilot CLI: uses the installed `copilot --acp --stdio`; a vault-local MCP
  configuration connects it to the vault's RAG without changing global settings.

## GPU Qwen and RAG

Add `--gpu-qwen` to `--ai` setup to use local Qwen 4B, a 6144-token OpenCode context and 2048-token output budget,
GPU offload, thinking mode, and a 300-second cold-start timeout. The included
`ollama/qwen3-4b.Modelfile` preserves this installed model's thinking template
and sets GPU defaults. Apply it explicitly with `ollama create qwen3:4b -f
/path/to/ollama/qwen3-4b.Modelfile`. Embedding settings remain independent;
CPU embeddings leave GPU memory for generation. RAG retains its separate 4096-token
context. Existing indices are preserved.
RAG MCP returns an error when generation fails, rather than a successful answer
containing an error string.

## Copilot blank-panel repair

Copilot 4.0.15's relevant-notes hook assumes every historical message context
has `notes` and `urls`. Missing arrays or note paths can crash the entire chat.
Close Obsidian and run:

```sh
underlight-obsidian /path/to/vault --repair-copilot-view
```

This backs up the bundle and applies three guarded replacements matching the
source patch in `obsidian/copilot-4.0.15-context.patch`. It refuses unknown
versions or bundle contents. A plugin update replaces the repair; check the
upstream version before reapplying. Chat history and credentials are preserved.

## Shared Luma companion

Luma reuses the portfolio's four-pose tech-mage artwork. The desktop avatar
floats above windows; the Obsidian avatar sits inside the vault window. Click
her to open an agent, or use Escape to close the panel. Dock switches sides;
Motion toggles animation. Hide affects only the current surface.

```sh
underlight-obsidian /path/to/vault --luma
underlight-luma --show
```

The desktop entry **Underlight Luma** restores a hidden desktop avatar. In
Obsidian use **Luma: Open Luma AI launcher** in the command palette or its
sparkles ribbon icon. Preferences (`selected`, `dock`, `motion`, and per-surface
visibility) live in `~/.config/underlight/luma.json`. Set `vault` there to choose
the desktop agents' working directory. Both surfaces observe this file; it
contains no credentials. Agent history remains with each agent's own client.
Luma is a launcher, not an additional chat service. Account sign-ins and quotas
are those of the underlying agents. The desktop requires GTK3, PyGObject,
and gtk-layer-shell, also used by Underlight widgets.

## NotebookLM blank panel

Star NotebookLM 1.2.4 can leave a blank embedded page after a failed navigation.
Google's old `notebooklm.google.com` address redirects to `notebook.google.com`.
The guarded `--repair-notebooklm` command updates those links and adds visible
loading/failure text with directions to the existing Refresh and Notebook List
controls. It preserves the `persist:notebooklm` login partition. This repair
is verified for 1.2.4 only; plugin updates replace it. It does not automate
uploads or change any notebooks.
