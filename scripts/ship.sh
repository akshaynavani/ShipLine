#!/usr/bin/env bash
# Run the full pipeline for a service directory:
#   scripts/ship.sh [service-dir] [extra shipline flags...]
# Example: scripts/ship.sh examples/hello-service --dry-run

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

SERVICE_DIR="${1:-.}"
shift || true

GLOBAL_FLAGS=()
CMD_FLAGS=()
for arg in "$@"; do
  case "$arg" in
    --dry-run|-v|--verbose) GLOBAL_FLAGS+=("$arg") ;;
    *) CMD_FLAGS+=("$arg") ;;
  esac
done

load_env "$SERVICE_DIR/.env"
require_cmd git docker aws kubectl

[[ -f "$SERVICE_DIR/shipline.yaml" ]] || die "no shipline.yaml in $SERVICE_DIR"

log "shipping $(basename "$(cd "$SERVICE_DIR" && pwd)")"
start=$(date +%s)
shipline_cmd -c "$SERVICE_DIR/shipline.yaml" "${GLOBAL_FLAGS[@]+"${GLOBAL_FLAGS[@]}"}" \
  ship "${CMD_FLAGS[@]+"${CMD_FLAGS[@]}"}"
log "done in $(( $(date +%s) - start ))s"
