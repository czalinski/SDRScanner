#!/usr/bin/env bash
# Launch the "hey radio" voice-command listener (src/voice/voice_service.py).
# Used by the voice-commands systemd --user service.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/.venv/bin/activate"

exec python3 -u -m src.voice.voice_service
