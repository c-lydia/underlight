#!/usr/bin/env bash
set -euo pipefail

if (($#)); then
  exec underlight-rag index "$@"
else
  exec underlight-rag index --table projects --dry-run
fi
