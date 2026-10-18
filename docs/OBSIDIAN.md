# Obsidian in Underlight

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
