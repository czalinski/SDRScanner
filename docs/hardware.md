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
| IP | 192.168.68.98 |

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
- #2 (`RTLSDR_MRN`): Marine VHF voice, 156–162 MHz

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
reused below for ADS-B; the other (a SMArTee v5, bias-tee enabled) is now
reused for AIS — see below. HAM gets its own dedicated dongle instead (a
NooElec SMArt XTR HF Bundle), since AIS needs the SMArTee.

### NooElec RTL-SDR v5 (SMArTee variant) — AIS

| Spec | Value |
|------|-------|
| Tuner | Rafael Micro R820T2 |
| Frequency range | 500 kHz – 1.75 GHz |
| Connector | SMA female |
| Bias-T | Yes — not needed for AIS, just a side effect of reusing this dongle |

**Assigned role:** `RTL_AIS` — AIS vessel tracking,
Commencement Bay. Needs its own dedicated dongle: `rtl_ais` requires
exclusive device access, and AIS's frequencies (161.975/162.025 MHz) fall
outside the marine voice dongle's 155.8–157.8 MHz window. Antenna: a
dedicated third J-pole (see `docs/antennas.md` §5) rather than a splitter
off the marine antenna — avoids splitter loss, not yet built. Decoded via
`rtl_ais` + `src/display/ais_listener.py` (uses the `pyais` library),
rendered as dark blue markers on the same live map as ADS-B aircraft
(bright red) — see `src/display/adsb_map.py`.

### NooElec NESDR SMArt XTR HF Bundle — HAM/HF

Connected 2026-11-06. Includes: SMArt XTR RTL-SDR (Elonics E4000 tuner,
~52 MHz and up — HF only via the upconverter), Ham It Up Plus v2
upconverter, 3 antennas, balun, adapters — a purpose-built kit rather than
assembling pieces separately (the original plan of adding just an
upconverter to the existing SMArTee v5 no longer works now that the
SMArTee is needed for AIS).

**Assigned role:** `RTLSDR_HAM` (burned 2026-11-06; takes effect after a
physical replug) — HAM/shortwave HF, receive only. Demodulated by
`src/scanner/linear_demod.py` (AM/USB/LSB/CW); channels in
`config/channels/ham.yaml`, dial frequencies + `upconverter_offset_mhz: 125`.

Signal chain: long wire → unun → Ham It Up (RF IN) → Ham It Up (IF OUT) →
XTR. Ham It Up mode button: the four white LEDs are UP+Amp / UP / Amp / PT
(pass-through); use **UP** (upconvert, no amp). In PT or Amp the HF signal
isn't shifted and the XTR (E4000, ~52 MHz and up) hears nothing. **Note:** librtlsdr treats a
numeric `-d` argument as a device index, so `rtl_power -d 00000001` opened
device #1 (ADS-B), not the XTR — use `-d RTLSDR_HAM` once replugged.

## USB Topology

```
OrangePi USB port
└── Externally-powered USB hub
    ├── RTL-SDR.COM V3 #1  (RTLSDR_RR)
    ├── RTL-SDR.COM V3 #2  (RTLSDR_MRN)
    ├── NooElec SMArt v5   (RTLSDR_ADSB)
    ├── NooElec SMArTee v5 (RTL_AIS)
    └── NooElec SMArt XTR  (RTLSDR_HAM) ← Ham It Up ← long wire
```

**Important:** Must use an externally-powered hub — several dongles running
concurrently draws more than a bus-powered hub can supply from a single Pi
USB port (~300 mA per RTL-SDR). Confirmed by direct testing: a bus-powered
4-port hub caused constant USB disconnect/reconnect churn with only 3
dongles attached; switching to an externally-powered hub resolved it.

## Initial Setup Steps

1. **Flash firmware / update**: `sudo apt-get update && sudo apt-get upgrade`
2. **Blacklist DVB-T modules**: done by `install.sh`
3. **Assign serial numbers**: `./scripts/set_serials.sh <role>` (one dongle at a time)
4. **Calibrate PPM**: use `kalibrate-rtl` against a known signal or GSM tower
5. **Run install**: `./scripts/install.sh`
6. **Test dongles**: `rtl_test -d RTLSDR_RR -t && rtl_test -d RTLSDR_MRN -t`
