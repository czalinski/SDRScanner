#!/usr/bin/env bash
# Launch dump1090 for the ADS-B device using config/channels/adsb.yaml settings.
# Single source of truth for the launch args — used by both start_scanner.sh
# (manual start) and the dump1090-adsb systemd service (auto-start on boot).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
source "$REPO_DIR/.venv/bin/activate"

read -r FREQ_HZ GAIN LAT LON JSON_DIR JSON_EVERY <<< "$(python3 -c "
from src.scanner.config_loader import load_channel_config
c = load_channel_config('adsb')
d, m = c['dump1090'], c['mlat']
print(d['freq_mhz'] * 1e6, d['gain'], m['receiver_lat'], m['receiver_lon'], d['write_json_dir'], d['write_json_every'])
")"

mkdir -p "$REPO_DIR/$JSON_DIR"

exec dump1090 --device-type soapy --device driver=rtlsdr,serial=RTLSDR_ADSB \
    --freq "$FREQ_HZ" --gain "$GAIN" \
    --lat "$LAT" --lon "$LON" \
    --write-json "$REPO_DIR/$JSON_DIR" --write-json-every "$JSON_EVERY" \
    --net --net-bind-address 127.0.0.1 --quiet
