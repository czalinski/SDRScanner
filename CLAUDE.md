# SDRScanner

Multi-channel Software Defined Radio scanner running on an Orange Pi Max V1.1 (RK3588, aarch64).

## Hardware

| Device | Role | Status |
|--------|------|--------|
| RTL-SDR.COM V3 #1 (R820T2) | BNSF Railroad scanner | Connected |
| RTL-SDR.COM V3 #2 (R820T2) | Marine VHF voice | Connected |
| NooElec RTL-SDR v5 #1 | P25 trunking (public safety) | Pending purchase |
| NooElec RTL-SDR v5 #2 | ADS-B (1090 MHz) or AIS | Pending purchase |

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
- `dump1090` — ADS-B decoder (1090 MHz)
- `rtl-ais` — AIS marine vessel decoder
- `op25` — GNU Radio P25 decoder (built from source)
- Python packages: see `requirements.txt`

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
- Pierce County P25: `config/channels/p25.yaml` + `config/trunking/`
- ADS-B: 1090 MHz (no config needed — fixed frequency)
