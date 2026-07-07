# Antenna Design Reference

## Device → Antenna Assignments

| Device | Target Frequencies | Antenna Type |
|--------|--------------------|--------------|
| RTL-SDR.COM V3 #1 | 160–162 MHz (Railroad) | 5/8λ vertical or dipole |
| RTL-SDR.COM V3 #2 | 156–162 MHz (Marine VHF + AIS) | 5/8λ vertical |
| NooElec v5 #1 | P25 trunking (varies by system) | Discone / broadband |
| NooElec v5 #2 | 1090 MHz (ADS-B) | Collinear or spider |

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

## 2. Marine VHF + AIS Antenna (156–162 MHz)

**Target:** 156–162 MHz (VHF Marine band + AIS channels 87B/88B)  
Band is narrow enough that a 159 MHz center antenna covers everything.

**λ at 159 MHz = 1.886 m**

### 5/8λ marine vertical
- Same construction as railroad antenna above but tuned to 159 MHz
- Radiator: 117.9 cm
- Mount outdoors with clear horizon view (AIS line-of-sight, typically 20–40 nmi)

### AIS note
- AIS (161.975 + 162.025 MHz) decoded by `rtl-ais` capturing 2 MHz of bandwidth centered ~162 MHz.
- A single wideband antenna covers both AIS channels and the marine VHF voice band.

---

## 3. P25 Broadband Antenna (NooElec v5 #1)

**Target:** Pierce County P25 system (exact frequencies TBD from radioreference.com)  
P25 Phase 1 in the Pacific Northwest commonly uses 700/800 MHz or VHF bands.

### Discone antenna
- Covers 25 MHz–1.3 GHz — best choice until P25 frequencies are confirmed
- Commercially available or can be built from brass rods and plate
- 50 Ω feed impedance across the range

### After confirming P25 frequencies
- Cut a resonant collinear or yagi for the specific band (VHF, UHF, 700, 800 MHz)

---

## 4. ADS-B Antenna (NooElec v5 #2, 1090 MHz)

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

## Coax & Connectors

| Run length | Recommended coax |
|------------|------------------|
| < 1 m | RG-316 or RG-174 (pigtail to dongle) |
| 1–5 m | RG-58 or LMR-195 |
| 5–15 m | LMR-400 |
| > 15 m | Consider a low-noise preamp at the antenna |

All RTL-SDR.COM V3 and NooElec v5 dongles use SMA female connectors.  
Pigtail: **SMA male → F-type** or directly to RG-316 with SMA male crimp.
