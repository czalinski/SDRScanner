# Antenna Design Reference

## Device → Antenna Assignments

| Device | Target Frequencies | Antenna Type |
|--------|--------------------|--------------|
| RTL-SDR.COM V3 #1 | 160–162 MHz (Railroad) | 5/8λ vertical or dipole |
| RTL-SDR.COM V3 #2 | 156–162 MHz (Marine VHF) | 5/8λ vertical |
| Uniden SDS200 (standalone, not RTL-SDR) | 763–775 MHz (P25 fire/police) | DPD 769–775 MHz omni collinear |
| NooElec NESDR SMArt v5 | 1090 MHz (ADS-B) | Collinear or spider |
| NooElec NESDR SMArTee v5 | HF (HAM, band TBD) | TBD — pending hardware decision (§5) |

---

## 1. Railroad VHF Antenna (160–162 MHz)

**Target:** 161 MHz center  
**λ = c/f = 299,792,458 / 161,000,000 = 1.862 m**

### Quarter-wave ground plane (simplest)
- Radiator: λ/4 = **46.5 cm**
- 4× radials: λ/4 = 46.5 cm each, angled down 45°
- Connector: SMA male to coax, then SMA female chassis mount
- Feed impedance: ~35 Ω; add a 1:1.5 transformer or accept slight mismatch

### 5/8λ vertical (better gain, ~3 dBi)
- Radiator: 5λ/8 = **116.4 cm**
- Matching coil at base (shorten with ~10 cm coil, ~6 turns, adjust for 50 Ω)
- 4× λ/4 radials

### Notes
- Railroad VHF is horizontal polarization in some areas but mostly vertical.
- Mount as high as practical; avoid nearby metal structures.

---

## 2. Marine VHF Antenna (156–162 MHz)

**Target:** 156–162 MHz (VHF Marine band)  
Band is narrow enough that a 159 MHz center antenna covers everything.

**λ at 159 MHz = 1.886 m**

### 5/8λ marine vertical
- Same construction as railroad antenna above but tuned to 159 MHz
- Radiator: 117.9 cm
- Mount outdoors with clear horizon view

---

## 3. P25 Antenna — Pierce County (Uniden SDS200, standalone)

**Confirmed (radioreference.com):** "A P25 Phase 2 TDMA 700 MHz Motorola trunked
radio system with 21 sites, 38 channels and 74 talk paths."

**Target:** 763–775 MHz (public safety base/repeater-tx block — what a
scanner receives). Center 769 MHz. Confirmed against real documented 700 MHz
P25 control/voice channels, which cluster at 769–774 MHz (e.g. WSDOT P25:
769.69/770.17/770.71/774.33 MHz).

**21 sites = multi-site trunking.** The system can hand a call to any site
depending on load and location — omnidirectional only, no yagi.

**P25 reception moved off the RTL-SDR/Orange Pi stack entirely.** A
standalone **Uniden SDS200** handles fire/police directly — its True I/Q SDR
receiver handles this multi-site/simulcast environment better than a DIY
software decode chain would, at comparable cost to the RF chain (LNA +
multicoupler) the RTL-SDR route would have needed. This section now only
covers the antenna and feedline; there's no splitting, LNA, or multicoupler
to spec since the SDS200 is a single receiver with its own adequate
front-end sensitivity (adding an external preamp ahead of an already-tuned
commercial scanner more often causes overload than improvement).

### Antenna — DPD Productions 700 MHz UHF Vertical Outdoor Base Antenna

**Chosen.** Verified specs, exact match to the corrected 763–775 MHz target:

| Spec | Value |
|------|-------|
| Passband | 769–775 MHz |
| Gain | 6 dBi, omnidirectional |
| Polarization | Vertical |
| VSWR | 1.5:1 or less on center |
| Connector | N female, 24" RG8X pigtail |
| Dimensions | 57" tall × 1.25" wide, 2 lb |
| Mount | Standard 1¼" mast, no ground plane needed |
| Price | $189.95 |

**Mount:** outdoor, on the house siding just outside the window (can go
higher on the same wall if clearance allows — more height is better).

