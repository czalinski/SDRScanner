# Antenna Design Reference

## Device → Antenna Assignments

| Device | Target Frequencies | Antenna Type |
|--------|--------------------|--------------|
| RTL-SDR.COM V3 #1 | 160–162 MHz (Railroad) | J-pole **#1** (built, field-tested — see §7) — design §1 |
| RTL-SDR.COM V3 #2 | 156–162 MHz (Marine VHF) | J-pole **#3** (built, field-tested — see §7) — design §2 |
| Uniden SDS200 (standalone, not RTL-SDR) | 763–775 MHz (P25 fire/police) | DPD 769–775 MHz omni collinear |
| NooElec NESDR SMArt v5 | 1090 MHz (ADS-B) | Collinear (built, field-tested — see §7) — design §4 |
| NooElec NESDR SMArTee v5 | 161.975/162.025 MHz (AIS) | J-pole **#2** (built, field-tested — see §7) — design §5 |
| NooElec NESDR SMArt XTR (not yet purchased) | HF (HAM, band TBD) | Bundle includes antennas + balun (§6) |

---

## 1. Railroad VHF Antenna (160–162 MHz)

**Target:** 161 MHz center  
**λ = c/f = 299,792,458 / 161,000,000 = 1.862 m**

### J-pole (chosen — equipment ordered)
A half-wave radiator fed by a shorted quarter-wave matching stub, mounted
side by side. No radials needed (self-contained, unlike the ground-plane
options below), omnidirectional, ~unity to 2 dBi gain (similar to a dipole).

**Built from 300 Ω twin-lead/ladder line**, same as §5 (AIS) — not bare
wire/rod. That means the `468/f` / `234/f` foot formulas (f in MHz) can't
be applied uniformly to both elements, because they behave differently:

- **Matching stub** (both twin-lead conductors run parallel, shorted at
  bottom) is a real two-conductor transmission line — its length depends
  on the *twin-lead's own* velocity factor, nominally **~0.82** for 300 Ω
  window line (verify against your cable's datasheet — commonly
  0.80–0.91+ depending on product).
- **Radiator** (the exposed single conductor above where the stub's
  second conductor is cut) is just a wire in free space — standard
  bare-wire VF (~0.95, already folded into `468/f`) applies, unaffected
  by the twin-lead's VF.

| Element | Basis | At 161 MHz |
|---------|-------|------------|
| A) Matching stub (shorted, twin-lead VF 0.82) | λ/4 × 0.82 | **38.2 cm / 15.0 in** |
| B) Radiator, excluding the section run parallel with the stub | (λ/2 × 0.95, `468/f`) − A | **50.4 cm / 19.8 in** |
| C) Coax tap point (starting estimate) | scaled from A | **~8.2 cm / 3.2 in** from the short |

**Build notes:**
- Short both conductors at the bottom (0 cm reference). One runs the full
  A (38.2 cm) as the stub, open at top. The other runs the same A in
  parallel, then continues alone for B (50.4 cm) to the antenna's true
  top.
- Coax center conductor taps the radiator leg, shield taps the stub leg,
  both at height C above the short.
- C is only a starting point — trim by sliding while checking SWR, don't
  solder at a fixed point and assume it's right first try.

**If this antenna was already built using the earlier (uncorrected) 44.3
cm stub figure**, the stub is roughly 6 cm too long relative to the
VF-corrected 38.2 cm target — worth re-trimming down for a proper match.
Receive-only use tolerates a mismatched stub better than transmit would
(it'll still pull in signal), but it's not tuned to spec as built.

### Alternative: quarter-wave ground plane (simpler, if J-pole build stalls)
- Radiator: λ/4 = **46.5 cm**
- 4× radials: λ/4 = 46.5 cm each, angled down 45°
- Connector: SMA male to coax, then SMA female chassis mount
- Feed impedance: ~35 Ω; add a 1:1.5 transformer or accept slight mismatch

### Notes
- Railroad VHF is horizontal polarization in some areas but mostly vertical.
- Mount as high as practical; avoid nearby metal structures.

---

## 2. Marine VHF Antenna (156–162 MHz)

**Target:** 156–162 MHz (VHF Marine band)  
Band is narrow enough that a 159 MHz center antenna covers everything.

**λ at 159 MHz = 1.886 m**

### J-pole (chosen — equipment ordered)
Same design as §1, tuned to 159 MHz — also built from 300 Ω twin-lead, so
the same stub-vs-radiator VF split applies (see §1 for why):

| Element | Basis | At 159 MHz |
|---------|-------|------------|
| A) Matching stub (shorted, twin-lead VF 0.82) | λ/4 × 0.82 | **38.6 cm / 15.2 in** |
| B) Radiator, excluding the section run parallel with the stub | (λ/2 × 0.95, `468/f`) − A | **51.1 cm / 20.1 in** |
| C) Coax tap point (starting estimate) | scaled from A | **~8.2 cm / 3.2 in** from the short |

