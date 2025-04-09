#!/usr/bin/env bash
# Shared helpers for ShipLine shell entry points.

set -euo pipefail

log()  { printf '\033[1;34m[shipline]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[shipline]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[shipline]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
  local missing=()
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if ((${#missing[@]})); then
    die "missing required tools: ${missing[*]}"
  fi
}

load_env() {
  # Load KEY=VALUE pairs from .env if present (never committed).
  local env_file="${1:-.env}"
  if [[ -f "$env_file" ]]; then
    log "loading $env_file"
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

shipline_cmd() {
  if command -v shipline >/dev/null 2>&1; then
    shipline "$@"
  else
    python3 -m shipline "$@"
  fi
}
