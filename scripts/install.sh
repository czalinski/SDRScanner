#!/usr/bin/env bash
# SDRScanner full system installation — Orange Pi Max (aarch64 / Debian/Ubuntu)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO_DIR/scripts/install.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== SDRScanner Installation ==="
log "Host: $(uname -n)  Arch: $(uname -m)"

# ── System packages ────────────────────────────────────────────────────────────
log "Updating package lists..."
sudo apt-get update -qq

log "Installing base dependencies..."
sudo apt-get install -y --no-install-recommends \
    build-essential cmake pkg-config git \
    libusb-1.0-0-dev \
    libncurses-dev \
    rtl-sdr librtlsdr-dev \
    sox \
    multimon-ng \
    python3 python3-pip python3-venv python3-dev \
    libpython3-dev \
    ffmpeg \
    screen \
    curl wget

# ── Blacklist DVB-T kernel modules (they grab the dongle before rtl-sdr can) ──
BLACKLIST=/etc/modprobe.d/rtlsdr-blacklist.conf
if [[ ! -f "$BLACKLIST" ]]; then
    log "Blacklisting DVB-T kernel modules..."
    sudo tee "$BLACKLIST" > /dev/null <<'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist dvb_usb_v2
blacklist dvb_core
EOF
    sudo modprobe -r dvb_usb_rtl28xxu rtl2832 rtl2830 2>/dev/null || true
    log "NOTE: A reboot may be required for the blacklist to take full effect."
fi

# ── SoapySDR + SoapyRTLSDR ────────────────────────────────────────────────────
log "Installing SoapySDR..."
sudo apt-get install -y --no-install-recommends \
    libsoapysdr-dev soapysdr-tools python3-soapysdr \
    soapysdr-module-rtlsdr 2>/dev/null || {
    log "SoapySDR not in apt — building from source..."
    build_soapy_from_source
}

# ── dump1090 (ADS-B) ──────────────────────────────────────────────────────────
if ! command -v dump1090 &>/dev/null && ! command -v readsb &>/dev/null; then
    log "Installing dump1090-fa..."
    sudo apt-get install -y --no-install-recommends dump1090-fa 2>/dev/null || {
        log "Building dump1090 from source..."
        TMP=$(mktemp -d)
        git clone --depth=1 https://github.com/flightaware/dump1090.git "$TMP/dump1090"
        make -C "$TMP/dump1090" -j"$(nproc)"
        sudo install -m755 "$TMP/dump1090/dump1090" /usr/local/bin/
        sudo install -m755 "$TMP/dump1090/view1090" /usr/local/bin/ 2>/dev/null || true
        rm -rf "$TMP"
        log "dump1090 installed from source."
    }
fi

# ── rtl-ais (AIS marine vessel decoder) ───────────────────────────────────────
if ! command -v rtl_ais &>/dev/null; then
    log "Building rtl-ais from source..."
    TMP=$(mktemp -d)
    git clone --depth=1 https://github.com/dgiardini/rtl-ais.git "$TMP/rtl-ais"
    make -C "$TMP/rtl-ais" -j"$(nproc)"
    sudo install -m755 "$TMP/rtl-ais/rtl_ais" /usr/local/bin/
    rm -rf "$TMP"
    log "rtl-ais installed."
fi

# ── OP25 (P25 decoder) — skip until NooElec v5 devices arrive ─────────────────
# log "Building OP25 (GNU Radio P25 decoder)..."
# This requires GNU Radio which is a large install; uncomment when NooElec arrives.
# sudo apt-get install -y gnuradio gnuradio-dev gr-osmosdr
# TMP=$(mktemp -d)
# git clone --depth=1 https://github.com/boatbod/op25.git "$TMP/op25"
# cd "$TMP/op25" && mkdir build && cd build && cmake .. && make -j"$(nproc)" && sudo make install
# rm -rf "$TMP"

# ── Python virtual environment ─────────────────────────────────────────────────
log "Setting up Python virtual environment..."
# --system-site-packages gives the venv access to system-installed python3-soapysdr
python3 -m venv --system-site-packages "$REPO_DIR/.venv"
source "$REPO_DIR/.venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$REPO_DIR/requirements.txt" -q

log ""
log "=== Installation complete ==="
log "Next steps:"
log "  1. Reboot (or run: sudo modprobe -r dvb_usb_rtl28xxu)"
log "  2. Verify dongles: rtl_test -t"
log "  3. Set serial numbers: ./scripts/set_serials.sh"
log "  4. Start scanner: ./scripts/start_scanner.sh"
