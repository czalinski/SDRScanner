"""
Audio output — pipes float32 PCM to an aplay subprocess.

float32 [-1, 1]  →  int16 little-endian  →  aplay stdin
"""
import logging
import subprocess
import threading

import numpy as np

log = logging.getLogger(__name__)


class AudioSink:
    def __init__(self, rate: int = 48_000, channels: int = 1,
                 device: str = "default", label: str = ""):
        self.rate = rate
        self.channels = channels
        self.device = device
        self.label = label or "audio"
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def open(self) -> None:
        cmd = [
            "aplay",
            "-D", self.device,
            "-r", str(self.rate),
            "-f", "S16_LE",
            "-c", str(self.channels),
            "-",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("AudioSink [%s]: aplay started (rate=%d, dev=%s)",
                 self.label, self.rate, self.device)

    def write(self, audio: np.ndarray) -> None:
        """Write float32 [-1, 1] audio samples."""
        if self._proc is None or self._proc.poll() is not None:
            self._restart()
        if self._proc is None:
            return

        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with self._lock:
            try:
                self._proc.stdin.write(pcm.tobytes())  # type: ignore[union-attr]
            except BrokenPipeError:
                log.warning("AudioSink [%s]: aplay pipe broken — restarting", self.label)
                self._restart()

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
            except OSError:
                pass
            self._proc.wait(timeout=2.0)
        self._proc = None

    # ── private ────────────────────────────────────────────────────────────────

    def _restart(self) -> None:
        self.close()
        try:
            self.open()
        except Exception:
            log.exception("AudioSink [%s]: failed to restart aplay", self.label)
