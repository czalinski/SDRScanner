"""Runtime control of the scanner: speaker volume, mute, per-source mute and
focus, and what the HAM/shortwave dongle is tuned to.

State is saved to STATE_PATH on every change (rare — a voice command or a
`python -m src.scanner.ctl` call) and loaded at startup, so a reboot comes
back in the last mode. A missing or unreadable file means defaults.

Other programs (the voice-command service, the ctl CLI) talk to the running
scanner over a Unix socket at SOCKET_PATH: one JSON object per line in, one
JSON reply per line out — {"ok": true/false, "say": "<sentence to speak>"}.

Commands:
  {"cmd": "volume", "delta": 10} | {"cmd": "volume", "set": 60}
  {"cmd": "mute"} | {"cmd": "mute", "source": "railroad"}
  {"cmd": "unmute"} | {"cmd": "unmute", "source": "marine"}
  {"cmd": "focus", "source": "marine"} | {"cmd": "focus", "source": null}
  {"cmd": "ham", "mode": "auto"} | {"cmd": "ham", "band": "49m"}   (or "40m"/"75m": ham voice)
  {"cmd": "ham", "freq_khz": 6180} | {"cmd": "ham", "station": "radio habana cuba"}
  {"cmd": "status"}                  — what's playing / last played, as a sentence
  {"cmd": "hold", "seconds": 3}      — pause speaker playback (while the voice speaks)
  {"cmd": "state"}                   — the saved state, for display
"""
import difflib
import json
import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

STATE_PATH = Path.home() / ".local" / "state" / "sdrscanner" / "control.json"
SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "sdrscanner-control.sock"

SOURCES = ("marine", "railroad", "ham")
SPOKEN_SOURCE = {"marine": "marine", "railroad": "railroad", "ham": "shortwave"}
VOLUME_STEP = 10
DEFAULTS = {"volume": 80, "muted": False, "muted_sources": [], "focus": None,
            "ham": {"mode": "auto"}}

# Shortwave broadcast bands (kHz, ITU). "go to 31 meters" scans the whole band.
BROADCAST_BANDS = {
    "120m": (2300, 2495), "90m": (3200, 3400), "60m": (4750, 5060),
    "49m": (5900, 6200), "41m": (7200, 7600), "31m": (9400, 9900), "25m": (11600, 12100),
    "22m": (13570, 13870), "19m": (15100, 15800), "16m": (17480, 17900),
    "15m": (18900, 19020), "13m": (21450, 21850), "11m": (25670, 26100),
}
# Amateur (ham) phone segments, US General/Extra, and their sideband. 75m
# includes the 3.9–4.0 MHz broadcast band, which in the Americas is ham voice.
AMATEUR_BANDS = {"75m": (3600, 4000, "lsb"), "40m": (7125, 7300, "lsb"),
                 "20m": (14150, 14350, "usb")}
# SSB must be tuned to ~100 Hz: 1 kHz scan slots and 125 Hz FFT bins
# (fft_engine fft_size; linear_demod.DETECT_WINDOW explains the slot choice).
# Default hold settings, so a steady carrier/RFI whine is absorbed in a minute.
SSB_DETECTOR = {"fft_size": 16384}
# Tune the dongle this far below the band/station: the RTL-SDR's DC spike sits
# at its centre frequency, so nothing we listen to may be there.
DC_OFFSET_KHZ = 30


def amateur_band_of(khz: float) -> str | None:
    for name, (lo, hi, _) in AMATEUR_BANDS.items():
        if lo <= khz <= hi:
            return name
    return None


def band_of(khz: float) -> str | None:
    if amateur_band_of(khz):
        return amateur_band_of(khz)
    for name, (lo, hi) in BROADCAST_BANDS.items():
        if lo <= khz <= hi:
            return name
    return None


