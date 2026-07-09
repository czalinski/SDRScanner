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
    pkill -f "rtl_ais"          2>/dev/null || true
    sudo systemctl stop dump1090-fa piaware fr24feed 2>/dev/null || true
    docker stop adsbx-feed 2>/dev/null || true
}
trap stop_all EXIT INT TERM

echo "=== SDRScanner starting ==="

# ADS-B: dump1090-fa + feeders (piaware, fr24feed, ADS-B Exchange) run as
# system services / a Docker container, not hand-launched with CLI flags —
# that's how these packages are designed to be used, and it's how the device
# serial / receiver lat-lon / feed keys actually get configured (one-time
# setup in /etc/default/dump1090-fa, piaware-config, fr24feed's dpkg-reconfigure,
# and the adsbx-feed docker run — see TODO.md). This script just starts them.
if rtl_test -d RTLSDR_ADSB -t &>/dev/null; then
    echo "[adsb] Starting dump1090-fa + feeders..."
    sudo systemctl start dump1090-fa
    sudo systemctl start piaware  2>/dev/null || echo "[adsb] piaware not configured yet — skipping"
    sudo systemctl start fr24feed 2>/dev/null || echo "[adsb] fr24feed not configured yet — skipping"
    docker start adsbx-feed 2>/dev/null || echo "[adsb] adsbx-feed container not set up yet — skipping"
else
    echo "[adsb] RTLSDR_ADSB dongle not found — skipping"
fi

# AIS (dedicated NooElec v5 — split off the marine antenna). Separate dongle
# from marine voice: RTL-SDR devices are exclusive-access, so rtl_ais and
# the Python NFM marine scanner can't share RTLSDR_MRN.
if rtl_test -d RTLSDR_AIS -t &>/dev/null; then
    echo "[ais] Starting rtl_ais..."
    rtl_ais \
        -d RTLSDR_AIS \
        -n \
        -u 127.0.0.1 \
        -P 10110 \
        >> "$LOG_DIR/ais.log" 2>&1 &
else
    echo "[ais] RTLSDR_AIS dongle not found — skipping"
fi

# Main Python scanner (railroad VHF + marine voice)
echo "[scanner] Starting main scanner..."
python3 -m src.scanner.main >> "$LOG_DIR/scanner.log" 2>&1 &

echo "All services launched. Logs in $LOG_DIR/"
echo "Press Ctrl+C to stop."
wait
