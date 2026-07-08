"""
Per-device recording loop.

Monitors all channels on one dongle simultaneously via wideband FFT.
Each active channel is demodulated independently. When a transmission ends
(TAIL → IDLE), the accumulated audio is written to a WAV file whose name
encodes all metadata (timestamp, device, channel, frequency).
"""
import logging
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from src.scanner.channel_state import ChannelState
from src.scanner.fft_engine import Channel, FFTEngine
from src.scanner.iq_source import IQSource
from src.scanner.nfm_demod import AUDIO_RATE, NFMDemodulator

log = logging.getLogger(__name__)

_HEARTBEAT_S = 30.0


def _shift_to_baseband(iq: np.ndarray, offset_hz: float, sample_rate: float) -> np.ndarray:
    n = np.arange(len(iq), dtype=np.float64)
    return iq * np.exp(-2j * np.pi * offset_hz / sample_rate * n).astype(np.complex64)


class Recorder:
    """
    Captures all channel activity on one SDR dongle, writing a WAV file
    per transmission to recordings_dir/YYYYMMDD/.
    """

    def __init__(self, dev_id: str, serial: str, center_freq: float,
                 sample_rate: float, channels: list[Channel],
                 recordings_dir: str | Path,
                 gain: float | None = None, ppm: int = 0):
        self._dev_id = dev_id
        self._center_freq = center_freq
        self._sample_rate = sample_rate
        self._channels = channels
        self._recordings_dir = Path(recordings_dir)

        self._source = IQSource(serial, center_freq, sample_rate, gain, ppm)
        self._fft = FFTEngine(center_freq, sample_rate, channels)
        self._demods = [NFMDemodulator(sample_rate) for _ in channels]
        self._states = [ChannelState(i, ch.name) for i, ch in enumerate(channels)]

        self._buffers: list[list[np.ndarray]] = [[] for _ in channels]
        self._tx_start: list[float | None] = [None] * len(channels)

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── public ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self._source.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"rec-{self._dev_id}")
        self._thread.start()
        log.info("[%s] Recorder started — %.3f MHz center, %d channels",
                 self._dev_id, self._center_freq / 1e6, len(self._channels))

    def stop(self) -> None:
        self._stop.set()
        self._source.stop()
        if self._thread:
            self._thread.join(timeout=10.0)

    # ── private ────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        last_heartbeat = time.monotonic()

        while not self._stop.is_set():
            iq = self._source.get_block(timeout=1.0)
            if iq is None:
                continue

            active_set = set(self._fft.process(iq))
            now = time.monotonic()
            any_active = False

            for idx, ch in enumerate(self._channels):
                was_receiving = self._states[idx].is_receiving
                changed = self._states[idx].update(idx in active_set, now)
                is_receiving = self._states[idx].is_receiving

                if changed:
                    log.info("[%s] %-30s  %s", self._dev_id, ch.name,
                             self._states[idx].state.value.upper())

                if is_receiving:
                    any_active = True
                    if self._tx_start[idx] is None:
                        self._tx_start[idx] = time.time()
                    offset = ch.freq_hz - self._center_freq
                    bb = _shift_to_baseband(iq, offset, self._sample_rate)
                    self._buffers[idx].append(self._demods[idx].demodulate(bb))
                elif was_receiving:
                    self._flush(idx, ch)

            if not any_active and now - last_heartbeat >= _HEARTBEAT_S:
                log.info("[%s] Scanning…", self._dev_id)
                last_heartbeat = now

        # Flush any in-progress transmissions before exiting
        for idx, ch in enumerate(self._channels):
            if self._buffers[idx]:
                self._flush(idx, ch)

        log.info("[%s] Recorder stopped", self._dev_id)

    def _flush(self, idx: int, ch: Channel) -> None:
        if not self._buffers[idx]:
            return

        audio = np.concatenate(self._buffers[idx])
        duration_s = len(audio) / AUDIO_RATE

        now = datetime.now()
        day_dir = self._recordings_dir / now.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        safe_name = ch.name.replace("/", "_").replace(" ", "_")
        freq_khz = int(ch.freq_hz / 1000)
        fname = (f"{now.strftime('%Y%m%d_%H%M%S')}"
                 f"_{self._dev_id}_{safe_name}_{freq_khz}kHz.wav")

        # Atomic write: write to .tmp, then rename so watcher only sees complete files
        tmp = day_dir / (fname + ".tmp")
        dst = day_dir / fname

        audio_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        with wave.open(str(tmp), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(AUDIO_RATE)
            w.writeframes(audio_i16.tobytes())
        tmp.rename(dst)

        log.info("[%s] Saved %.1fs → %s", self._dev_id, duration_s, fname)

        self._buffers[idx] = []
        self._tx_start[idx] = None
        self._demods[idx].reset()
