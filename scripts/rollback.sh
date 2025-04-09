#!/usr/bin/env bash
# Roll a service back to the previous good release, or to a specific tag:
#   scripts/rollback.sh [service-dir]            # previous good release
#   scripts/rollback.sh [service-dir] <tag>      # explicit tag from history

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

SERVICE_DIR="${1:-.}"
TAG="${2:-}"

load_env "$SERVICE_DIR/.env"
require_cmd aws kubectl

CONFIG="$SERVICE_DIR/shipline.yaml"
shipline_cmd -c "$CONFIG" releases -n 10

if [[ -n "$TAG" ]]; then
  log "rolling back to $TAG"
  shipline_cmd -c "$CONFIG" rollback --to "$TAG"
else
  log "rolling back to previous good release"
  shipline_cmd -c "$CONFIG" rollback
fi
