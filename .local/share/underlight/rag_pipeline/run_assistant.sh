#!/usr/bin/env bash
set -euo pipefail
case ${1:-} in
  answer) shift; exec underlight-rag ask "$@" ;;
  ask) shift; exec underlight-rag direct "$@" ;;
  *) printf '%s\n' 'Usage: run_assistant.sh answer|ask TEXT' >&2; exit 2 ;;
esac
