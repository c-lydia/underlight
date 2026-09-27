# Underlight local RAG

Underlight RAG indexes selected files into a local LanceDB database, retrieves
the most relevant chunks for a question, and asks a local Ollama model to
answer with that context. The index, downloaded models, config, and chat logs
stay outside the dotfiles repository.

## Install

After the normal Ubuntu `./install.sh`:

```bash
underlight-rag setup
```

On EndeavourOS, the complete bootstrap is:

```bash
./install-endeavouros.sh --with-rag
```

Both routes create an isolated environment below
`~/.local/share/underlight/venvs/rag_pipeline` and an editable config at
`~/.config/underlight/rag.yaml`. OCR and sentence-transformers are deliberately
separate because their packages are large:

```bash
underlight-rag setup --with-ocr
underlight-rag setup --with-sentence-transformers
```

Tesseract OCR also needs the distribution's `tesseract` package. EasyOCR can
run on CPU or CUDA according to the `ocr` section of the config.

## First run

Edit the roots and exclusions before indexing:

```bash
underlight-rag config
underlight-rag status
underlight-rag index --table projects --dry-run
underlight-rag index --table projects
underlight-rag ask "where is the ROS 2 launch configuration?"
```

The default embedder is Ollama's `nomic-embed-text`. Pull it once before the
first real index. `--dry-run` only lists files and does not call the embedder:

```bash
ollama pull nomic-embed-text
```

Dry runs show the first 50 matching paths and a total. Add `--verbose` only
when you need the complete list. On a large `~/projects`, narrow `include` or
expand `exclude` before starting the real index.

The default Ollama answer model is `qwen3:4b`. If it is not installed:

```bash
ollama pull qwen3:4b
```

## Commands

```text
underlight-rag setup [OPTIONS]          install or refresh the environment
underlight-rag status                   inspect setup, Ollama, and index tables
underlight-rag menu                     open the Wofi interface
underlight-rag config                   edit rag.yaml
underlight-rag index --table SOURCE     index projects, downloads, home, or all
underlight-rag ask QUESTION             retrieve context, then ask Ollama
underlight-rag direct PROMPT             ask Ollama without local retrieval
underlight-rag chat list                 list remembered chat projects
underlight-rag chat rebuild              re-embed chat logs after model changes
underlight-rag chat query QUERY          search remembered conversations
underlight-rag chat log --role user --text TEXT
underlight-rag server                    serve the local HTTP API on port 8080
underlight-rag mcp                       serve read-only tools over MCP stdio
underlight-rag opencode [ARGUMENTS]      run OpenCode with the RAG environment
```

Useful query options:

```bash
underlight-rag ask "find the UART driver" --tables projects
underlight-rag ask "what did we decide?" --remember --project robot
underlight-rag ask "why does this board fail?" --verbose
```

Indexing is incremental and deterministic. Existing chunk IDs are updated and
chunks from deleted or excluded files are removed after a successful pass. Use
`--rebuild` after changing embedding models or when upgrading an old table:

```bash
underlight-rag index --table projects --rebuild
```

## Desktop and Neovim

Choose **Local RAG** in `underlight-ai menu`, or run `underlight-rag menu`
directly. In Neovim:

- `:RagAsk [question]` opens the answer in a terminal split.
- `:RagIndex [projects|downloads|home|all]` updates an index.
- `:RagIndex! projects` rebuilds an incompatible index.
- `:RagStatus` shows the local stack state.
- `Space a r` prompts for a RAG question when Space is the leader key.

## Configuration

The source sections (`projects`, `downloads`, and `home`) each support:

```yaml
projects:
  root: $HOME/projects
  include: ["*"]
  exclude: [".git", "node_modules", "build", ".venv"]
  extensions: [".py", ".cpp", ".md", ".yaml"]
```

Symlinks and files larger than 100 MiB are skipped. PDFs are indexed one page
at a time. Code is split near function/class boundaries, text by paragraph,
and KiCad files by top-level s-expression blocks.

