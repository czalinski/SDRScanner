"""
Per-device recording loop.

Monitors all channels on one dongle simultaneously via wideband FFT.
Each active channel is demodulated independently — NFM for VHF voice, or
AM/USB/LSB/CW for HF (see linear_demod.py). When a transmission ends
(TAIL → IDLE), the accumulated audio is written to a WAV file whose name
encodes all metadata (timestamp, device, channel, frequency). Transmissions
longer than max_segment_s (e.g. a continuous shortwave broadcast) are split
into consecutive files so playback isn't held up until the station signs off.

Channel frequencies are always the frequency on the air ("dial" frequency).
With an upconverter (Ham It Up: HF + 125 MHz), lo_offset_hz is added only
when tuning the dongle.
"""
import logging
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from src.scanner.channel_state import ChannelState, State
from src.scanner.dsp import Mixer
from src.scanner.fft_engine import Channel, FFTEngine
from src.scanner.iq_source import IQSource
from src.scanner.linear_demod import LINEAR_MODES, LinearDemodulator
from src.scanner.nfm_demod import AUDIO_RATE, NFMDemodulator

log = logging.getLogger(__name__)

_HEARTBEAT_S = 30.0


def _shift_to_baseband(iq: np.ndarray, offset_hz: float, sample_rate: float) -> np.ndarray:
    n = np.arange(len(iq), dtype=np.float64)
    return iq * np.exp(-2j * np.pi * offset_hz / sample_rate * n).astype(np.complex64)


def make_demodulator(mode: str, sample_rate: float):
    mode = mode.lower()
    if mode == "nfm":
        return NFMDemodulator(sample_rate)
    if mode in LINEAR_MODES:
        return LinearDemodulator(sample_rate, mode)
    raise ValueError(f"Unknown mode {mode!r}")


class Recorder:
    """
    Captures all channel activity on one SDR dongle, writing a WAV file
    per transmission to recordings_dir/YYYYMMDD/.
    """

    def __init__(self, dev_id: str, serial: str, center_freq: float,
                 sample_rate: float, channels: list[Channel],
                 recordings_dir: str | Path,
                 gain: float | None = None, ppm: int = 0,
                 lo_offset_hz: float = 0.0,
                 max_segment_s: float | None = None,
                 max_active_channels: int | None = None,
                 detector: dict | None = None):
        self._dev_id = dev_id
        self._center_freq = center_freq
        self._sample_rate = sample_rate
        self._channels = channels
        self._recordings_dir = Path(recordings_dir)
        self._max_segment_samples = (int(max_segment_s * AUDIO_RATE)
                                     if max_segment_s else None)
        # Record at most this many channels at once. A channel already being
        # recorded keeps its slot until it goes idle; free slots go to the
        # highest-SNR active channels. 1 = "radio" behaviour for broadcast:
        # stay on one station rather than chopping between all of them.
        self._max_active = max_active_channels

        self._source = IQSource(serial, center_freq + lo_offset_hz, sample_rate, gain, ppm)
        self._fft = FFTEngine(center_freq, sample_rate, channels, **(detector or {}))
        self._demods = [make_demodulator(ch.mode, sample_rate) for ch in channels]
        self._mixers = [Mixer(ch.freq_hz - center_freq, sample_rate) for ch in channels]
        self._buffered = [0] * len(channels)
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

            changed_idx = set()
            for idx in range(len(self._channels)):
                if self._states[idx].update(idx in active_set, now):
                    changed_idx.add(idx)
            recording = self._select_recording()

            for idx, ch in enumerate(self._channels):
                was_receiving = self._tx_start[idx] is not None
                is_receiving = idx in recording

                if idx in changed_idx and (is_receiving or was_receiving):
                    # Start/end at INFO; ACTIVE↔TAIL flicker (a fading HF
                    # station, a choppy mobile) only at DEBUG.
                    st = self._states[idx].state
                    starting = st is State.ACTIVE and not was_receiving
                    level = logging.INFO if (starting or st is State.IDLE) else logging.DEBUG
                    log.log(level, "[%s] %-30s  %s", self._dev_id, ch.name, st.value.upper())

                if is_receiving:
                    any_active = True
                    if self._tx_start[idx] is None:
                        self._tx_start[idx] = time.time()
                    bb = self._mixers[idx].shift(iq)
                    audio = self._demods[idx].demodulate(bb)
                    self._buffers[idx].append(audio)
                    self._buffered[idx] += len(audio)
                    if (self._max_segment_samples
                            and self._buffered[idx] >= self._max_segment_samples):
                        # Split a long transmission; keep demod state so the
                        # next segment continues seamlessly.
                        self._flush(idx, ch, reset_demod=False)
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

    def _select_recording(self) -> set[int]:
        receiving = [i for i, st in enumerate(self._states) if st.is_receiving]
        if self._max_active is None:
            return set(receiving)
        # Channels already recording keep their slot through TAIL; a free slot
        # only goes to a channel whose signal is present now (ACTIVE) — one
        # already in TAIL would just record a fragment of silence.
        keep = [i for i in receiving if self._tx_start[i] is not None][: self._max_active]
        snrs = self._fft.channel_snrs()
        new = sorted((i for i in receiving
                      if i not in keep and self._states[i].state is State.ACTIVE),
                     key=lambda i: -snrs[i])
        return set(keep + new[: self._max_active - len(keep)])

    def _flush(self, idx: int, ch: Channel, reset_demod: bool = True) -> None:
        if not self._buffers[idx]:
            return

        audio = np.concatenate(self._buffers[idx])
        duration_s = len(audio) / AUDIO_RATE

        now = datetime.now()
        day_dir = self._recordings_dir / now.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        safe_name = ch.name.replace("/", "_").replace(" ", "_")
        freq_khz = int(round(ch.freq_hz / 1000))
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
        self._buffered[idx] = 0
        if reset_demod:
            self._tx_start[idx] = None
            self._demods[idx].reset()
