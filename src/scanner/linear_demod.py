"""
Linear-mode demodulator for HF — AM, USB, LSB and CW — baseband IQ → float32 audio.

Used for the HAM/shortwave dongle (NooElec SMArt XTR + Ham It Up upconverter).
The NFM chain in nfm_demod.py doesn't apply: SSB/CW carry no FM, and AM
broadcast needs an envelope detector.

Signal chain
------------
IQ (fs = 2.048 MS/s, dial frequency already shifted to 0 Hz by the caller)
  → LPF 16 kHz, ÷16                       → 128 kS/s
  → LPF 5 kHz,  ÷4                        →  32 kS/s
  → mode detector at 32 kS/s:
      USB/LSB  complex band-pass on one side of 0 Hz, take real part
      CW       shift carrier to +BFO (700 Hz tone), narrow band-pass, real part
      AM       envelope |x|, DC removed
  → AGC (SSB/CW/AM levels vary by 60+ dB on HF)
  → ×3/2 polyphase resample                →  48 kHz

Every filter keeps state across calls, and block sizes divide evenly by
the decimation factors, so consecutive blocks join without clicks — needed for
SSB, where a phase jump every block would be heard as a ~60 Hz buzz.
"""
import logging

import numpy as np
from scipy import signal as ss

from src.scanner.dsp import Mixer

log = logging.getLogger(__name__)

AUDIO_RATE = 48_000
_D1, _D2 = 16, 4               # 2.048 MS/s → 128 kS/s → 32 kS/s
_UP, _DOWN = 3, 2              # 32 kS/s → 48 kS/s

CW_TONE_HZ = 700.0

# Audio passband relative to the dial frequency, after any BFO shift.
_PASSBAND = {
    "usb": (300.0, 2_800.0),
    "lsb": (-2_800.0, -300.0),
    "cw":  (CW_TONE_HZ - 250.0, CW_TONE_HZ + 250.0),
}

# Where the signal's energy sits relative to the dial frequency, and how wide —
# used by the FFT detector (fft_engine.Channel.detect_offset_hz / bandwidth_hz).
DETECT_WINDOW = {
    "usb": (1_550.0, 2_500.0),
    "lsb": (-1_550.0, 2_500.0),
    "cw":  (0.0, 500.0),
    # Carrier only (±1 kHz): broadcasters sit on a 5 kHz raster, and an 8 kHz
    # window would also trigger on a neighbour's sidebands.
    "am":  (0.0, 2_000.0),
}

LINEAR_MODES = frozenset(DETECT_WINDOW)


class _StatefulFIR:
    """FIR filter that carries state between blocks."""

    def __init__(self, taps: np.ndarray, complex_input: bool):
        self.taps = taps
        dtype = np.complex64 if complex_input else np.float32
        self._zi_init = np.zeros(len(taps) - 1, dtype=dtype)
        self.zi = self._zi_init.copy()

    def __call__(self, x: np.ndarray) -> np.ndarray:
        y, self.zi = ss.lfilter(self.taps, [1.0], x, zi=self.zi)
        return y

    def reset(self) -> None:
        self.zi = self._zi_init.copy()


class _DecimatingFIR:
    """
    FIR + keep-every-Dth-sample, computing only the kept outputs.

    Same result as _StatefulFIR(x)[::D] for blocks whose length is a multiple
    of D, at 1/D of the cost — the first stage runs at the full 2 MS/s, where
    filtering every sample and discarding 15 of 16 dominated the CPU budget.
    """

    def __init__(self, taps: np.ndarray, decim: int):
        self._rev = taps[::-1].astype(np.complex64)
        self._d = decim
        self._hist = np.zeros(len(taps) - 1, dtype=np.complex64)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        xx = np.concatenate([self._hist, x.astype(np.complex64)])
        self._hist = xx[len(xx) - len(self._hist):]
        win = np.lib.stride_tricks.sliding_window_view(xx, len(self._rev))[::self._d]
        return win @ self._rev

    def reset(self) -> None:
        self._hist[:] = 0


