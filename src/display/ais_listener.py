"""AIS listener: decodes rtl_ais's NMEA UDP stream into vessel positions.

rtl_ais (see scripts/run_rtl_ais.sh) decodes raw AIS RF into standard NMEA
AIVDM sentences and forwards them over UDP. This listens on that socket,
feeds sentences to pyais's AISTracker (which handles multi-part message
reassembly and per-vessel state automatically), and periodically writes a
ships.json file in the same spirit as dump1090's --write-json aircraft.json
so src/display/adsb_map.py can read vessel positions the same way it reads
aircraft.
"""
import enum
import json
import logging
import socket
import time
from pathlib import Path

from pyais import AISTracker
from pyais.messages import AISSentence

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

REPO_DIR = Path(__file__).resolve().parents[2]
SHIPS_JSON = REPO_DIR / "run" / "adsb-json" / "ships.json"

UDP_HOST = "127.0.0.1"
UDP_PORT = 10110
WRITE_INTERVAL_S = 1.0
TRACK_TTL_S = 600  # drop vessels not heard from in 10 minutes


def _jsonable(value):
    if isinstance(value, enum.Enum):
        return value.name
    return value


def _write_ships(tracker: AISTracker) -> None:
    ships = []
    for t in tracker.tracks:
        if t.lat is None or t.lon is None:
            continue  # static/voyage-only messages — no position yet, nothing to plot

        ships.append({
            "mmsi": t.mmsi,
            "lat": t.lat,
            "lon": t.lon,
            "course": t.course,
            "speed": t.speed,
            "shipname": (t.shipname or "").strip() or None,
            "callsign": (t.callsign or "").strip() or None,
            "ship_type": _jsonable(t.ship_type),
            "status": _jsonable(t.status),
        })

    tmp = SHIPS_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"now": time.time(), "ships": ships}))
    tmp.rename(SHIPS_JSON)


def main() -> None:
    SHIPS_JSON.parent.mkdir(parents=True, exist_ok=True)
    tracker = AISTracker(ttl_in_seconds=TRACK_TTL_S)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_HOST, UDP_PORT))
    sock.settimeout(1.0)
    log.info("Listening for AIS NMEA on udp://%s:%d", UDP_HOST, UDP_PORT)

    last_write = 0.0
    while True:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            data = None

        if data:
            for line in data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    tracker.update(AISSentence(line))
                except Exception as e:
                    log.debug("Could not decode AIS sentence %r: %s", line, e)

        now = time.time()
        if now - last_write >= WRITE_INTERVAL_S:
            tracker.cleanup()
            _write_ships(tracker)
            last_write = now


if __name__ == "__main__":
    main()
