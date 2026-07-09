# SDRScanner — TODO

Current scope: railroad + marine audio scanning with playback (Orange Pi),
and ADS-B with a live map + feeds to FlightAware/FlightRadar24/ADS-B
Exchange. P25 (fire/police) runs on a standalone Uniden SDS200 — its
antenna/RF chain is tracked separately, not part of this list.

## Resolved this session

- [x] `start_scanner.sh` fixed: correct `RTLSDR_ADSB` serial, launches
      `dump1090-fa` + piaware/fr24feed/adsbx-feed as system
      services/container instead of a hand-rolled `dump1090` invocation,
      stale P25 comment removed.
- [x] **Marine/AIS dongle conflict resolved**: added a dedicated `ais`
      device (`RTLSDR_AIS`, one of the two NooElec v5 dongles) in
      `devices.yaml`, split off the marine antenna via a 2-way splitter
      (156–162 MHz — AIS and marine voice are the same band, no separate
      antenna build needed). `set_serials.sh` has an `ais` role now.
      `rtl_ais` and the Python marine voice scanner each get their own
      dongle, no more shared-serial conflict.

## Hardware

- [ ] Purchase the cheap RTL-SDR (~$25) for ADS-B (`devices.yaml` id `adsb`,
      serial `RTLSDR_ADSB`)
- [ ] Build/mount ADS-B antenna (spec: `docs/antennas.md` §4)
- [ ] Get the 2-way splitter for the marine antenna (feeds both `RTLSDR_MRN`
      and the new `RTLSDR_AIS` dongle) and wire it in
- [ ] Confirm railroad + marine antennas are actually built/mounted to spec
      (`docs/antennas.md` §1/§2) — `CLAUDE.md` lists both dongles as
      "Connected" already, but worth verifying the antenna side matches
- [ ] 7" display: mount, connect, confirm a desktop/X session is available
      on the Pi for a kiosk browser (needed before the map autostart works)
- [ ] PPM calibration for all dongles via `kalibrate-rtl`
      (`docs/hardware.md` setup step 4) — not yet confirmed done
- [ ] Once the AIS NooElec v5 arrives: run `./scripts/set_serials.sh ais`
      to program it

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

## Software — railroad/marine audio + playback

- [ ] Fresh end-to-end test of railroad + marine running concurrently with
      the playback queue now that project scope has changed (the pieces —
      FFT scan, NFM demod, recorder, playback queue — exist per git
      history, but haven't been retested since the P25 pivot)
- [ ] Once the AIS dongle/splitter are physically in place, test AIS and
      marine voice running concurrently

## Declared but not built

- [ ] `requirements.txt` includes `fastapi`/`uvicorn`/`websockets` but there's
      no corresponding web UI code in `src/` yet. Decide whether that's still
      planned (e.g. a dashboard combining railroad/marine status + the ADS-B
      map) or drop the unused dependencies.

## Out of scope for this repo (tracked separately)

- Uniden SDS200 + DPD antenna + coax + lightning arrestor/grounding — your
  hardware/RF chain, not part of the Pi's config or software.