class _AGC:
    """Block AGC: fast attack, slow decay, gain ramped across each block."""

    def __init__(self, rate: float, target: float = 0.3,
                 decay_s: float = 1.5, max_gain: float = 1e5):
        self._target = target
        self._decay_per_sample = np.exp(-1.0 / (decay_s * rate))
        self._max_gain = max_gain
        self.reset()

    def __call__(self, x: np.ndarray) -> np.ndarray:
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        decay = self._decay_per_sample ** len(x)
        self._level = peak if peak > self._level else self._level * decay + peak * (1 - decay)
        new_gain = min(self._target / max(self._level, 1e-12), self._max_gain)
        ramp = np.linspace(self._gain, new_gain, len(x), dtype=np.float32)
        self._gain = new_gain
        return x * ramp

    def reset(self) -> None:
        self._level = 0.0
        self._gain = 1.0


class LinearDemodulator:
    def __init__(self, sample_rate: float, mode: str, audio_rate: int = AUDIO_RATE):
        mode = mode.lower()
        if mode not in LINEAR_MODES:
            raise ValueError(f"Unsupported linear mode {mode!r} (expected one of {sorted(LINEAR_MODES)})")
        if audio_rate != AUDIO_RATE:
            raise ValueError("LinearDemodulator only produces 48 kHz audio")
        if round(sample_rate) % (_D1 * _D2):
            raise ValueError(f"sample_rate {sample_rate} must be a multiple of {_D1 * _D2}")

        self.mode = mode
        self.sample_rate = sample_rate
        self.audio_rate = audio_rate
        fs1 = sample_rate / _D1
        self._fs_dem = fs1 / _D2               # 32 kS/s at 2.048 MS/s

        self._lpf1 = _DecimatingFIR(ss.firwin(127, 16_000.0, fs=sample_rate), _D1)
        self._lpf2 = _DecimatingFIR(ss.firwin(127, 5_000.0, fs=fs1), _D2)

        if mode == "am":
            # DC blocker y[n] = x[n] − x[n−1] + R·y[n−1] removes the carrier level
            self._dc_b, self._dc_a = np.array([1.0, -1.0]), np.array([1.0, -0.995])
            self._dc_zi = np.zeros(1)
            self._band = None
        else:
            lo, hi = _PASSBAND[mode]
            centre, half = (lo + hi) / 2.0, (hi - lo) / 2.0
            lp = ss.firwin(255, half, fs=self._fs_dem)
            n = np.arange(len(lp)) - (len(lp) - 1) / 2.0
            band = (lp * np.exp(2j * np.pi * centre / self._fs_dem * n)).astype(np.complex64)
            self._band = _StatefulFIR(band, True)

        self._bfo = Mixer(-CW_TONE_HZ, self._fs_dem) if mode == "cw" else None
        self._agc = _AGC(self._fs_dem)

        # Polyphase ×3/2 resampler: zero-stuff ×3, low-pass, keep every 2nd
        self._rs = _StatefulFIR(
            (ss.firwin(96, 0.9 * self._fs_dem / 2.0, fs=self._fs_dem * _UP) * _UP).astype(np.float32),
            False)

        log.debug("LinearDemod %s: %.0f S/s → %.0f S/s → %d Hz",
                  mode, sample_rate, self._fs_dem, audio_rate)

    # ── public ─────────────────────────────────────────────────────────────────

    def demodulate(self, baseband_iq: np.ndarray) -> np.ndarray:
        if len(baseband_iq) % (_D1 * _D2):
            raise ValueError(f"block length must be a multiple of {_D1 * _D2}")
        x = self._lpf1(baseband_iq)
        x = self._lpf2(x)

        if self.mode == "am":
            env = np.abs(x).astype(np.float64)
            audio, self._dc_zi = ss.lfilter(self._dc_b, self._dc_a, env, zi=self._dc_zi)
            audio = audio.astype(np.float32)
        else:
            if self._bfo is not None:
                x = self._bfo.shift(x)          # carrier 0 Hz → +700 Hz
            audio = np.real(self._band(x)).astype(np.float32)

        audio = self._agc(audio)

        up = np.zeros(len(audio) * _UP, dtype=np.float32)
        up[::_UP] = audio
        out = self._rs(up)[::_DOWN]
        return np.clip(out, -1.0, 1.0).astype(np.float32)

    def reset(self) -> None:
        for f in (self._lpf1, self._lpf2, self._rs, self._band):
            if f is not None:
                f.reset()
        if self.mode == "am":
            self._dc_zi = np.zeros(1)
        if self._bfo is not None:
            self._bfo.reset()
        self._agc.reset()
