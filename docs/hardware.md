# Hardware Reference

## Orange Pi Max V1.1

| Spec | Value |
|------|-------|
| SoC | Rockchip RK3588 |
| CPU | 4× Cortex-A76 + 4× Cortex-A55, up to 2.4 GHz |
| RAM | 8 GB LPDDR4X |
| Storage | 64 GB eMMC |
| OS | Linux 6.1.99-vendor-rk35xx (aarch64) |
| USB | USB 3.0 ×2, USB 2.0 ×2 |
| Network | 2.5 GbE |
| IP | 192.168.68.230 |

## SDR Dongles

### RTL-SDR.COM V3 (R820T2) ×2

| Spec | Value |
|------|-------|
| Tuner | Rafael Micro R820T2 |
| Frequency range | 500 kHz – 1.75 GHz |
| ADC | RTL2832U, 8-bit |
| Max sample rate | 3.2 MS/s (stable: 2.56 MS/s) |
| Connector | SMA female |
| Bias-T | Yes (4.5V, software controlled via `rtl_biast`) |
| TCXO | Yes (0.5 ppm) |
| Noise figure | ~3.5 dB typical |
| Notes | Direct-sampling mode enables HF (< 24 MHz) via Q-branch |

**Assigned roles:**
- #1 (`RTLSDR_RR`): BNSF Railroad scanner, 160–162 MHz
- #2 (`RTLSDR_MRN`): Marine VHF voice + AIS, 156–162 MHz

### NooElec RTL-SDR v5 ×2 *(pending purchase)*

| Spec | Value |
|------|-------|
| Tuner | Rafael Micro R828D |
| Frequency range | 500 kHz – 1.75 GHz |
| ADC | RTL2832U, 8-bit |
| TCXO | Yes (0.5 ppm) |
| ESD protection | Yes (improved vs. V3) |
| Connector | SMA female |
| Noise figure | ~3 dB typical (slightly better than V3) |

**Assigned roles:**
- #1 (`NOOELEC_P25`): P25 trunking — Pierce County / Tacoma public safety
- #2 (`NOOELEC_ADSB`): ADS-B 1090 MHz aircraft tracking

## USB Topology

```
OrangePi USB 3.0 port
└── USB Hub (Bus 001 / 002)
    ├── RTL-SDR.COM V3 #1  (RTLSDR_RR)
    ├── RTL-SDR.COM V3 #2  (RTLSDR_MRN)
    ├── [slot] NooElec v5 #1  (NOOELEC_P25)    — pending
    └── [slot] NooElec v5 #2  (NOOELEC_ADSB)   — pending
```

**Important:** Use a powered USB hub when running all 4 dongles. Each RTL-SDR draws ~300 mA.

## Initial Setup Steps

1. **Flash firmware / update**: `sudo apt-get update && sudo apt-get upgrade`
2. **Blacklist DVB-T modules**: done by `install.sh`
3. **Assign serial numbers**: `./scripts/set_serials.sh <role>` (one dongle at a time)
4. **Calibrate PPM**: use `kalibrate-rtl` against a known signal or GSM tower
5. **Run install**: `./scripts/install.sh`
6. **Test dongles**: `rtl_test -d RTLSDR_RR -t && rtl_test -d RTLSDR_MRN -t`
