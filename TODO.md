# SDRScanner — TODO

Current scope: railroad + marine + HAM audio scanning with playback
(Orange Pi), ADS-B with a full-screen live map (built and kiosk-wired this
session), and AIS ship tracking on the same map. P25 (fire/police) runs on
a standalone Uniden SDS200 — its antenna/RF chain is tracked separately,
not part of this list.

Long-term: two-monitor setup — one showing the ADS-B+AIS live map (built,
see below), one showing current audio-output status across
Marine/Railroad/HAM (not built yet — see "Declared but not built" below).

## Resolved this session

- [x] Found the Pi at its new IP (`192.168.68.98`, was `.230`).
- [x] **Diagnosed and fixed a USB hub power issue** (bus-powered hub caused
      disconnect/reconnect churn under load) — externally-powered hub
      resolved it.
- [x] **Built the ADS-B live map** (`src/display/adsb_map.py`) — full-screen
      pygame kiosk over cached real OpenStreetMap tiles, wired into systemd
      (`dump1090-adsb.service` + `adsb-map.service`) and verified via an
      actual reboot. Tuned to your exact address (Stadium District, Tacoma)
      and a ~20mi visual-range zoom instead of the whole region.
      Self-heals GNOME's fullscreen/focus-loss quirk; dark-red/black
      colors for contrast against the light basemap.
- [x] **AIS reinstated** (previously dropped, brought back this session):
      `src/display/ais_listener.py` decodes `rtl_ais`'s NMEA UDP stream via
      `pyais`'s `AISTracker` (handles multi-part message reassembly
      automatically) and writes `ships.json` the same way dump1090 writes
      `aircraft.json`. `adsb_map.py` now renders both — aircraft bright
      red, ships dark blue. Verified the decode logic against sample AIVDM
      sentences (position + multi-part static/voyage data); **not yet
      tested against real RF**, since the AIS dongle isn't wired up yet
      (see Hardware below).
- [x] **HAM hardware plan changed**: buying the NooElec SMArt XTR HF Bundle
      (XTR + Ham It Up Plus v2 + antennas + balun) instead of just an
      upconverter, since the SMArTee v5 originally earmarked for HAM is now
      needed for AIS instead. XTR bundle not yet purchased.

## Hardware