Same build notes as §1 — trim for lowest SWR rather than trusting the
formula dimensions exactly.

**If this antenna was already built using the earlier (uncorrected) 44.9
cm stub figure**, it's similarly oversized by ~6 cm relative to the
38.6 cm VF-corrected target — same re-trim recommendation as §1.

### Alternative: 5/8λ vertical (if J-pole build stalls)
- Radiator: 5λ/8 = **117.9 cm**
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

## 5. AIS Antenna (161.975/162.025 MHz — NooElec SMArTee v5)

**Target:** AIS channels 87B/88B, 161.975/162.025 MHz — center 162.0 MHz.

**Chosen: a dedicated third J-pole**, same design as §1/§2, rather than a
splitter off the marine antenna — avoids the few dB of splitter loss, at
the cost of building one more antenna.

**Built from 300 Ω twin-lead/ladder line** (unlike a bare-wire J-pole,
where a single velocity factor applies to the whole element). Two
different velocity factors apply here, because the two sections behave
differently:

- **Matching stub** — the shorted section where both conductors of the
  twin-lead run parallel — is electrically a real two-conductor
  transmission line. Its resonant length depends on the *twin-lead's own*
  velocity factor, not free-space or bare-wire VF. Nominal VF for 300 Ω
  window line is **~0.82** (verify against your specific cable's
  datasheet — window line commonly ranges 0.80–0.91+ depending on
  dielectric/spacing; true open-wire ladder line can run higher).
- **Radiator** — the exposed single-conductor section above where the
  stub's second conductor is cut — is just a wire in free space, not a
  transmission line. It uses the standard bare-wire VF (~0.95, the same
  factor already folded into the `468/f` formula), unaffected by the
  twin-lead's VF.

**λ at 162 MHz = 1.851 m**

| Element | Basis | At 162 MHz |
|---------|-------|------------|
| A) Matching stub (shorted, twin-lead VF 0.82) | λ/4 × 0.82 | **37.9 cm / 14.9 in** |
| B) Radiator, excluding the section run parallel with the stub | (λ/2 × 0.95, `468/f`) − A | **50.2 cm / 19.8 in** |
| C) Coax tap point (starting estimate) | scaled from A | **~8.2 cm / 3.2 in** from the short |

Build: short both conductors at the bottom (0 cm reference). One
conductor runs the full A (37.9 cm) as the stub, left open at top. The
other runs the same A in parallel, then continues alone for B (50.2 cm)
to the antenna's true top. Coax center conductor taps the radiator leg,
shield taps the stub leg, both at height C above the short. C is only a
starting point — trim by sliding while checking SWR, same as the other
J-poles.

**If §1/§2 (railroad, marine) were also built from 300 Ω twin-lead rather
than bare wire/rod**, the same stub-VF correction applies there and their
listed stub/radiator dimensions should be recalculated the same way —
the `468/f` / `234/f` formulas in those sections assume bare wire
throughout and will give an oversized stub if twin-lead was actually
used.

---

## 6. HAM Antenna (HF — band TBD)

**Hardware decided** (see `docs/hardware.md`): NooElec SMArt XTR HF Bundle
— comes with 3 antennas + a balun, so this section may not need a custom
build at all once the bundle arrives.

**Target band(s):** still TBD. Antenna choice depends on which HAM bands
matter most (e.g. 40m, 20m, 17m) — HF wire antennas (dipole, longwire,
magnetic loop) generally cover a narrow range well; multi-band coverage
typically needs either a trap dipole, an antenna tuner, or accepting a
compromise antenna. Fill in once bands of interest are chosen and the
bundle's included antennas are evaluated against them.

---

## 7. Field Test Results (2026-11-06)

All four homemade antennas compared against a baseline: the ~50 cm
dipole that came with a handheld radio. Purpose was a sanity check on
construction quality (no SWR meter / VNA available), not a calibrated
gain measurement.

### Method
- Two RTL-SDR.COM V3 dongles on one powered USB hub: baseline dipole on
  `RTLSDR_RR`, antenna under test on `RTLSDR_MRN`. Both antennas
  vertical, side by side, same location indoors.
- **Channel match check:** with two identical commercial antennas on both
  dongles, the receive chains read within ~1 dB of each other (median
  per-bin difference 0.9 dB) — differences below are the antennas, not
  the dongles.