def band_for_meters(name: str) -> dict | None:
    """Band dict (band_schedule.py format) scanning a whole broadcast or ham band."""
    if name in AMATEUR_BANDS:
        lo, hi, mode = AMATEUR_BANDS[name]
        return {"name": f"{name} ham", "center_mhz": (lo - DC_OFFSET_KHZ) / 1000,
                "detector": SSB_DETECTOR,
                "scan_ranges": [{"label": name, "from_mhz": lo / 1000, "to_mhz": hi / 1000,
                                 "step_khz": 1, "mode": mode}]}
    if name not in BROADCAST_BANDS:
        return None
    lo, hi = BROADCAST_BANDS[name]
    return {"name": name, "center_mhz": (lo - DC_OFFSET_KHZ) / 1000,
            "scan_ranges": [{"label": name, "from_mhz": lo / 1000, "to_mhz": hi / 1000,
                             "step_khz": 5}]}


def band_for_freq(khz: float) -> dict:
    """Band dict holding a single station — the radio stays on it."""
    label = band_of(khz) or "HF"
    band = {"name": f"{khz:g} kHz", "center_mhz": (khz - DC_OFFSET_KHZ) / 1000,
            "channels": [{"name": f"{label} {khz:g}", "freq_mhz": khz / 1000, "mode": "am"}]}
    ham = amateur_band_of(khz)
    if ham:                                       # a ham voice frequency — sideband
        band["channels"][0]["mode"] = AMATEUR_BANDS[ham][2]
        band["detector"] = SSB_DETECTOR
    return band


def load_state(path: Path = STATE_PATH) -> dict:
    """Saved state merged over DEFAULTS; anything missing, corrupt or of the
    wrong type falls back to the default."""
    state = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(path.read_text())
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as e:
        log.warning("Control state %s unreadable (%s) — using defaults", path, e)
        return state
    if not isinstance(saved, dict):
        return state
    if isinstance(saved.get("volume"), int) and 0 <= saved["volume"] <= 100:
        state["volume"] = saved["volume"]
    if isinstance(saved.get("muted"), bool):
        state["muted"] = saved["muted"]
    if isinstance(saved.get("muted_sources"), list):
        state["muted_sources"] = [s for s in saved["muted_sources"] if s in SOURCES]
    if saved.get("focus") in SOURCES:
        state["focus"] = saved["focus"]
    ham = saved.get("ham")
    if isinstance(ham, dict) and (ham.get("mode") == "auto"
                                  or ham.get("band") in BROADCAST_BANDS
                                  or ham.get("band") in AMATEUR_BANDS
                                  or isinstance(ham.get("freq_khz"), (int, float))):
        state["ham"] = ham
    return state


