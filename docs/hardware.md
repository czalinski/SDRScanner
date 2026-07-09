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
- #2 (`RTLSDR_MRN`): Marine VHF voice, 156–162 MHz (AIS moved to a
  dedicated dongle — see below; RTL-SDR dongles are exclusive-access and
  can't run rtl_ais and the NFM voice scanner on the same one)

### P25 Trunking — moved off this stack

Fire/police (Pierce County P25 Phase 2 TDMA, 21-site trunked) is now handled
by a standalone **Uniden SDS200** scanner, not RTL-SDR/trunk-recorder. Its
True I/Q SDR receiver handles the multi-site/simulcast environment better
than a DIY software decode chain, and its cost was comparable to the RF
chain (LNA + multicoupler) this project would otherwise have needed. It
uses the same DPD 769–775 MHz omni antenna spec'd for this project
(see `docs/antennas.md` §3), fed directly — no splitter or preamp needed
since it's a single receiver.

Of the two NooElec RTL-SDR v5 dongles originally planned for P25, one is
reused below as a dedicated AIS receiver; the other is a spare.

### NooElec RTL-SDR v5 — dedicated AIS

| Spec | Value |
|------|-------|
| Tuner | Rafael Micro R828D |
| Frequency range | 500 kHz – 1.75 GHz |
| Connector | SMA female |
| Noise figure | ~3 dB typical |

**Assigned role:** `RTLSDR_AIS` — AIS vessel tracking, split off the marine
antenna via a 2-way splitter (156–162 MHz is the same band as marine voice,
so no separate antenna build is needed).

## USB Topology

```
OrangePi USB 3.0 port
└── USB Hub (Bus 001 / 002)
    ├── RTL-SDR.COM V3 #1  (RTLSDR_RR)
    ├── RTL-SDR.COM V3 #2  (RTLSDR_MRN)
    ├── NooElec v5         (RTLSDR_AIS)
    └── [slot] RTL-SDR (cheap) (RTLSDR_ADSB) — pending purchase
```

**Important:** Use a powered USB hub — 4 dongles running concurrently draws
more than most Pi USB ports can supply on their own. Each RTL-SDR draws
~300 mA.

## Initial Setup Steps

1. **Flash firmware / update**: `sudo apt-get update && sudo apt-get upgrade`
2. **Blacklist DVB-T modules**: done by `install.sh`
3. **Assign serial numbers**: `./scripts/set_serials.sh <role>` (one dongle at a time)
4. **Calibrate PPM**: use `kalibrate-rtl` against a known signal or GSM tower
5. **Run install**: `./scripts/install.sh`
6. **Test dongles**: `rtl_test -d RTLSDR_RR -t && rtl_test -d RTLSDR_MRN -t`