- **VHF (J-poles):** simultaneous `rtl_power` sweeps, 155.5–163 MHz,
  12.5 kHz bins, gain 40, 60 s. Compared the median level (mostly noise)
  and individual signals: NOAA 162.550/162.475 (constant carriers, used
  only as a steady reference), AIS bursts at 161.975/162.025, Ch 16.
- **1090 MHz (collinear):** two `dump1090` instances in parallel, gain
  49.6, 2 min, counting aircraft / positions / messages.
- Script and raw CSVs: `~/antenna_tests/` on the Pi (`cmp.sh <label>
  [seconds]`, selects dongles by serial).
- Values are relative dB (uncalibrated), useful only side by side.

### Environment notes
- Strong local broadband noise indoors. The dipole's background sits
  ~34 dB above the dongle's own floor (unconnected input ≈ −39), and there
  is a strong local spur at **157.500 MHz** — likely from the Pi, USB hub
  or household electronics. Swapping to a new powered hub dropped the
  dipole's background ~4 dB, so the old hub contributed some of this.
- **Polarization matters:** with both antennas horizontal, J-pole #1
  read −5.5 dB vs the dipole on everything; vertical, its real signals
  matched or beat the dipole. Horizontal tests mostly compared local
  noise pickup. Test and mount vertical.

### VHF results (J-poles, vertical, vs dipole)

"Above background" = how far a signal stands above that antenna's own
median level — the figure that matters for hearing weak stations.

| | Dipole | J-pole #1 | J-pole #2 | J-pole #3 |
|---|---|---|---|---|
| Background vs dipole | — | −5 dB | −12 dB | −2.5 dB |
| 157.5 MHz local spur vs dipole | — | −7 dB | −20 dB | −6 dB |
| NOAA 162.550 above background | ~+10 | +14 | +15 | **+24** |
| NOAA 162.475 above background | ~+2–9 | +13 | +15 | +14 |
| AIS strongest burst above background | ~+11 | ~+14 | **~+27** | ~+20 |
| Real signals, absolute vs dipole | — | −1 to +5 dB | −7 to +4 dB | **+2 to +14 dB** |
| Ch 16 | no traffic | no traffic | no traffic | caught one (+11 dB vs dipole) |

- **J-pole #3:** best on real signals, ~+10 dB over the dipole, flat across
  the marine band. Only antenna that caught Ch 16 traffic.
- **J-pole #2:** lowest noise pickup by far and cleanest AIS bursts.
  Background is 2–4 dB lower mid-band than at the edges and the 162 MHz
  signals did best — consistent with resonance slightly high, toward
  162 MHz. Suits AIS.
- **J-pole #1:** usable, weakest of the three. Fine for strong signals.
- None of the three needs a rebuild. Since the three designs differ by
  only 1–2 cm (§1/§2/§5), the spread is mostly build variation, not
  design frequency.

### 1090 MHz result (collinear vs dipole, 2 min)

| | Dipole | Collinear |
|---|---|---|
| Aircraft seen | 12 | **27** |
| With position | 6 | **22** |
| Messages | 3,873 | **15,056** (~4×) |
| Mean signal | −23.8 dBFS | **−16.8 dBFS** |
| Peak signal | −16.2 dBFS | **−5.0 dBFS** |

The dipole is badly off-resonance at 1090 MHz so this is a weak baseline,
but the collinear clearly works — phasing sections are close enough.

(At 156–163 MHz the collinear reads ~19 dB below the dipole with very low
noise pickup — expected, it's 1/7 of its design frequency. Not a defect.)

### Assignment

| Antenna | Job | Reason |
|---|---|---|
| J-pole #3 | Marine VHF voice | Best sensitivity; distant boats are the weakest target |
| J-pole #2 | AIS | Appears tuned toward 162 MHz; lowest noise; cleanest bursts |
| J-pole #1 | Railroad | Weakest, but nearby BNSF traffic is typically strong |
| Collinear | ADS-B | Works at 1090 MHz, ~2× aircraft / ~4× messages vs dipole |

---

## Coax & Connectors

| Run length | Recommended coax |
|------------|------------------|
| < 1 m | RG-316 or RG-174 (pigtail to dongle) |
| 1–5 m | RG-58 or LMR-195 |
| 5–15 m | LMR-400 |
| > 15 m | Consider a low-noise preamp at the antenna |

RTL-SDR.COM V3 dongles (railroad, marine) and the NooElec v5/XTR dongles
(ADS-B, AIS, HAM) use SMA female connectors.
Pigtail: **SMA male → F-type** or directly to RG-316 with SMA male crimp.

The SDS200 (P25) is BNC female — see §3 for its N-to-BNC feedline, separate
from the RTL-SDR/Orange Pi stack.
