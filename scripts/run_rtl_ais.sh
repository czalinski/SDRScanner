#!/usr/bin/env bash
# Launch rtl_ais for the dedicated AIS device (RTL_AIS), forwarding
# decoded NMEA over UDP to src/display/ais_listener.py.
# Used by the rtl-ais systemd service (auto-start on boot).
set -euo pipefail

exec rtl_ais -d RTL_AIS -n -h 127.0.0.1 -P 10110
