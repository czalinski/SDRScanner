# SDRScanner

Multi-channel Software Defined Radio scanner running on an Orange Pi Max V1.1 (RK3588, aarch64).

## Hardware

| Device | Role | Status |
|--------|------|--------|
| RTL-SDR.COM V3 #1 (R820T2) | BNSF Railroad scanner | Connected |
| RTL-SDR.COM V3 #2 (R820T2) | Marine VHF voice | Connected |
| NooElec NESDR SMArTee v5 (bias-tee), serial `RTL_ADSB` | ADS-B (1090 MHz), fed to FlightAware/FR24/ADS-B Exchange — collinear (DC-open, bias-tee safe) | Connected |
| NooElec NESDR SMArt v5, serial `RTLSDR_AIS` | AIS ship tracking — J-pole #2 (DC short: never on a bias-tee dongle) | Connected |
| NooElec NESDR SMArt XTR + Ham It Up | HAM/shortwave HF, receive only (AM/SSB/CW) | Connected — long wire via unun, no counterpoise yet |
| Uniden SDS200 (standalone scanner) | P25 trunking — Pierce County fire/police | Planned purchase |
| HDMI monitor (primary display) | Full-screen ADS-B+AIS live map kiosk | Built — `src/display/adsb_map.py`, systemd auto-start |

Long-term: a second monitor is also planned, showing live audio-output
status across Marine/Railroad/HAM (not built yet — see `TODO.md`).

P25 (fire/police) runs on a standalone Uniden SDS200, not the RTL-SDR/Orange
Pi stack — see `docs/hardware.md` and `docs/antennas.md` §3.

Target host: `zalinskic@192.168.68.70` — second Orange Pi 5 Max, Armbian (noble) on eMMC, repo at `~/SDRScanner` (deployed by rsync, not a git checkout). The first board (`czalinski@`) was retired 2026-11-07 after overheating.

## Project Layout

```
src/            Python source — scanner engine, decoders, web UI
config/         YAML/JSON config for devices, channels, trunking systems
models/         3D-printable designs (OpenSCAD source + exported STL)
scripts/        Installation and startup shell scripts
docs/           Frequency references, antenna designs, hardware notes
tests/          Unit and integration tests
```

## Key Dependencies

- `rtl-sdr` — userspace driver and CLI tools
- `SoapySDR` + `SoapyRTLSDR` — hardware abstraction (multi-device)
- `dump1090` — ADS-B decoder (1090 MHz), source-built (not the `dump1090-fa`
  apt package — no HTTP JSON server, uses `--write-json` instead), feeds
  piaware/fr24feed/adsbx-feed
- `rtl-ais` — AIS NMEA decoder (marine vessel tracking)
- `pygame` — full-screen ADS-B+AIS live map kiosk (`src/display/adsb_map.py`)
- `pyais` — AIS NMEA sentence parsing (`src/display/ais_listener.py`)
- Python packages: see `requirements.txt`

P25 no longer runs on this stack (standalone Uniden SDS200), so `op25` /
GNU Radio are not a dependency here.

## Device Serial Number Assignment

Before running, each dongle must have a unique serial number set via:
```
rtl_eeprom -d <index> -s <serial>
```
Serials and role assignments live in `config/devices.yaml`.

## Running

```bash
# Full scanner stack
./scripts/start_scanner.sh

# Individual services
python3 -m src.scanner.main
```

## Frequency References

- BNSF AAR channels: `config/channels/railroad.yaml`
- Marine VHF: `config/channels/marine.yaml`
- Pierce County P25: standalone Uniden SDS200 (not part of this repo's config)
- ADS-B: `config/channels/adsb.yaml` — fixed 1090 MHz, feeder settings, kiosk display
- AIS: no dedicated channel config — `rtl_ais` decodes both AIS channels
  (161.975/162.025 MHz) in one capture; see `config/devices.yaml` `ais` entry