The default embedder uses Ollama and keeps PyTorch out of the base environment:

```yaml
embedder:
  model: nomic-embed-text
  device: ollama
  ollama_base_url: http://localhost:11434
  batch_size: 64
```

To use sentence-transformers on CPU instead:

```yaml
embedder:
  model: sentence-transformers/all-MiniLM-L6-v2
  device: cpu
  batch_size: 64
```

First run `underlight-rag setup --with-sentence-transformers`. Whenever the
embedding model changes, run `underlight-rag index --table all --rebuild` and
`underlight-rag chat rebuild`. Vector sizes are checked so incompatible
vectors cannot be silently mixed.

## Chat memory

`--remember` retrieves relevant messages and appends the new exchange to both a
JSONL log and the `idx_chat` vector table. Manual examples:

```bash
underlight-rag chat log --project robot --role user --text "Use Cyclone DDS"
underlight-rag chat query "which DDS did we choose?" --project robot
underlight-rag chat list
```

The logs live in `~/.local/state/underlight/rag-chatlogs` by default.

## HTTP API

Start the loopback-only server:

```bash
underlight-rag server
curl http://127.0.0.1:8080/health
curl -sS -X POST http://127.0.0.1:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"where is the motor node?","remember":true}'
```

`POST /log` accepts `project`, `role`, and `text`. The server has no
authentication; keep the default `127.0.0.1` binding unless the surrounding
network is trusted and protected.

## OpenCode Zen and Hermes

The same index can be used from OpenCode or Hermes through the bundled
read-only MCP server. It publishes three tools:

- `search_local_knowledge` returns matching local excerpts.
- `ask_local_assistant` retrieves and generates with local Ollama, returning
  the answer and source metadata.
- `local_rag_status` reports models and indexed tables.

Underlight's installer does not overwrite either application's configuration.
Add this entry to `~/.config/opencode/opencode.json` (merge it with the existing
JSON object):

```json
"mcp": {
  "underlight_rag": {
    "type": "local",
    "command": ["/home/YOU/.local/bin/underlight-rag", "mcp"],
    "enabled": true,
    "timeout": 30000
  }
}
```

Add the equivalent top-level entry to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  underlight_rag:
    command: /home/YOU/.local/bin/underlight-rag
    args: [mcp]
    enabled: true
    connect_timeout: 30
    tools:
      include:
        - search_local_knowledge
        - ask_local_assistant
        - local_rag_status
```

After `underlight-rag setup`, verify both connections:

```bash
opencode mcp list
hermes mcp test underlight_rag
```

For OpenCode Zen, start OpenCode, enter `/connect`, choose **OpenCode Zen**,
and paste the API key created by its sign-in flow. Enter `/models` and choose a
model marked Free, or launch the current Underlight default directly:

```bash
underlight-ai zen ~/projects/example
opencode models opencode --refresh --verbose
```

Override that launcher's default with a second argument or
`UNDERLIGHT_ZEN_MODEL`, for example:

```bash
underlight-ai zen ~/projects/example opencode/nemotron-3.5-lightning-free
```

Hermes continues to use the provider and model already selected in
`~/.hermes/config.yaml`; the RAG server only adds local knowledge tools.

Cloud privacy boundary: `search_local_knowledge` sends its returned excerpts
to the calling client, so a Zen or other cloud model can receive that content.
Use `ask_local_assistant` to keep raw retrieval and generation local (the
resulting answer and source paths are still visible to the cloud client), or
use `underlight-rag ask` for a completely local session.

## Storage and privacy

- Vector store: `~/.local/share/underlight/rag-store`
- Python environment: `~/.local/share/underlight/venvs/rag_pipeline`
- Config: `~/.config/underlight/rag.yaml`
- Chat logs: `~/.local/state/underlight/rag-chatlogs`

Retrieval and generation remain local when both the embedder and Ollama URL are
local. Only paths permitted by `rag.yaml` are scanned.
