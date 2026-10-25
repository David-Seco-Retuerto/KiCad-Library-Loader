#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
workspace=${1:-$base}
if [ -x "$base/.venv/bin/python" ]; then
    exec "$base/.venv/bin/python" "$base/scripts/import_gui.py" --workspace "$workspace"
fi
exec python3 "$base/scripts/import_gui.py" --workspace "$workspace"
