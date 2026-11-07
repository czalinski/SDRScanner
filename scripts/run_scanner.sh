#!/usr/bin/env bash
# Launch the main scanner (src/scanner/main.py) — railroad, marine, HF.
# Used by the sdr-scanner systemd --user service; logs go to the journal:
#   journalctl --user -u sdr-scanner -f
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/.venv/bin/activate"

exec python3 -u -m src.scanner.main
