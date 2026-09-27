# Underlight dotfiles roadmap

This file tracks useful additions that should remain portable, reversible, and
safe to keep in Git. Generated data, credentials, model files, and machine-only
state do not belong in this repository.

## Priority 1: reliability and recovery

### Unified doctor command

Extend `underlight-doctor` into one clear health report for:

- symlinks and required packages;
- user services and desktop/session dependencies;
- SSH and persistent terminal sessions;
- GPU, power profiles, and Ollama;
- OpenCode, Hermes, and Underlight RAG integrations;
- distro-specific requirements on Ubuntu and EndeavourOS.

The command should be read-only by default, explain each failure, and offer
explicit repair commands instead of silently changing the machine.

### Snapshot and restore

Add commands that can export and restore the small, important parts of the
environment before a reinstall or migration:

- Neovim and terminal session metadata;
- SSH configuration, excluding private keys unless separately encrypted;
- Underlight, RAG, OpenCode, and Hermes configuration;
- package manifests and enabled user services.

The backup must exclude vector indexes, downloaded models, caches, build
outputs, chat databases, API tokens, and other regenerable or sensitive data.

## Priority 2: portable machine setup

### Per-machine profiles

Introduce small declarative profiles for laptop, workstation, and optional
host overrides. Keep distro selection separate from hardware selection, for
example:

```text
profiles/
  distro/ubuntu.yaml
  distro/endeavouros.yaml
  hardware/laptop.yaml
  hardware/workstation.yaml
  hosts/example.yaml
```

Profiles should select packages, services, GPU behavior, displays, networking,
and performance defaults without copying whole config files.

### Reproducible package manifests

Track explicit packages for each supported distro and distinguish required,
desktop, development, ROS 2, and optional AI packages. Add a command that
reports installed, missing, and obsolete explicit packages without removing
anything automatically.

### Clean-machine verification

Run syntax and smoke tests in CI or disposable containers for both install
paths. Verify scripts, generated configuration, shell startup, Neovim startup,
and installer idempotency. Hardware-dependent tests should report a skip rather
than fail on machines without that hardware.

## Priority 3: secrets and privacy

### Secrets-safe bootstrap

Use an encrypted secrets workflow such as `sops` with `age`, or references to
an existing password manager. Git may contain encrypted values, public age
recipients, and templates, but never plaintext API keys, SSH private keys,
recovery codes, or tokens.

The bootstrap should work when no secrets bundle is present and explain which
optional integrations remain unavailable.

### AI privacy modes

Add an obvious session-level mode shared by Underlight RAG, OpenCode, and
Hermes:

- `local`: retrieval and generation stay in local Ollama;
- `local-answer`: local retrieval and Ollama generation, with only the answer
  and source metadata returned to a cloud client;
- `cloud-context`: matching local excerpts may be sent to the selected cloud
  provider.

Default to `local` or require a clear opt-in before exposing raw local excerpts.
Show the active mode in status output and the AI launcher.

## Priority 4: shell and project workflow

### Project-aware environments

Add optional `direnv` templates for ROS 2 and general development projects.
They should source the requested ROS distribution and workspace only after the
user approves the directory, and should not mutate the global shell startup.

### Navigation and history

Integrate `fzf` and `zoxide` with conservative defaults. Improve shell history
for concurrent terminals using timestamps, duplicate suppression, and safe
incremental sharing. Never store commands matching configured secret patterns.

### Persistent workspace presets

Provide tmux or zellij presets for common ROS 2 layouts so one command can open
build, launch, topic/log, and editor panes. The session should survive SSH
disconnects and remain usable from plain terminals without Neovim.

## Maintenance rules

- Every feature must have Ubuntu and EndeavourOS behavior documented.
- Installers must preserve existing user files and remain safe to run twice.
- Destructive or network-exposing actions require an explicit command.
- Host-specific paths and credentials stay outside tracked files.
- New commands need `--help`, README usage, and a smoke test.
- Prefer small inspectable scripts over opaque background automation.

## Suggested implementation order

1. Finish and test the OpenCode/Hermes RAG bridge and privacy modes.
2. Expand `underlight-doctor` and add configuration-only snapshot/restore.
3. Introduce distro, hardware, and host profiles.
4. Add package manifests and clean-machine CI tests.
5. Add encrypted-secret bootstrap.
6. Add project-aware ROS 2 environments and persistent workspace presets.
7. Add optional navigation and history enhancements.
