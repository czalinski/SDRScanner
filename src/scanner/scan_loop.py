"""
Per-dongle scan loop: IQ capture → FFT detection → NFM demodulation → audio.

One ScanLoop runs in its own thread for each connected SDR device that has
a channel_config assigned. It implements the spectrum-analyzer scanning strategy:
  - Always captures the full wideband spectrum (2 MS/s ≈ 2 MHz window)
  - Detects channel activity via averaged FFT + adaptive noise floor
  - Locks onto the highest-SNR active channel
  - Holds the lock through TAIL_TIMEOUT seconds of silence
  - Releases and resumes scanning when the channel goes fully quiet
"""
import logging
import threading
import time

import numpy as np

from src.scanner.audio_sink import AudioSink
from src.scanner.channel_state import ChannelState, State
from src.scanner.fft_engine import Channel, FFTEngine
from src.scanner.iq_source import IQSource
from src.scanner.nfm_demod import AUDIO_RATE, NFMDemodulator

log = logging.getLogger(__name__)

# Log a "still scanning" heartbeat no more often than this
_HEARTBEAT_S = 30.0


def _shift_to_baseband(iq: np.ndarray, offset_hz: float, sample_rate: float) -> np.ndarray:
    """Frequency-translate `iq` so that `offset_hz` maps to 0 Hz."""
    n = np.arange(len(iq), dtype=np.float64)
    shift = np.exp(-2j * np.pi * offset_hz / sample_rate * n).astype(np.complex64)
    return iq * shift


class ScanLoop:
    def __init__(self, dev_id: str, serial: str, center_freq: float,
                 sample_rate: float, channels: list[Channel],
                 gain: float | None = None, ppm: int = 0,
                 audio_device: str = "default"):
        self._dev_id = dev_id
        self.channels = channels
        self.center_freq = center_freq
        self.sample_rate = sample_rate

        self._source = IQSource(serial, center_freq, sample_rate, gain, ppm)
        self._fft = FFTEngine(center_freq, sample_rate, channels)
        self._demod = NFMDemodulator(sample_rate)
        self._states = [ChannelState(i, ch.name) for i, ch in enumerate(channels)]
        self._audio = AudioSink(rate=AUDIO_RATE, label=dev_id, device=audio_device)

        self._locked_ch: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── public ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._audio.open()
        self._source.start()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"scan-{self._dev_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10.0)
        self._source.stop()
        self._audio.close()

    # ── private ────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        log.info("[%s] Scan loop started — %.3f MHz center, %d channels",
                 self._dev_id, self.center_freq / 1e6, len(self.channels))
        last_heartbeat = time.monotonic()

        while not self._stop.is_set():
            block = self._source.get_block(timeout=1.0)
            if block is None:
                continue

            self._process_block(block)

            now = time.monotonic()
            if self._locked_ch is None and now - last_heartbeat >= _HEARTBEAT_S:
                log.info("[%s] Scanning… (no activity)", self._dev_id)
                last_heartbeat = now

        log.info("[%s] Scan loop stopped", self._dev_id)

    def _process_block(self, block: np.ndarray) -> None:
        now = time.monotonic()

        # ── 1. FFT detection ───────────────────────────────────────────────────
        active_set = set(self._fft.process(block))

        # ── 2. Update per-channel state machines ──────────────────────────────
        for cs in self._states:
            changed = cs.update(cs.idx in active_set, now)
            if changed:
                log.info("[%s] %-30s  %s", self._dev_id, cs.name, cs.state.value.upper())

        # ── 3. Channel selection ───────────────────────────────────────────────
        if self._locked_ch is not None:
            if not self._states[self._locked_ch].is_receiving:
                log.info("[%s] Released %s", self._dev_id,
                         self.channels[self._locked_ch].name)
                self._locked_ch = None
                self._demod.reset()

        if self._locked_ch is None and active_set:
            snrs = self._fft.channel_snrs()
            best = max(active_set, key=lambda i: snrs[i])
            self._locked_ch = best
            log.info("[%s] Locked → %-30s  SNR %.1f dB",
                     self._dev_id, self.channels[best].name, snrs[best])

        # ── 4. Demodulate ──────────────────────────────────────────────────────
        if self._locked_ch is not None:
            ch = self.channels[self._locked_ch]
            offset = ch.freq_hz - self.center_freq
            baseband = _shift_to_baseband(block, offset, self.sample_rate)
            audio = self._demod.demodulate(baseband)
        else:
            # Feed silence while scanning so the aplay process stays warm
            n_audio = round(len(block) / self.sample_rate * AUDIO_RATE)
            audio = np.zeros(n_audio, dtype=np.float32)

        self._audio.write(audio)
