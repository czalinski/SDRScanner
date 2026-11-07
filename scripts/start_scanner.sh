#!/usr/bin/env bash
# Start all SDRScanner services
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
elif rtl_test -d RTL_ADSB -t &>/dev/null; then
    echo "[adsb] dump1090-adsb.service not running — starting..."
    sudo systemctl start dump1090-adsb
else
    echo "[adsb] RTL_ADSB dongle not found — skipping"
fi

if systemctl is-active --quiet rtl-ais; then
    echo "[ais] rtl-ais.service already running"
elif rtl_test -d RTLSDR_AIS -t &>/dev/null; then
    echo "[ais] rtl-ais.service not running — starting..."
    sudo systemctl start rtl-ais
else
    echo "[ais] RTLSDR_AIS dongle not found — skipping"
fi

if systemctl is-active --quiet ais-listener; then
    echo "[ais] ais-listener.service already running"
else
    echo "[ais] ais-listener.service not running — starting..."
    sudo systemctl start ais-listener 2>/dev/null || echo "[ais] could not start ais-listener"
fi

# Main Python scanner (railroad VHF + marine voice + HAM) — sdr-scanner is a
# systemd --user service (starts at boot); logs: journalctl --user -u sdr-scanner -f
if systemctl --user is-active --quiet sdr-scanner; then
    echo "[scanner] sdr-scanner.service already running"
else
    echo "[scanner] sdr-scanner.service not running — starting..."
    systemctl --user start sdr-scanner
fi
systemctl --user --no-pager --lines=5 status sdr-scanner || true