class Control:
    def __init__(self, path: Path = STATE_PATH, apply_volume: bool = True):
        self._path = Path(path)
        self._apply_volume = apply_volume
        self._lock = threading.RLock()
        self.state = load_state(self._path)
        self._hold_until = 0.0
        # Wired up by main once they exist
        self.playback = None          # PlaybackQueue
        self.ham_switcher = None      # BandSwitcher
        self.station_db = None        # StationDB (also reachable via playback)
        self._set_volume(self.state["volume"])

    # ── queries used by the playback queue ──────────────────────────────────
    def should_play(self, device: str) -> bool:
        s = self.state
        if s["muted"] or device in s["muted_sources"]:
            return False
        return s["focus"] is None or s["focus"] == device

    def held(self) -> bool:
        return time.monotonic() < self._hold_until

    def ham_band(self) -> dict | None:
        """Band the HAM dongle should use, or None for the day/night schedule."""
        ham = self.state["ham"]
        if "band" in ham:
            return band_for_meters(ham["band"])
        if "freq_khz" in ham:
            return band_for_freq(ham["freq_khz"])
        return None

    # ── commands ─────────────────────────────────────────────────────────────
    def handle(self, req: dict) -> dict:
        cmd = req.get("cmd")
        try:
            with self._lock:
                fn = getattr(self, f"_cmd_{cmd}", None)
                if fn is None:
                    return {"ok": False, "say": f"Unknown command {cmd}."}
                reply = fn(req)
        except Exception:
            log.exception("Control command failed: %r", req)
            return {"ok": False, "say": "Sorry, that didn't work."}
        log.info("Control %s → %s", req, reply.get("say"))
        return reply

    def _cmd_volume(self, req):
        if "set" in req:
            v = int(req["set"])
        else:
            v = self.state["volume"] + int(req.get("delta", VOLUME_STEP))
        v = max(0, min(100, v))
        self.state["volume"] = v
        self._set_volume(v)
        self._save()
        return {"ok": True, "say": f"Volume {v} percent."}

    def _cmd_mute(self, req):
        src = req.get("source")
        if src is None:
            self.state["muted"] = True
            say = "Muted."
        elif src in SOURCES:
            if src not in self.state["muted_sources"]:
                self.state["muted_sources"].append(src)
            say = f"{SPOKEN_SOURCE[src].capitalize()} muted."
        else:
            return {"ok": False, "say": f"I don't know the source {src}."}
        self._save()
        return {"ok": True, "say": say}

    def _cmd_unmute(self, req):
        src = req.get("source")
        if src is None:
            self.state.update(muted=False, muted_sources=[], focus=None)
            say = "Unmuted. Playing everything."
        elif src in SOURCES:
            self.state["muted_sources"] = [s for s in self.state["muted_sources"] if s != src]
            if self.state["focus"] not in (None, src):
                self.state["focus"] = None
            say = f"{SPOKEN_SOURCE[src].capitalize()} unmuted."
        else:
            return {"ok": False, "say": f"I don't know the source {src}."}
        self._save()
        return {"ok": True, "say": say}

    def _cmd_focus(self, req):
        src = req.get("source")
        if src is None:
            self.state.update(focus=None, muted_sources=[])
            say = "Playing everything."
        elif src in SOURCES:
            self.state["focus"] = src
            self.state["muted_sources"] = [s for s in self.state["muted_sources"] if s != src]
            say = f"Only {SPOKEN_SOURCE[src]}."
        else:
            return {"ok": False, "say": f"I don't know the source {src}."}
        self.state["muted"] = False
        self._save()
        return {"ok": True, "say": say}

    def _cmd_ham(self, req):
        if req.get("mode") == "auto":
            self.state["ham"] = {"mode": "auto"}
            say = "Shortwave back on the automatic day and night schedule."
        elif "band" in req:
            band = str(req["band"]).lower().replace(" ", "")
            band = band if band.endswith("m") else band + "m"
            if band in AMATEUR_BANDS:
                say = f"Listening for hams on {band[:-1]} meters."
            elif band in BROADCAST_BANDS:
                say = f"Scanning the {band[:-1]} meter broadcast band."
            else:
                return {"ok": False, "say": f"I don't have a {band[:-1]} meter band."}
            self.state["ham"] = {"band": band}
        elif "freq_khz" in req:
            khz = float(req["freq_khz"])
            if not 1600 <= khz <= 30000:
                return {"ok": False, "say": f"{khz:g} kilohertz is outside the shortwave range."}
            self.state["ham"] = {"freq_khz": khz}
            name = self._station_label(khz)
            say = f"Tuned to {khz:g} kilohertz" + (f", {name.rstrip('.')}." if name else ".")
        elif "station" in req:
            hit = self._find_station(str(req["station"]))
            if hit is None:
                return {"ok": False, "say": f"I can't find {req['station']} on the air right now."}
            self.state["ham"] = {"freq_khz": hit.khz}
            say = f"Tuning to {hit.station.rstrip('.')} on {hit.khz:g} kilohertz."
        else:
            return {"ok": False, "say": "Tune to what?"}
        self._save()
        if self.ham_switcher is not None:
            self.ham_switcher.retune()
        return {"ok": True, "say": say}

    def _cmd_status(self, req):
        pb = self.playback
        history = list(pb.history) if pb is not None else []
        if not history:
            return {"ok": True, "say": "Nothing has played yet."}
        e = history[0]
        text = spoken_description(e)
        if e.get("status") == "playing" and time.time() < e["started"] + e.get("duration_s", 0) + 1:
            return {"ok": True, "say": f"This is {text}."}
        ago = int(time.time() - e["started"])
        when = f"{ago} seconds ago" if ago < 120 else f"{ago // 60} minutes ago"
        return {"ok": True, "say": f"The last one was {text}, {when}."}

    def _cmd_hold(self, req):
        self._hold_until = time.monotonic() + min(30.0, float(req.get("seconds", 3)))
        return {"ok": True, "say": ""}

    def _cmd_state(self, req):
        return {"ok": True, "say": "", "state": self.state}

    # ── helpers ──────────────────────────────────────────────────────────────
    def _db(self):
        return self.station_db or getattr(self.playback, "station_db", None)

    def _station_label(self, khz: float) -> str | None:
        db = self._db()
        ident = db.identify(khz) if db else None
        return ident[0] if ident else None

    def _find_station(self, name: str):
        """Best on-air schedule entry whose station name matches `name`."""
        db = self._db()
        if db is None:
            return None
        want = name.lower().strip()
        best, best_score = None, 0.0
        for e in db.on_air(1600, 30000):
            station = e.station.lower()
            score = difflib.SequenceMatcher(None, want, station).ratio()
            if want in station or all(w in station for w in want.split()):
                score = max(score, 0.9)
            # Prefer broadcasts aimed at us, then lower bands at night / higher by day
            score += 0.05 if e.target in ("NAm", "Am", "CAm", "USA", "WNA") else 0.0
            if score > best_score:
                best, best_score = e, score
        return best if best_score >= 0.7 else None

    def _set_volume(self, v: int) -> None:
        if not self._apply_volume:
            return
        try:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"],
                           timeout=5, check=False, capture_output=True)
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("Could not set volume: %s", e)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, indent=1))
            tmp.rename(self._path)
        except OSError as e:
            log.warning("Could not save control state: %s", e)


