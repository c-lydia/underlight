# Underlight Guide

This vault matches the Underlight desktop: navy surfaces, cyan focus accents,
pink highlights, Ubuntu Sans text, and Noto Sans Mono code. The appearance lives
in **Settings → Appearance → CSS snippets → underlight**. Switch it off to
disable the styling, or edit the snippet to adjust it.

## A small daily loop

1. Open today's daily note with **Ctrl+Alt+D** and choose a main outcome.
2. Capture loose thoughts with **Ctrl+N**. New notes go into `00 Inbox`.
3. Name the note, then use **Ctrl+Alt+T** to insert a template.
4. Move useful notes into Projects, Research, Knowledge, or Journal using the
   file menu. Links update automatically when you rename or move notes.
5. At the end of the day, record what changed and the next action.

Existing custom hotkeys are preserved. If either shortcut was already occupied,
use **Ctrl+P → Open today's daily note** or **Templates: Insert template**, and
set your preferred keys in Settings → Hotkeys.

## Folders

| Folder | Purpose |
| --- | --- |
| `00 Inbox` | Quick capture; sort when it becomes useful |
| `01 Daily` | Daily planning, work log, and brief reflection |
| `02 Projects` | Outcomes, decisions, experiments, and next actions |
| `03 Research` | Paper notes, lectures, sources, and reading questions |
| `04 Knowledge` | Reusable concepts, equations, and explanations |
| `05 Journal` | Longer personal reflections and weekly reviews |
| `90 Templates` | Templates for the built-in Templates command |
| `91 Attachments` | Newly pasted images, PDFs, and attachments |
| `99 Archive` | Finished work you want to keep |

## Engineering and research

Use **Project** to define an outcome and a concrete test of success. Use
**Experiment** for a debugging session or measurement: preserve the setup,
command, expected result, observed result, and next test. Use **Research** for
papers and lectures, then distill useful ideas into **Concept** notes.

Link related notes with `[[note name]]`. Markdown code fences, LaTeX equations,
PDF attachments, and Mermaid diagrams work in Obsidian. Keep large source
repositories, datasets, builds, and rosbags outside the vault; link to them from
your project notes. Existing files are left in place.

The home note uses built-in search queries for tasks, inbox notes, projects, and
research. The setup does not require additional community plugins. Your current
plugins remain enabled as before. These templates use the built-in Templates
plugin and its `{{date}}`, `{{time}}`, and `{{title}}` placeholders.

## Review and journal

Use **Journal** whenever you want space to think. Once a week, create a note in
`05 Journal` and insert **Weekly Review**. Choose what to continue, change, or
stop. Move finished projects to `99 Archive` when they no longer need attention.

## Maintain and undo

Underlight's source assets are in
`~/.local/share/underlight/obsidian/`. After updating Underlight, close Obsidian
and run `underlight-obsidian /path/to/vault` to reapply the settings and CSS.
Existing notes and templates are preserved, so your edits survive reapplication.

Every apply that changes files prints a backup path under
`~/.local/state/underlight/obsidian/` (or `$XDG_STATE_HOME/underlight/obsidian/`).
Close Obsidian, then run `underlight-obsidian --restore /path/to/backup` to undo
that apply. Rollback preserves files edited after setup and reports them;
original versions remain in the backup's `original/` directory for comparison.
Empty folders are retained. Reopen the vault after changing settings.

Reference: [CSS snippets](https://obsidian.md/help/snippets),
[Daily notes](https://obsidian.md/help/Plugins/Daily%2Bnotes),
[Templates](https://obsidian.md/help/plugins/templates).
