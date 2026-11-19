"""Command-line control of the running scanner (same commands as voice).

  python -m src.scanner.ctl tune 6180            # stay on one shortwave station
  python -m src.scanner.ctl station "radio habana cuba"
  python -m src.scanner.ctl band 31              # scan the 31 m band
  python -m src.scanner.ctl auto                 # back to the day/night schedule
  python -m src.scanner.ctl onair 49             # what EiBi says is on 49 m now
  python -m src.scanner.ctl volume 60 | volume +10 | volume -10
  python -m src.scanner.ctl mute [source] | unmute [source]
  python -m src.scanner.ctl only marine | only all
  python -m src.scanner.ctl status | state
"""
import json
import sys

from src.scanner.control import BROADCAST_BANDS, send


def _request(args: list[str]) -> dict | None:
    cmd, rest = args[0], args[1:]
    arg = " ".join(rest) or None
    if cmd == "tune":
        return {"cmd": "ham", "freq_khz": float(rest[0])}
    if cmd == "station":
        return {"cmd": "ham", "station": arg}
    if cmd == "band":
        return {"cmd": "ham", "band": rest[0]}
    if cmd == "auto":
        return {"cmd": "ham", "mode": "auto"}
    if cmd == "volume":
        v = rest[0]
        return {"cmd": "volume", "delta": int(v)} if v[0] in "+-" else {"cmd": "volume", "set": int(v)}
    if cmd in ("mute", "unmute"):
        return {"cmd": cmd, "source": arg}
    if cmd == "only":
        return {"cmd": "focus", "source": None if arg in (None, "all") else arg}
    if cmd in ("status", "state"):
        return {"cmd": cmd}
    return None


def _onair(band: str) -> None:
    from src.scanner.station_db import StationDB
    band = band if band.endswith("m") else band + "m"
    lo, hi = BROADCAST_BANDS[band]
    for e in sorted(StationDB(download=False).on_air(lo, hi), key=lambda e: e.khz):
        print(f"{e.khz:7g} kHz  {e.station:32.32s} {e.language_name:12.12s} → {e.target}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if args[0] == "onair":
        _onair(args[1])
        return
    req = _request(args)
    if req is None:
        sys.exit(f"Unknown command {args[0]!r}\n{__doc__}")
    reply = send(req)
    print(json.dumps(reply.get("state"), indent=1) if "state" in reply else reply.get("say"))
    sys.exit(0 if reply.get("ok") else 1)


if __name__ == "__main__":
    main()
