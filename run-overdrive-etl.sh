#!/bin/bash

# NOTE: to keep the systemd instance and runtime directory alive when
#       logged out, you need to enable linger with the below command
#       for your username ...
# sudo loginctl enable-linger USER_NAME_HERE

set -euo pipefail

export PATH=/usr/local/bin:/usr/bin:/bin
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"

# Resolve the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

# ensure that the out/logs directory exists
mkdir -p "$SCRIPT_DIR/out/logs"

/usr/bin/podman compose pull >/dev/null 2>&1 || true
/usr/bin/podman compose up --abort-on-container-exit >> "$SCRIPT_DIR/out/logs/overdrive_etl.log" 2>&1
/usr/bin/podman compose down
