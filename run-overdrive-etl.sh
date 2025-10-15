#!/bin/bash
set -euo pipefail

# Resolve the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# ensure that the out/logs directory exists
mkdir -p "$SCRIPT_DIR/out/logs"

/usr/bin/podman compose pull >/dev/null 2>&1 || true
/usr/bin/podman compose up --abort-on-container-exit >> "$SCRIPT_DIR/out/logs/overdrive_etl.log" 2>&1
/usr/bin/podman compose down
