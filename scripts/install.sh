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

# ── ADS-B feeders (piaware, fr24feed, adsbx-feed) ─────────────────────────────
# All three read dump1090-fa's Beast output (port 30005) — lightweight
# forwarding daemons, no extra decode cost. Each needs a one-time interactive
# claim/config step after install (see log output from each installer):
#   piaware:  sudo piaware-config -force -latitude <lat> -longitude <lon>
#             then claim at flightaware.com/adsb/piaware/claim
#   fr24feed: sudo dpkg-reconfigure fr24feed   (enter your sharing key)
#   adsbx-feed: no account needed, just needs receiver lat/lon in its config
if ! command -v piaware &>/dev/null; then
    log "Installing piaware (FlightAware feeder)..."
    sudo apt-get install -y --no-install-recommends piaware 2>/dev/null || \
        log "piaware not in apt for this arch — install manually from flightaware.com/adsb/piaware/install"
fi

if ! command -v fr24feed &>/dev/null; then
    log "Installing fr24feed (FlightRadar24 feeder)..."
    sudo apt-get install -y --no-install-recommends fr24feed 2>/dev/null || \
        log "fr24feed not in apt for this arch — install manually from flightradar24.com/share-your-data"
fi

if ! command -v adsbx-feed &>/dev/null; then
    log "Installing ADS-B Exchange feeder (Docker-based)..."
    if command -v docker &>/dev/null; then
        log "Docker present — ADS-B Exchange feed container can be started post-install; see adsbexchange.com/how-to-feed"
    else
        log "Docker not installed — ADS-B Exchange feeder needs it. Install docker separately if you want this feed."
    fi
fi

# ── Kiosk display (7" Pi display — local dump1090-fa SkyAware map) ───────────
# Requires a desktop/X session on the display; only relevant if a GUI is
# configured on this Orange Pi. Uncomment once the display + X session are set up:
# sudo apt-get install -y --no-install-recommends chromium unclutter
# Autostart: chromium --kiosk --noerrdialogs --disable-infobars http://localhost:8080

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

# NOTE: P25 (fire/police) runs on a standalone Uniden SDS200, not this stack.
# No OP25/GNU Radio dependency here — see docs/hardware.md.

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
