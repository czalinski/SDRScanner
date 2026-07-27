# SDRScanner — TODO

Current scope: railroad + marine + HAM audio scanning with playback
(Orange Pi), and ADS-B with a live map + feeds to
FlightAware/FlightRadar24/ADS-B Exchange. P25 (fire/police) runs on a
standalone Uniden SDS200 — its antenna/RF chain is tracked separately, not
part of this list. AIS is explicitly out of scope (dropped — not doing it).

Long-term: two-monitor setup — one showing the ADS-B live map (dump1090-fa
SkyAware, already planned), one showing current audio-output status across
Marine/Railroad/HAM (not built yet — see "Declared but not built" below).

## Resolved this session

- [x] Found the Pi at its new IP (`192.168.68.98`, was `.230`) — updated in
      `CLAUDE.md` and `docs/hardware.md`.
- [x] Confirmed all 4 dongles enumerate: `RTLSDR_RR`, `RTLSDR_MRN`,
      `RTLSDR_ADSB` (burned this session), and an unserialized NooElec
      SMArTee v5 (now assigned to HAM, see below).
- [x] **Diagnosed and fixed USB hub power issue**: a bus-powered 4-port hub
      caused constant disconnect/reconnect churn under load — confirmed via
      dmesg (repeated re-enumeration, a `device descriptor read` error).
      Swapped to an externally-powered hub, which resolved it. You may still
      swap to a different powered-hub model for a single shared power
      supply — not urgent, current one works.
- [x] Live ADS-B reception confirmed via `dump1090` (SoapySDR backend) —
      strong, continuous DF17/Mode-S traffic from multiple aircraft.
- [x] **AIS dropped from scope entirely** — removed the `ais` device from
      `devices.yaml`, the `ais` role from `set_serials.sh`, the `rtl_ais`
      launch block from `start_scanner.sh`, the rtl-ais build step from
      `install.sh`, the AIS section from `docs/hardware.md`/`docs/antennas.md`,
      and the AIS block from `config/channels/marine.yaml`.
- [x] **HAM added to scope**: the second NooElec v5 (a SMArTee variant,
      bias-tee enabled) is now assigned the `ham` role in `devices.yaml`
      (serial `RTLSDR_HAM`, not yet burned). Scope is HF (SSB/CW), not
      2m/70cm FM — this needs a demodulator this codebase doesn't have yet
      (see Software section below).

## Hardware

- [ ] Burn `RTLSDR_HAM` serial: `./scripts/set_serials.sh ham`
- [ ] **HAM hardware decided**: buy a Ham It Up Plus v2 upconverter, power
      it via the SMArTee v5's built-in bias tee (not the XTR bundle — no
      need for a second RTL-SDR). Purchase + wire in.
- [ ] Build/mount ADS-B antenna (spec: `docs/antennas.md` §4)
- [ ] Spec + build HAM antenna once band(s) of interest are chosen
      (`docs/antennas.md` §5 — currently a placeholder)
- [ ] Confirm railroad + marine antennas are actually built/mounted to spec
      (`docs/antennas.md` §1/§2) — `CLAUDE.md` lists both dongles as
      "Connected" already, but worth verifying the antenna side matches
- [ ] 7" display: mount, connect, confirm a desktop/X session is available
      on the Pi for a kiosk browser (needed before the map autostart works)
- [ ] Second monitor for the audio-status dashboard — physical mount/connect
      once that dashboard exists (see "Declared but not built")
- [ ] PPM calibration for all dongles via `kalibrate-rtl`
      (`docs/hardware.md` setup step 4) — not yet confirmed done

## Software — ADS-B

- [ ] One-time feeder account setup (these are what `start_scanner.sh` now
      assumes are already configured):
      - `dump1090-fa`: set the `RTLSDR_ADSB` device serial in
        `/etc/default/dump1090-fa`
      - piaware: `sudo piaware-config -force -latitude <lat> -longitude <lon>`,
        then claim at flightaware.com/adsb/piaware/claim
      - fr24feed: `sudo dpkg-reconfigure fr24feed`, enter your sharing key
      - ADS-B Exchange: one-time `docker run` per adsbexchange.com/how-to-feed
        to create the `adsbx-feed` container (script only `docker start`s an
        existing one)
- [ ] Fill in real `receiver_lat` / `receiver_lon` / `receiver_alt_m` in
      `config/channels/adsb.yaml` — currently a Tacoma-approximate
      placeholder; accurate mlat needs the real antenna position
- [ ] Kiosk browser autostart for the 7" display — commented out in
      `install.sh`, needs your display's actual setup to fill in

## Software — railroad/marine/HAM audio + playback

- [ ] Fresh end-to-end test of railroad + marine running concurrently with
      the playback queue now that project scope has changed (the pieces —
      FFT scan, NFM demod, recorder, playback queue — exist per git
      history, but haven't been retested since the P25 pivot)
- [ ] **Playback queue is currently a single shared FIFO across all
      devices** (`src/scanner/playback_queue.py`) — one `aplay` at a time,
      no priority awareness even though channel YAMLs already have a
      `priority` flag. Adding HAM traffic (which may run higher duty-cycle
      than railroad/marine) risks burying or stale-dropping priority
      channels (Ch 16 distress, BNSF road channels). Needs a priority-aware
      playback model before HAM goes live — agreed direction: priority
      channels preempt/jump ahead of routine traffic in the same shared
      queue, not separate audio outputs.
- [ ] HAM needs an **SSB/CW demodulator** — `src/scanner/nfm_demod.py` only
      handles NFM. Also needs a different channel-activity detection
      approach than the FFT power-threshold used for railroad/marine (HF
      noise floor/QRM makes that unreliable for SSB) — likely audio-domain
      voice-activity detection instead.
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