def spoken_description(e: dict) -> str:
    """'marine channel 14, Vessel Traffic' / 'Radio Habana Cuba, 6000 kilohertz, in Spanish'."""
    dev, channel, freq = e.get("device"), e.get("channel") or "", e.get("freq_khz")
    if dev == "ham":
        if e.get("station"):
            lang = f", in {e['language']}" if e.get("language") else ""
            return f"{e['station']}, {freq} kilohertz{lang}"
        ham = amateur_band_of(freq) if freq else None
        if ham:
            return f"ham radio, {ham[:-1]} meters, {freq} kilohertz"
        return f"shortwave {freq} kilohertz"
    name = channel.replace("Ch ", "channel ").replace(" — ", ", ")
    return f"{'railroad' if dev == 'railroad' else dev} {name}"


# ── socket server / client ───────────────────────────────────────────────────

def serve(control: Control, path: Path = SOCKET_PATH) -> threading.Thread:
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path))
    os.chmod(path, 0o600)
    srv.listen(4)

    def _client(conn):
        with conn, conn.makefile("rw") as f:
            for line in f:
                try:
                    req = json.loads(line)
                    reply = control.handle(req) if isinstance(req, dict) else {"ok": False}
                except ValueError:
                    reply = {"ok": False, "say": "Bad request."}
                f.write(json.dumps(reply) + "\n")
                f.flush()

    def _accept():
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=_client, args=(conn,), daemon=True).start()

    t = threading.Thread(target=_accept, daemon=True, name="control")
    t.start()
    log.info("Control socket %s", path)
    return t


def send(req: dict, path: Path = SOCKET_PATH, timeout: float = 10.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(path))
        with s.makefile("rw") as f:
            f.write(json.dumps(req) + "\n")
            f.flush()
            return json.loads(f.readline())
