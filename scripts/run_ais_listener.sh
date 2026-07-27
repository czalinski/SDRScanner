#!/usr/bin/env bash
# Launch the AIS NMEA listener/decoder (writes run/adsb-json/ships.json).
# Used by the ais-listener systemd service (auto-start on boot).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/.venv/bin/activate"

exec python3 -m src.display.ais_listener
