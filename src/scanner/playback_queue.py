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
"""
import heapq
import itertools
import logging
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PRIORITY = 1
_POLL_S = 0.2


def device_id_from_filename(name: str) -> str:
    parts = Path(name).stem.split("_")
    return parts[2] if len(parts) > 2 else ""


class PlaybackQueue:
    def __init__(self, recordings_dir: str | Path, max_latency_s: float = 30.0,
                 priorities: dict[str, int] | None = None):
        self._dir = Path(recordings_dir)
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

            log.info("Playing: %s", path.name)
            try:
                proc = subprocess.Popen(["aplay", "-q", str(path)])
            except FileNotFoundError:
                log.error("aplay not found — is alsa-utils installed?")
                self._stop.set()
                return

            started = time.monotonic()
            while proc.poll() is None:
                if self._stop.is_set() or self._more_important_waiting(prio):
                    if not self._stop.is_set():
                        log.info("Interrupted %s for higher-priority audio", path.name)
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
