"""
Playback queue: watches recordings/ for new WAV files and plays them in order.

Files older than max_latency_s when dequeued are silently dropped — this
prevents a backlog of simultaneous activity from playing minutes later when
the context is gone.

Ordering is by device priority (lower number = more important), then age.
A file from a more important device interrupts whatever is playing — so
marine/railroad calls cut in over HAM/shortwave, which is continuous
background audio (split into ~30 s segments by the Recorder). Priorities come
from `playback_priority` in config/devices.yaml; the device id is the third
"_"-separated field of the recording filename (see Recorder._flush).

If history_path is given, the last HISTORY_LEN clips played (newest first,
with the one playing now marked) are written there as JSON after every change
— the kiosk map (src/display/adsb_map.py) shows it as the audio panel.
"""
import heapq
import itertools
import json
import logging
import subprocess
import threading
import time
import wave
from collections import deque
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PRIORITY = 1
_POLL_S = 0.2
HISTORY_LEN = 50


def device_id_from_filename(name: str) -> str:
    parts = Path(name).stem.split("_")
    return parts[2] if len(parts) > 2 else ""


def describe_recording(name: str) -> dict:
    """Device, channel name and frequency from a recording filename
    (YYYYMMDD_HHMMSS_<device>_<channel name>_<freq>kHz.wav — Recorder._flush
    turned the channel name's spaces into underscores)."""
    parts = Path(name).stem.split("_")
    freq = parts[-1].removesuffix("kHz") if len(parts) >= 5 else ""
    return {
        "device": device_id_from_filename(name),
        "channel": " ".join(parts[3:-1]) if len(parts) >= 5 else Path(name).stem,
        "freq_khz": int(freq) if freq.isdigit() else None,
    }


def _wav_duration_s(path: Path) -> float:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, EOFError, wave.Error):
        return 0.0


class PlaybackQueue:
    def __init__(self, recordings_dir: str | Path, max_latency_s: float = 30.0,
                 priorities: dict[str, int] | None = None,
                 history_path: str | Path | None = None, station_db=None):
        self._dir = Path(recordings_dir)
        self._history_path = Path(history_path) if history_path else None
        self._history: deque[dict] = deque(maxlen=HISTORY_LEN)
        # StationDB (station_db.py) — names shortwave clips; may be set later,
        # once the schedule has loaded in the background
        self.station_db = station_db
        # Control (control.py) — mute / focus / hold; None = play everything
        self.control = None
        self._max_latency = max_latency_s
        self._priorities = priorities or {}
        self._heap: list[tuple[int, float, int, Path]] = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._seen: set[Path] = set()
        self._stop = threading.Event()
        self._watcher = threading.Thread(target=self._watch, daemon=True, name="pb-watch")
        self._player = threading.Thread(target=self._play, daemon=True, name="pb-play")

    def start(self) -> None:
        self._stop.clear()
        self._watcher.start()
        self._player.start()
        log.info("PlaybackQueue started (recordings=%s, max_latency=%.0fs, priorities=%s)",
                 self._dir, self._max_latency, self._priorities)

    def stop(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()
        self._watcher.join(timeout=3.0)
        self._player.join(timeout=5.0)
        log.info("PlaybackQueue stopped")

    def priority_of(self, path: Path) -> int:
        return self._priorities.get(device_id_from_filename(path.name), DEFAULT_PRIORITY)

    def enqueue(self, path: Path) -> None:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        with self._cv:
            heapq.heappush(self._heap, (self.priority_of(path), mtime, next(self._seq), path))
            self._cv.notify()

    # ── private ────────────────────────────────────────────────────────────────

    def _watch(self) -> None:
        """Poll recordings dir every second; enqueue any WAV file not yet seen."""
        while not self._stop.is_set():
            # Only today's and yesterday's day folders (yesterday covers
            # midnight): with a week of recordings kept, rglob over the whole
            # tree every second would cost real CPU, and anything older is
            # past max_latency_s anyway.
            now = time.time()
            current: set[Path] = set()
            for day in {time.strftime("%Y%m%d", time.localtime(now - d)) for d in (0, 86400)}:
                day_dir = self._dir / day
                if day_dir.is_dir():
                    current.update(day_dir.glob("*.wav"))
            for f in sorted(current - self._seen):
                self.enqueue(f)
            self._seen = current
            self._stop.wait(1.0)

    def _next(self) -> tuple[int, Path] | None:
        with self._cv:
            while not self._heap and not self._stop.is_set():
                self._cv.wait(timeout=1.0)
            if not self._heap:
                return None
            prio, _, _, path = heapq.heappop(self._heap)
            return prio, path

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def _blocked(self, device: str) -> bool:
        c = self.control
        return c is not None and not c.should_play(device)

    def _write_history(self) -> None:
        if not self._history_path:
            return
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._history_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"now": time.time(), "history": list(self._history)}))
            tmp.rename(self._history_path)
        except OSError as e:
            log.warning("Could not write playback history: %s", e)

    def _more_important_waiting(self, prio: int) -> bool:
        with self._cv:
            return bool(self._heap) and self._heap[0][0] < prio

    def _play(self) -> None:
        """Dequeue and play; drop stale files; let higher priority interrupt."""
        while not self._stop.is_set():
            item = self._next()
            if item is None:
                continue
            prio, path = item

            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue

            if age > self._max_latency:
                log.info("Drop stale: %s (%.0fs old)", path.name, age)
                continue

            device = device_id_from_filename(path.name)
            if self._blocked(device):
                log.debug("Muted: %s", path.name)
                continue
            while self.control is not None and self.control.held() and not self._stop.is_set():
                time.sleep(_POLL_S)            # the voice service is speaking

            log.info("Playing: %s", path.name)
            entry = {**describe_recording(path.name), "started": time.time(),
                     "duration_s": round(_wav_duration_s(path), 1), "status": "playing"}
            if entry["device"] == "ham" and entry["freq_khz"] and self.station_db:
                ident = self.station_db.identify(entry["freq_khz"])
                if ident:
                    entry["station"], entry["language"] = ident
            self._history.appendleft(entry)
            self._write_history()
            try:
                proc = subprocess.Popen(["aplay", "-q", str(path)])
            except FileNotFoundError:
                log.error("aplay not found — is alsa-utils installed?")
                self._stop.set()
                return

            started = time.monotonic()
            outcome = "played"
            while proc.poll() is None:
                muted_now = self._blocked(device) or (self.control is not None
                                                       and self.control.held())
                if self._stop.is_set() or muted_now or self._more_important_waiting(prio):
                    if not self._stop.is_set():
                        log.info("Interrupted %s for %s", path.name,
                                 "mute/voice" if muted_now else "higher-priority audio")
                    outcome = "interrupted"
                    proc.terminate()
                    break
                if time.monotonic() - started > 300:
                    log.warning("aplay timed out on %s", path.name)
                    proc.terminate()
                    break
                time.sleep(_POLL_S)
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            entry["status"] = outcome
            self._write_history()
