#!/usr/bin/env bash
# Prepare a workstation or CI runner: create a venv, install ShipLine + dev tools,
# and verify the external CLIs the pipeline shells out to.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd python3

VENV="${VENV:-$ROOT/.venv}"
if [[ ! -d "$VENV" ]]; then
  log "creating virtualenv at $VENV"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e "$ROOT[dev]"
log "installed shipline $(python -c 'import shipline; print(shipline.__version__)')"

for tool in git docker aws kubectl; do
  if command -v "$tool" >/dev/null 2>&1; then
    log "found $tool"
  else
    warn "$tool not found - required for build/publish/deploy stages"
  fi
done

log "activate with: source $VENV/bin/activate"