- [x] AIS serial burned: `RTL_AIS` (shortened from `RTLSDR_AIS` — didn't fit
      this dongle's EEPROM string space). Replugged and confirmed.
- [x] **AIS antenna decided**: a dedicated third J-pole (161.975/162.025 MHz,
      see `docs/antennas.md` §5), not a splitter off the marine antenna —
      avoids splitter loss. Not yet built.
- [ ] Build the three J-poles — railroad (161 MHz), marine (159 MHz), AIS
      (162 MHz). Equipment already ordered for railroad/marine; AIS J-pole
      dimensions are in `docs/antennas.md` §5 (very close to the other two,
      consider building as a batch). This is the only remaining blocker for
      live ship tracking — the software side is done.
- [x] **HAM**: XTR + Ham It Up connected; `RTLSDR_HAM` burned 2026-11-06.
- [x] HF chain working (2026-11-06): Ham It Up was wired backwards; now
      antenna → RF IN, IF OUT → XTR, mode LED "UP" (upconvert, no amp).
      WWV 10/15 MHz and 22m/31m broadcasters received; WWV 15 decoded.
      (The XTR also needed a physical replug — a software USB reset left it
      streaming garbage.)
- [ ] Compare Ham It Up "UP" vs "UP+Amp" with a sweep — keep the amp only
      if signals rise more than the noise floor does.
- [ ] Counterpoise/ground for the long-wire unun.
- [ ] Build/mount ADS-B antenna (spec: `docs/antennas.md` §4)
- [ ] Spec + build HAM antenna once band(s) of interest are chosen
      (`docs/antennas.md` §6 — may not be needed at all if the XTR bundle's
      included antennas cover it)
- [ ] Second monitor for the audio-status dashboard — physical mount/connect
      once that dashboard exists (see "Declared but not built")
- [ ] PPM calibration for all dongles via `kalibrate-rtl`
      (`docs/hardware.md` setup step 4) — not yet confirmed done

## Software — ADS-B / AIS

- [x] Live map built and kiosk-wired (see "Resolved this session").
- [ ] One-time feeder account setup (piaware/fr24feed/adsbx-feed need
      accounts before they do anything — see `start_scanner.sh` comments):
      - piaware: `sudo piaware-config -force -latitude <lat> -longitude <lon>`,
        then claim at flightaware.com/adsb/piaware/claim
      - fr24feed: `sudo dpkg-reconfigure fr24feed`, enter your sharing key
      - ADS-B Exchange: one-time `docker run` per adsbexchange.com/how-to-feed
        to create the `adsbx-feed` container (script only `docker start`s an
        existing one)
- [ ] `receiver_alt_m` in `config/channels/adsb.yaml` is still a placeholder
      (50m) — update with actual antenna height MSL once mounted; lat/lon
      are already exact.
- [ ] Test AIS against real RF once the dongle/antenna are wired up —
      software side (decoder, tracker, map rendering) is built and unit
      tested against sample data, but unverified against actual Commencement
      Bay traffic.

## Software — railroad/marine/HAM audio + playback

- [ ] Fresh end-to-end test of railroad + marine running concurrently with
      the playback queue now that project scope has changed (the pieces —
      FFT scan, NFM demod, recorder, playback queue — exist per git
      history, but haven't been retested since the P25 pivot)
- [x] **Device-level playback priority with preemption** —
      `playback_priority` in devices.yaml (marine 0, railroad 1, ham 5); a
      recording from a more important device interrupts the one playing, so
      continuous HAM/shortwave audio can't bury or stale-drop marine/railroad.
- [ ] **Channel-level playback priority** — the `priority` flag in channel
      YAMLs (e.g. Ch 16 distress over Ch 12, BNSF road channels) is still
      ignored; only device priority is used.
- [x] HAM **AM/SSB/CW demodulator** — `src/scanner/linear_demod.py`, tested
      in `tests/test_ham.py`. Continuous stations split into 30 s files.
- [x] **Shortwave day/night band switching** — `src/scanner/band_schedule.py`,
      sun elevation at the receiver; day 22m+19m (14.55 MHz), night 49m+41m
      (6.75 MHz). Each band scans the 5 kHz broadcast raster and records one
      station at a time (`max_active_channels: 1`). Verified live: locked
      onto 13.870 MHz and recorded continuous 30 s files through fades.
- [ ] Check the night band after dark — the 49m/41m choice is from general
      propagation, not yet confirmed with a night sweep from this antenna.
- [ ] Optional: rotate to another station after N minutes (currently stays
      on one station until it fades or the band switches).
- [x] Fixed detector cutting off long transmissions: the noise floor used
      to climb into any steady carrier in ~0.3 s, ending recordings ~3 s in
      (affected marine/railroad too). Re-test VHF end to end with this.
- [ ] Tune HAM activity detection against real signals — it uses the same
      FFT power threshold as VHF, with a per-mode SSB/CW/AM energy window.
      If HF noise/QRM makes that unreliable for SSB, switch to audio-domain
      voice-activity detection.
- [ ] If any HAM digital modes (FT8, PSK31, etc.) end up in scope: these
      aren't "audio to play back" the way NFM/SSB/CW are — they need
      time-synced decode (WSJT-x-style) producing decoded text/callsigns,
      not something the current playback-queue/audio-status model fits.
      Currently out of scope (SSB/CW only).

## Declared but not built

- [ ] `requirements.txt` includes `fastapi`/`uvicorn`/`websockets` but there's
      no corresponding web UI code in `src/` yet. This is the "monitor 2"
      audio-status dashboard (current audio output across
      Marine/Railroad/HAM) for the two-monitor plan — the ADS-B map
      (monitor 1) is already covered by dump1090-fa's SkyAware web UI.

## Out of scope for this repo (tracked separately)

- Uniden SDS200 + DPD antenna + coax + lightning arrestor/grounding — your
  hardware/RF chain, not part of the Pi's config or software.
