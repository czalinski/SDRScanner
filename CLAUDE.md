# SDRScanner

Multi-channel Software Defined Radio scanner running on an Orange Pi Max V1.1 (RK3588, aarch64).

## Hardware

| Device | Role | Status |
|--------|------|--------|
| RTL-SDR.COM V3 #1 (R820T2) | BNSF Railroad scanner | Connected |
| RTL-SDR.COM V3 #2 (R820T2) | Marine VHF voice | Connected |
| RTL-SDR (cheap, ~$25) | ADS-B (1090 MHz), fed to FlightAware/FR24/ADS-B Exchange | Pending purchase |
| Uniden SDS200 (standalone scanner) | P25 trunking — Pierce County fire/police | Planned purchase |
| 7" Pi display | Local kiosk map (dump1090-fa SkyAware) | Purchased |

P25 (fire/police) runs on a standalone Uniden SDS200, not the RTL-SDR/Orange
Pi stack — see `docs/hardware.md` and `docs/antennas.md` §3.

Target host: `czalinski@192.168.68.230`

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
- `dump1090-fa` — ADS-B decoder (1090 MHz), feeds piaware/fr24feed/adsbx-feed
- `rtl-ais` — AIS marine vessel decoder
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
