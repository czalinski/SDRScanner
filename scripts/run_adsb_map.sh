#!/usr/bin/env bash
# Launch the full-screen ADS-B map display app.
# Used by the adsb-map systemd --user service (auto-start on graphical login).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/.venv/bin/activate"

exec python3 -m src.display.adsb_map
