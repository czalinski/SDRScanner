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
    pkill -f "dump1090"         2>/dev/null || true
    pkill -f "rtl_ais"          2>/dev/null || true
}
trap stop_all EXIT INT TERM

echo "=== SDRScanner starting ==="

# ADS-B (only if NOOELEC_ADSB dongle is present)
if rtl_test -d NOOELEC_ADSB -t &>/dev/null; then
    echo "[adsb] Starting dump1090..."
    dump1090 \
        --device NOOELEC_ADSB \
        --gain 49.6 \
        --net \
        --net-sbs-port 30003 \
        --net-ro-port 30002 \
        --net-beast-port 30005 \
        --write-json /tmp/adsb-json \
        >> "$LOG_DIR/adsb.log" 2>&1 &
else
    echo "[adsb] NOOELEC_ADSB dongle not found — skipping"
fi

# AIS marine (RTL-SDR.COM V3 marine dongle)
if rtl_test -d RTLSDR_MRN -t &>/dev/null; then
    echo "[ais] Starting rtl_ais..."
    rtl_ais \
        -d RTLSDR_MRN \
        -n \
        -u 127.0.0.1 \
        -P 10110 \
        >> "$LOG_DIR/ais.log" 2>&1 &
else
    echo "[ais] RTLSDR_MRN dongle not found — skipping"
fi

# Main Python scanner (railroad VHF + marine voice + P25 when available)
echo "[scanner] Starting main scanner..."
python3 -m src.scanner.main >> "$LOG_DIR/scanner.log" 2>&1 &

echo "All services launched. Logs in $LOG_DIR/"
echo "Press Ctrl+C to stop."
wait
