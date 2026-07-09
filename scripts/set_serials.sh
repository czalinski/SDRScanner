#!/usr/bin/env bash
# Assign unique serial numbers to RTL-SDR dongles.
# Run with ONE dongle plugged in at a time, then swap.
#
# Usage:
#   ./set_serials.sh railroad    — programs serial RTLSDR_RR
#   ./set_serials.sh marine      — programs serial RTLSDR_MRN
#   ./set_serials.sh ais         — programs serial RTLSDR_AIS
#   ./set_serials.sh adsb        — programs serial RTLSDR_ADSB
#
# P25 (fire/police) runs on a standalone Uniden SDS200, not an RTL-SDR
# dongle — no serial to assign here. See docs/hardware.md.

set -euo pipefail

ROLE="${1:-}"

case "$ROLE" in
  railroad) SERIAL="RTLSDR_RR"   ;;
  marine)   SERIAL="RTLSDR_MRN"  ;;
  ais)      SERIAL="RTLSDR_AIS"  ;;
  adsb)     SERIAL="RTLSDR_ADSB" ;;
  *)
    echo "Usage: $0 {railroad|marine|ais|adsb}"
    echo ""
    echo "Plug in ONLY the dongle you want to label, then run this script."
    exit 1
    ;;
esac

echo "Detected dongles:"
rtl_eeprom 2>&1 | grep -E "Serial|Found" || true
echo ""

read -rp "This will write serial '$SERIAL' to the dongle at index 0. Continue? [y/N] " ans
[[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

rtl_eeprom -d 0 -s "$SERIAL"
echo ""
echo "Done. Unplug and replug the dongle, then verify with: rtl_test -d $SERIAL"
