#!/usr/bin/env python3
"""Restart the ADS-B / AIS services when their dongle has gone quiet.

dump1090 and rtl_ais are separate programs under system services with
Restart=on-failure, which only helps if they exit. When a dongle drops off USB
they can instead keep running with no data. This checks their output once a
minute (systemd timer, sdr-watchdog.timer, as root) and restarts the service
whose data has stopped:

  dump1090-adsb  aircraft.json "messages" counter not increasing for QUIET_S
  rtl-ais        ships.json "last_rx" (AIS listener) older than QUIET_S
  ais-listener   ships.json not rewritten for STALE_S

Each service is restarted at most once per COOLDOWN_S, so an unplugged dongle
causes a restart every few minutes rather than a tight loop. The scanner's own
dongles (marine/railroad/HAM) reconnect in-process — see iq_source.py.
Stdlib only: runs under the system python3, not the project venv.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
AIRCRAFT_JSON = REPO_DIR / "run" / "adsb-json" / "aircraft.json"
SHIPS_JSON = REPO_DIR / "run" / "adsb-json" / "ships.json"
STATE = Path("/run/sdr-watchdog.json")

QUIET_S = 600      # no new ADS-B messages / AIS sentences for this long → restart
STALE_S = 120      # JSON file not rewritten for this long → its writer is dead
COOLDOWN_S = 600


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def main() -> None:
    now = time.time()
    state = _read(STATE) or {}
    restarts = state.setdefault("restarts", {})

    def restart(unit: str, why: str) -> None:
        if now - restarts.get(unit, 0) < COOLDOWN_S or not _active(unit):
            return   # just restarted, or stopped on purpose (e.g. antenna testing)
        print(f"restarting {unit}: {why}", flush=True)
        subprocess.run(["systemctl", "restart", unit], check=False)
        restarts[unit] = now

    # ── ADS-B ────────────────────────────────────────────────────────────────
    ac = _read(AIRCRAFT_JSON)
    if ac is None or now - ac.get("now", 0) > STALE_S:
        restart("dump1090-adsb", "aircraft.json missing or stale")
    else:
        msgs = ac.get("messages", 0)
        if msgs != state.get("adsb_messages"):
            state["adsb_messages"], state["adsb_since"] = msgs, now
        elif now - state.get("adsb_since", now) > QUIET_S:
            restart("dump1090-adsb", f"no new messages for {QUIET_S}s")
            state["adsb_since"] = now

    # ── AIS ──────────────────────────────────────────────────────────────────
    ships = _read(SHIPS_JSON)
    if ships is None or now - ships.get("now", 0) > STALE_S:
        restart("ais-listener", "ships.json missing or stale")
    elif "last_rx" in ships and now - ships["last_rx"] > QUIET_S:
        restart("rtl-ais", f"no AIS sentences for {QUIET_S}s")

    try:
        STATE.write_text(json.dumps(state))
    except OSError as e:
        print(f"could not save state: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
