#!/usr/bin/env bash
# Start all SDRScanner services
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/.venv/bin/activate"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

source "$VENV"

stop_all() {
    echo "Stopping all scanner processes..."
    pkill -f "src.scanner.main" 2>/dev/null || true
    sudo systemctl stop piaware fr24feed 2>/dev/null || true
    docker stop adsbx-feed 2>/dev/null || true
}
trap stop_all EXIT INT TERM

echo "=== SDRScanner starting ==="

# ADS-B + AIS: dump1090, rtl_ais, the AIS listener, and the full-screen map
# display are permanent systemd services now (dump1090-adsb / rtl-ais /
# ais-listener system-wide, adsb-map per-user — see systemd/ and TODO.md),
# not launched or stopped by this script. This just reports status and
# starts anything that's somehow not running.
# Feeders (piaware, fr24feed, ADS-B Exchange) need one-time account setup
# before they'll do anything useful — see TODO.md. Not started here until
# configured.
if systemctl is-active --quiet dump1090-adsb; then
    echo "[adsb] dump1090-adsb.service already running"
elif rtl_test -d RTLSDR_ADSB -t &>/dev/null; then
    echo "[adsb] dump1090-adsb.service not running — starting..."
    sudo systemctl start dump1090-adsb
else
    echo "[adsb] RTLSDR_ADSB dongle not found — skipping"
fi

if systemctl is-active --quiet rtl-ais; then
    echo "[ais] rtl-ais.service already running"
elif rtl_test -d RTL_AIS -t &>/dev/null; then
    echo "[ais] rtl-ais.service not running — starting..."
    sudo systemctl start rtl-ais
else
    echo "[ais] RTL_AIS dongle not found — skipping"
fi

if systemctl is-active --quiet ais-listener; then
    echo "[ais] ais-listener.service already running"
else
    echo "[ais] ais-listener.service not running — starting..."
    sudo systemctl start ais-listener 2>/dev/null || echo "[ais] could not start ais-listener"
fi

# Main Python scanner (railroad VHF + marine voice + HAM)
echo "[scanner] Starting main scanner..."
python3 -m src.scanner.main >> "$LOG_DIR/scanner.log" 2>&1 &

echo "All services launched. Logs in $LOG_DIR/"
echo "Press Ctrl+C to stop."
wait
