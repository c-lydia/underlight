# Neovim workbench code walkthrough

This document explains the complete companion
[`c-lydia/neovim_config`](https://github.com/c-lydia/neovim_config) repository
that `Underlight/install.sh` clones into
`~/.local/share/underlight/neovim_config`. It describes the committed workbench
that a fresh install receives; local, uncommitted changes in an existing
`~/.config/nvim` checkout are intentionally not modified or incorporated here.

## 1. Startup architecture

```text
init.lua
├─ validates Neovim >= 0.11.3
├─ selects the 0.11 or 0.12 lockfile
├─ bootstraps lazy.nvim at its locked commit
├─ require("options")
├─ require("keymaps")
├─ require("reverse")
├─ require("workflows")
└─ lazy.setup("plugins")
   ├─ completion.lua
   ├─ debugging.lua
   ├─ lsp.lua
   ├─ tools.lua
   ├─ treesitter.lua
   └─ ui.lua
```

The configuration targets application development, embedded systems, reverse
engineering, security, databases, documentation, and the Underlight desktop.
The modules are divided by responsibility: core editor behavior loads eagerly;
Lazy plugin specifications control third-party features; `workbench/` contains
small platform-safe feature adapters.

## 2. Bootstrap: `init.lua`

`init.lua` sets Space as the global leader and backslash as the local leader
before any plugin loads. It refuses Neovim versions older than 0.11.3.

Neovim 0.11 and 0.12 use different Tree-sitter APIs, so startup selects
`lazy-lock.json` for 0.11 and `lazy-lock-0.12.json` for 0.12+. The helper
`locked_lazy_commit()` reads the chosen JSON file and extracts the exact
`lazy.nvim` revision.

If Lazy is absent, startup clones its stable branch into Neovim's data
directory and checks out the recorded commit. The resulting directory is
prepended to `runtimepath`. Core modules then load in a fixed order before
`lazy.setup("plugins")` discovers every file below `lua/plugins/`.

Lazy uses four concurrent operations to avoid exhausting DNS or file
descriptors during the large first install. Automatic change notifications and
Lua rocks are disabled, the selected lockfile is explicit, and the plugin UI
uses rounded borders.

## 3. Core editor behavior

### `lua/options.lua`

The defaults enable absolute and relative line numbers, two-space indentation,
spaces instead of tabs, smart indentation, an unwrapped view, cursor line,
scroll margins, a column-120 ruler, permanent sign column, smart-case search,
true color, right/below splits, system clipboard integration, persistent undo,
and completion menus without automatic selection. Swap and backup files are
disabled.

Python, C, C++, Java, Arduino, and CMake buffers switch locally to four-space
indentation. Filetype registration maps Arduino `.ino`/`.pde` to C++, ROS
interface extensions to `rosidl`, YARA files to `yara`, Sage files to `sage`,
and common Compose names to `yaml.docker-compose`.

The active-window code defines bright and dim separator highlights, dims
inactive normal windows, and enables the cursor line only in the current split.
It reapplies those decisions after color changes and window/buffer focus events
so the active editor remains visually obvious.

### `lua/keymaps.lua`

The keymap module centralizes mappings that do not belong to one plugin:

- `Ctrl+h/j/k/l` changes splits; Ctrl+arrows resize them.
- Shift+h/l changes buffers and `<leader>bd` deletes one.
- Visual indentation keeps the selection; visual J/K moves selected lines.
- Joined lines, half-page scrolling, and search results retain useful cursor
  placement.
- Leader-delete uses the black-hole register and visual leader-paste preserves
  the copied value.
- Ctrl+s saves from normal or insert mode.
- `<leader>cf`, `<leader>e`, `<leader>f*`, `<leader>g*`, `<leader>x*`,
  `<leader>t`, `<leader>db`, and `<leader>sr` dispatch formatting, tree,
  Telescope, Git, diagnostics, terminal, database, and replacement tools.
- Terminal Escape returns to normal mode.

LSP-local mappings are deliberately not defined here; `lsp.lua` attaches them
only to buffers with a language server.

## 4. Completion: `lua/plugins/completion.lua`

The completion stack lazy-loads on insert mode. `nvim-cmp` merges LSP, LuaSnip,
buffer, filesystem-path, command-line, and Dadbod SQL sources. LSP results have
the highest normal priority, SQL is next, followed by snippets, buffer words,
and paths.

LuaSnip loads the VS Code-compatible `friendly-snippets` collection.
Ctrl+j/k changes items, Ctrl+b/f scrolls documentation, Ctrl+Space opens the
menu, Ctrl+e aborts, and Enter confirms only an explicitly selected item. Tab
and Shift+Tab move through completion items or snippet fields before falling
back to their normal behavior. LSPkind adds source labels and icons; completion
and documentation windows use borders and ghost text previews the candidate.

The same engine provides buffer completion for `/` and `?`, plus path/command
completion after `:`. `nvim-autopairs` inserts matching delimiters and reacts to
confirmed completions. `nvim-ts-autotag` closes and renames HTML/JavaScript/
TypeScript/XML tags.

## 5. Language servers and developer tools

### `lua/plugins/lsp.lua`

The server inventory covers Python, C/C++, Java, JavaScript/TypeScript, HTML,
CSS, JSON, XML, Docker/Compose, SQL, Bash, CMake, Markdown, RST, Lua, YAML,
assembly, Rust, Go, and YARA.

Mason provides the package UI. `mason-tool-installer` installs formatters
(Stylua, Black, isort, clang-format, Google Java Format, Prettier, shfmt,
pgFormatter, XML formatter), linters (Ruff, mypy, eslint_d, Hadolint,
Markdownlint, ShellCheck, YARA), and CodeLLDB/debugpy. Go formatters, linter, and
Delve are added only when a Go toolchain exists. `NVIM_SKIP_TOOL_INSTALL=1`
disables network/tool setup during tests.

`mason-lspconfig` installs supported servers but omits YARA's separately
packaged server and skips assembly/Go/SQL tools when their host toolchains are
unavailable.

When a server attaches, buffer-local mappings provide definition/declaration,
references, implementation, hover, rename, code actions, type definition,
diagnostic movement, diagnostic float, and symbol outline. Diagnostics use
virtual text, signs, underline, severity sorting, and rounded floats.

Important server customization includes:

- Pyright basic workspace analysis, Sage support, auto-imports, and ROS Humble/
  Iron package paths.
- Clangd background indexing, clang-tidy, detailed completion, C++17 fallback,
  build-root detection, and embedded cross-compiler query drivers.
- JDTLS formatting/import organization and Fernflower source content.
- JSON/YAML SchemaStore integration.
- LuaJIT runtime awareness and Neovim runtime libraries.
- SQLS plugin attachment.
- Rust Analyzer with all Cargo features, Clippy, and proc macros.
- Gopls with gofumpt, staticcheck, placeholders, and extra analyses.

The module supports Neovim's modern `vim.lsp.config/enable` API and a legacy
`lspconfig` fallback. Optional executables are enabled only when present.
Lspsaga supplies previews, hover, actions, rename, breadcrumbs, and outline;
`lsp_signature` shows parameter help; Illuminate highlights matching symbols.

### `lua/plugins/tools.lua`

Telescope uses its native FZF sorter and ignores dependency folders, build
output, virtual environments, embedded binaries, and large AI model weights.

Conform maps each language to a formatter. Python runs isort then Black; C/C++
uses clang-format; web/data/document formats use Prettier or their native
formatter; shell, SQL, XML, Go, Rust, and Lua have dedicated tools. In the
committed configuration it formats before save with LSP fallback, except while
the safe hex view is active. `<leader>cf` also requests formatting manually.

`nvim-lint` runs after writes and after leaving insert mode. It maps Python to
Ruff/mypy, C/C++ to cppcheck, JS/TS to eslint_d, Dockerfiles to Hadolint,
Markdown to Markdownlint, shell to ShellCheck, and Go to golangci-lint.

The remainder of the file configures:

- Gitsigns with blame plus stage/reset/undo/preview hunk mappings.
- LazyGit.
- ToggleTerm with a general float and named ROS 2, Python, and PostgreSQL
  terminals.
- Trouble's diagnostic lists, Comment, and Surround.
- Dadbod and Dadbod UI. Connection data is stored below `stdpath("data")`, not
  in the Git checkout where credentials could be committed.
- Markdown Preview with a prebuilt server, Flatpak-aware browser bridge, binary
  version validation, and self-repair of incomplete plugin caches.
- Spectre search/replace and Flash navigation.
- Neominimap pinned to v3.16.0, disabled by default, with Tree-sitter
  integration only on Neovim 0.12.

## 6. Syntax parsing: `lua/plugins/treesitter.lua`

The parser set covers the supported programming languages, web/data formats,
build/infrastructure files, documents, SQL, shells, Vim/Lua, regular
expressions, and Git-related formats. Language aliases route assembly to NASM,
Sage to Python, and specialized YAML filetypes to YAML.

Neovim 0.11 uses Tree-sitter's compatibility branch and its `configs.setup`
API. It enables highlighting, indentation, incremental selection, text-object
selection, function/class movement, and parameter swapping.

Neovim 0.12 uses the rewritten `main` branch. It installs parsers with at most
four parallel jobs, starts parsing from a `FileType` autocmd, sets the modern
indent expression, and recreates the same text-object mappings through the new
select/move/swap modules. Both the core and textobjects plugins select matching
branches for the running Neovim version.

## 7. Debugging: `lua/plugins/debugging.lua`

The workbench builds on `nvim-dap`, DAP UI, async UI support, and virtual text.
Adapters include native GDB DAP, Mason's CodeLLDB, debugpy, and optional Delve.

C, C++, Rust, and assembly share launch-with-GDB, launch-with-CodeLLDB, and
attach configurations. Python and Sage launch the current file and select the
active/project/system Python interpreter in that order. Go can launch a file or
package when Delve exists. A project `.vscode/launch.json` is imported and its
adapter names mapped to workbench filetypes.

DAP UI opens before launch/attach and closes on termination/exit. Its left
panel contains scopes, breakpoints, stacks, and watches; REPL/console occupy a
bottom panel. Breakpoint/stopped signs and virtual values are defined.
F5/F10/F11/F12 and the `<leader>d*`/`<leader>b*` mappings implement the common
debug actions.

## 8. User interface: `lua/plugins/ui.lua`

Catppuccin Mocha loads first and integrates explicitly with Tree-sitter, LSP,
Telescope, Neo-tree, Gitsigns, Mason, Which-key, Bufferline, Lspsaga, Noice, and
notifications.

Lualine shows mode, Git branch/diff, diagnostics, full relative filename,
active virtual environment, filetype/encoding, progress, and location.
Bufferline provides diagnostic-aware tabs with a Neo-tree offset. Neo-tree
shows dotfiles and ignored files, follows the active file, and watches the
filesystem. Indent Blankline adds scope guides.

Which-key declares leader-key groups. Noice renders commands/messages and LSP
Markdown. Colorizer displays literal colors in web/data files. TODO Comments
highlights annotations, and Twilight can dim irrelevant code on demand.

## 9. Reverse engineering: `lua/reverse.lua`

This module exposes `:HexToggle`, `:Disassemble`, and `:BinaryStrings`.

Hex mode checks for `xxd`, requires a saved readable file, stores the buffer's
original file options, replaces its text with an `xxd -g 1` view, and installs
a buffer-local `BufWriteCmd`. Saving decodes through `xxd -r`, writes a
same-directory temporary file with the original permission bits, flushes it,
and atomically renames it over the target. Only after a successful conversion
is the buffer marked clean and `BufWritePost` emitted. Leaving hex mode writes
pending edits, removes the custom autocmd, restores options, and reloads bytes.

Disassembly and string extraction validate the target, invoke `objdump` or
`strings` with argument arrays rather than interpolated shell commands, and
place asynchronous output in nonmodifiable scratch buffers. Buffer cleanup
removes stale hex-autocmd bookkeeping. Leader mappings mirror all three
commands.

## 10. Integrated workflows: `lua/workflows.lua`

Shared helpers locate project roots, verify executables, create disposable
scratch buffers, and run commands in terminal splits. Commands are always
passed as argument lists. The module remembers the original PATH and Python
provider after removing any inherited virtual-environment `bin`, allowing a
true later deactivation.

### Underlight integration

`desktop_tool()` calls host commands directly in native Neovim and through
`flatpak-spawn --host` in Flatpak. It backs these commands:

- `:GpuInfo` runs the readiness report into a scratch buffer.
- `:GpuRun` runs a prompted command through discrete-GPU offload in a terminal.
- `:LaptopControl` embeds the Textual laptop controller.
- `:UnderlightDoctor` captures the whole system report.
- `:AI`, `:OpenCode`, and `:Hermes` launch desktop tools detached.
- `:OllamaInfo` captures AI-stack status.
- `:PowerProfile` applies or prompts for an Underlight profile.

### Python environments

Project roots are detected from Python metadata or Git. Names are constrained
to simple local path components. `:VenvCreate` asynchronously runs
`python3 -m venv`; `:VenvActivate` accepts a name/path or discovers project
environments; `:VenvDeactivate` restores the original PATH/provider; and
`:VenvInfo` reports state. Activation updates `VIRTUAL_ENV`, PATH, the Neovim
Python provider, and restarts Pyright.

### Docker and Compose

Docker roots use Compose/Dockerfile/Git markers. Image and container names are
validated so they cannot begin with an option or contain whitespace.
`:DockerBuild`, `:DockerImages`, and `:DockerRun` provide named builds,
formatted listings, and interactive selection. Compose project names use a
strict lowercase pattern; `:ComposeUp`, `:ComposeDown`, and `:ComposeLogs` keep
each project explicit and do not delete volumes.

### CMake presets

`:CMakeConfigurePreset`, `:CMakeBuildPreset`, and `:CTestPreset` locate the
project, accept an explicit preset or parse the tool's preset listing, present
a selector, and run the chosen command in a terminal. The bottom of the module
maps all environment, Docker, Compose, CMake, GPU, AI, laptop, and diagnostic
commands into the corresponding Which-key groups.

## 11. Platform and feature adapters

### `lua/workbench/platform.lua`

`is_flatpak()` checks both `FLATPAK_ID` and `/.flatpak-info`. `open_url()` uses
Neovim's desktop-aware `vim.ui.open` and produces context-specific errors.
`configure_markdown_preview()` defines a Vimscript callback that forwards the
preview URL through this adapter, allowing Flatpak to use the desktop portal.

### `lua/workbench/features.lua`

`regular_file_buffer()` excludes dashboards, terminals, sidebars, unnamed
buffers, and directories. `toggle_markdown_preview()` requires a Markdown file
and an available plugin command, then wraps the call with an actionable error.
`toggle_minimap()` applies the same file guard, loads Neominimap safely, toggles
it, and reports the new state. These wrappers prevent mappings from failing
cryptically when focus is in a plugin window.

## 12. Installation and reproducibility

### `scripts/install.sh`

The companion installer accepts native, Flatpak, or both destinations and link
or copy methods. Native defaults to `${XDG_CONFIG_HOME:-~/.config}/nvim`;
Flatpak uses its application-specific config directory. `install_target()`
returns successfully when the destination already resolves to this checkout,
but refuses to overwrite any unrelated file, directory, or symlink. Parent
directories are created only after that safety check.

Underlight normally performs the equivalent native link itself so the action
can participate in Underlight's unified backup/rollback record.

### Lockfiles

`lazy-lock.json` pins the Neovim 0.11 plugin graph, while
`lazy-lock-0.12.json` pins the 0.12 graph. Most revisions match; the significant
difference is the compatible Tree-sitter and textobjects branches. The files
also pin Lazy itself, allowing bootstrap to become reproducible before the
plugin manager is loaded.

### `.clangd.example`

This project template explains how ROS 2, ESP-IDF, PlatformIO, STM32, and
Arduino projects should expose `compile_commands.json`. Its sample flags remove
known incompatible/noisy vendor options and show optional ROS include paths.

## 13. Tests and CI

### `scripts/smoke-test.sh`

The shell runner creates a guarded temporary tree, exercises copy installation
for both native and Flatpak targets, builds a fake inherited virtual
environment, disables tool downloads, and launches Neovim headlessly with an
error-notification collector. Cleanup removes only a path matching the exact
temporary prefix.

### `tests/smoke.lua`

The Lua release test:

- Requires the supported Neovim version and correct version-specific lockfile.
- Restores any locally drifted plugin checkout before testing.
- Force-loads every plugin and verifies installed/loaded state and exact Git
  revision.
- Confirms the correct Tree-sitter API/branch, aliases, textobjects, and pinned
  Neominimap release.
- Checks all important custom/plugin commands.
- Verifies custom filetypes and that Dadbod state cannot land in the config
  repository.
- Exercises Flatpak detection and the Markdown portal callback.
- Confirms Markdown/minimap file-buffer guards.
- Starts the Markdown Preview server, captures/validates its URL, and fetches
  its HTML when curl is present.
- Activates/deactivates the fake inherited virtual environment and checks PATH
  plus Python-provider restoration.
- Round-trips binary bytes through safe hex mode.
- Opens the minimap and waits for rendered, nonmodifiable content.
- Fails on captured error notifications or startup traceback markers.

On success it prints `RC_SMOKE_OK` with the Neovim version and plugin count.

### `.github/workflows/smoke.yml`

GitHub Actions runs the release test against pinned Neovim 0.11 and 0.12
versions. It grants read-only repository permission, limits the job to 15
minutes, keeps matrix failures independent, installs Neovim, caches Lazy plugin
data using both lockfiles and plugin specs, and invokes the shell runner.

## 14. Complete companion file map

| Path | Responsibility |
|---|---|
| `init.lua` | Version gate, lockfile choice, Lazy bootstrap, module load order. |
| `lua/options.lua` | Core options, filetypes, indentation, split-focus visuals. |
| `lua/keymaps.lua` | Global editing/navigation/plugin-dispatch mappings. |
| `lua/reverse.lua` | Safe hex editing, disassembly, and binary strings. |
| `lua/workflows.lua` | Underlight, venv, Docker, Compose, and CMake commands. |
| `lua/workbench/platform.lua` | Native/Flatpak detection and URL opening. |
| `lua/workbench/features.lua` | Guarded Markdown Preview and minimap toggles. |
| `lua/plugins/completion.lua` | Completion, snippets, pairs, and tags. |
| `lua/plugins/debugging.lua` | DAP adapters, UI, configurations, and mappings. |
| `lua/plugins/lsp.lua` | Mason tools, servers, diagnostics, and LSP UI. |
| `lua/plugins/tools.lua` | Search, format, lint, Git, terminals, DB, docs, navigation. |
| `lua/plugins/treesitter.lua` | Parsers and 0.11/0.12-compatible syntax/textobjects. |
| `lua/plugins/ui.lua` | Theme, status/tab/tree UI, guides, messages, highlights. |
| `scripts/install.sh` | Safe native/Flatpak link-or-copy installer. |
| `scripts/smoke-test.sh` | Isolated headless release-test runner. |
| `tests/smoke.lua` | End-to-end configuration and plugin assertions. |
| `lazy-lock.json` | Reproducible Neovim 0.11 plugin revisions. |
| `lazy-lock-0.12.json` | Reproducible Neovim 0.12 plugin revisions. |
| `.github/workflows/smoke.yml` | Two-version CI matrix. |
| `.clangd.example` | Cross-stack Clangd project template. |
| `.gitignore` | Swap, backup, macOS, log, and DB UI exclusions. |
| `README.md` | Installation, requirements, commands, keys, and workflows. |
| `CHANGELOG.md` | Workbench release history. |
| `LICENSE` | MIT license for the companion repository. |
