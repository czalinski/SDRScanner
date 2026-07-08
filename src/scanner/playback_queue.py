"""
Playback queue: watches recordings/ for new WAV files and plays them in order.

Files older than max_latency_s when dequeued are silently dropped — this
prevents a backlog of simultaneous activity from playing minutes later when
the context is gone. The queue drains FIFO otherwise.
"""
import logging
import queue
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)


class PlaybackQueue:
    def __init__(self, recordings_dir: str | Path, max_latency_s: float = 30.0):
        self._dir = Path(recordings_dir)
        self._max_latency = max_latency_s
        self._q: queue.Queue[Path] = queue.Queue()
        self._seen: set[Path] = set()
        self._stop = threading.Event()
        self._watcher = threading.Thread(target=self._watch, daemon=True, name="pb-watch")
        self._player = threading.Thread(target=self._play, daemon=True, name="pb-play")

    def start(self) -> None:
        self._stop.clear()
        self._watcher.start()
        self._player.start()
        log.info("PlaybackQueue started (recordings=%s, max_latency=%.0fs)",
                 self._dir, self._max_latency)

    def stop(self) -> None:
        self._stop.set()
        self._watcher.join(timeout=3.0)
        self._player.join(timeout=5.0)
        log.info("PlaybackQueue stopped")

    # ── private ────────────────────────────────────────────────────────────────

    def _watch(self) -> None:
        """Poll recordings dir every second; enqueue any WAV file not yet seen."""
        while not self._stop.is_set():
            if self._dir.exists():
                for f in sorted(self._dir.rglob("*.wav")):
                    if f not in self._seen:
                        self._seen.add(f)
                        self._q.put(f)
            self._stop.wait(1.0)

    def _play(self) -> None:
        """Dequeue and play; drop anything older than max_latency_s."""
        while not self._stop.is_set():
            try:
                path = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue

            if age > self._max_latency:
                log.info("Drop stale: %s (%.0fs old)", path.name, age)
                continue

            log.info("Playing: %s", path.name)
            try:
                subprocess.run(["aplay", "-q", str(path)],
                               timeout=300, check=False)
            except subprocess.TimeoutExpired:
                log.warning("aplay timed out on %s", path.name)
            except FileNotFoundError:
                log.error("aplay not found — is alsa-utils installed?")
                self._stop.set()