### Lightning protection — required for an outdoor house-mounted antenna
Not needed for the earlier attic-mount plan, but mandatory now that the
antenna lives on the exterior of the house:
- **Coax lightning/surge arrestor** at the point the cable enters the
  building, rated for the connector type and frequency in use.
- **Grounding block** at that same entry point, bonded to the house's
  electrical grounding system (NEC Article 810 requirement for outdoor
  antenna installations, not optional best practice).
- **Ground the mast itself.**
- Any coax run with outdoor exposure needs a UV-resistant outdoor-rated
  jacket; indoor sections can be standard.

### Signal chain

```
DPD antenna (N-female) → coax → lightning arrestor + ground block
  (at wall entry) → coax → N-to-BNC adapter/cable → Uniden SDS200
```

**Connector note:** the SDS200's antenna input is **BNC female** (confirmed
from Uniden's own documentation), not SMA. The DPD antenna's pigtail is
N-female. The feedline needs to terminate **N-male on the antenna end,
BNC-male on the SDS200 end** — a single N-to-BNC adapter or a purpose-made
cable, no multi-way split needed since the SDS200 is one receiver.

### Cable
Loss estimates at 769 MHz (extrapolated from published 440 MHz figures via
√f scaling — confirm exact datasheet numbers before ordering):

| Cable | ~769 MHz loss (est.) | Use for |
|-------|----------------------|---------|
| RG-58 | ~14 dB/100 ft | Short runs only, < 15 ft |
| RG-8X | ~11 dB/100 ft | Short-to-moderate runs |
| LMR-240 | ~7 dB/100 ft | Moderate runs |
| LMR-400 | ~3.6 dB/100 ft | Runs past ~30–40 ft |

Actual run length (mount point to where the SDS200 sits indoors) determines
which is worth it — under ~15 ft, even RG-8X costs under 2 dB.

---

## 4. ADS-B Antenna (1090 MHz — NooElec NESDR SMArt v5)

**λ at 1090 MHz = 27.5 cm**

### Spider / ground plane (λ/4)
- Radiator: λ/4 = **6.88 cm**  (straight wire or brass rod)
- 4–8× radials: 6.88 cm each, bent 45° down
- Impedance: ~35 Ω; close enough to 50 Ω for low-cost builds

### Coax collinear (better range)
- Stack of λ/2 sections phased with λ/2 coax stubs
- 5–7 dBi gain; significant improvement for aircraft range

### Notes
- ADS-B is right-hand circular polarization (RHCP) from the aircraft, vertical from the ground.
- Vertical polarization antennas work fine — marginal loss vs. RHCP.
- Mount in the clear, ideally on the roof. Every meter of height = more range.
- Use low-loss coax (LMR-400 or similar) for cable runs longer than ~3 m at 1090 MHz.

---

## 5. HAM Antenna (HF — band TBD)

**Hardware decided** (see `docs/hardware.md`): NooElec SMArTee v5 + Ham It
Up Plus v2 upconverter, powered via the SMArTee's bias tee.

**Target band(s):** still TBD. Antenna choice depends on which HAM bands
matter most (e.g. 40m, 20m, 17m) — HF wire antennas (dipole, longwire,
magnetic loop) generally cover a narrow range well; multi-band coverage
typically needs either a trap dipole, an antenna tuner, or accepting a
compromise antenna. Fill in once bands of interest are chosen.

---

## Coax & Connectors

| Run length | Recommended coax |
|------------|------------------|
| < 1 m | RG-316 or RG-174 (pigtail to dongle) |
| 1–5 m | RG-58 or LMR-195 |
| 5–15 m | LMR-400 |
| > 15 m | Consider a low-noise preamp at the antenna |

RTL-SDR.COM V3 dongles (railroad, marine) and the NooElec v5 dongles
(ADS-B, HAM) use SMA female connectors.
Pigtail: **SMA male → F-type** or directly to RG-316 with SMA male crimp.

The SDS200 (P25) is BNC female — see §3 for its N-to-BNC feedline, separate
from the RTL-SDR/Orange Pi stack.
