"""
Narrowband FM demodulator — processes baseband complex IQ → float32 audio.

Signal chain
------------
IQ (fs = sample_rate)
  → channel isolation LPF + decimate ÷d1   → fs_mid  (~256 kS/s)
  → FM discriminator  angle(conj(x[n-1])·x[n])
  → de-emphasis IIR  (τ = 75 µs, US standard)
  → audio LPF (4 kHz voice bandwidth)
  → resample_poly(up, down)               → 48 000 Hz
  → float32 [-1, 1]

The caller is responsible for shifting the desired channel to 0 Hz (baseband)
before calling demodulate(). See scan_loop._shift_to_baseband().
"""
import logging
from math import gcd

import numpy as np
from scipy import signal as ss

log = logging.getLogger(__name__)

AUDIO_RATE = 48_000
NFM_DEVIATION_HZ = 5_000   # peak deviation for narrowband FM


class NFMDemodulator:
    def __init__(self, sample_rate: float, audio_rate: int = AUDIO_RATE):
        self.sample_rate = sample_rate
        self.audio_rate = audio_rate

        # ── Stage 1: decimate to intermediate rate ─────────────────────────────
        # Choose d1 as the largest power-of-2 that keeps fs_mid ≥ 4 * audio_rate
        d1 = 1
        while sample_rate / (d1 * 2) >= audio_rate * 4:
            d1 *= 2
        self._d1 = d1
        self._fs_mid = sample_rate / d1   # e.g. 256 000 Hz for 2.048 MS/s ÷ 8

        # Channel isolation LPF (pre-decimation, cutoff 12.5 kHz)
        cutoff_norm = 12_500.0 / (sample_rate / 2.0)
        self._lpf_taps = ss.firwin(127, cutoff_norm).astype(np.float32)
        self._lpf_zi = np.zeros(len(self._lpf_taps) - 1, dtype=np.complex64)

        # ── FM discriminator state ─────────────────────────────────────────────
        self._prev = np.complex64(0.0)

        # Gain after discriminator: convert radians/sample → normalised audio
        # discriminator output is angle in [-π, π]; peak for max_dev is:
        #   max_rad = 2π * max_dev / fs_mid
        self._disc_gain = float(self._fs_mid) / (2.0 * np.pi * NFM_DEVIATION_HZ)

        # ── De-emphasis IIR (τ = 75 µs, bilinear transform) ───────────────────
        b_s = np.array([1.0])
        a_s = np.array([75e-6, 1.0])   # H(s) = 1 / (τs + 1)
        self._deemph_b, self._deemph_a = ss.bilinear(b_s, a_s, fs=self._fs_mid)
        self._deemph_zi = ss.lfilter_zi(self._deemph_b, self._deemph_a).astype(np.float32)

        # ── Audio LPF (cutoff 4 kHz) ───────────────────────────────────────────
        audio_cutoff = 4_000.0 / (self._fs_mid / 2.0)
        self._audio_taps = ss.firwin(63, audio_cutoff).astype(np.float32)
        self._audio_zi = ss.lfilter_zi(self._audio_taps, [1.0]).astype(np.float32)

        # ── Resample ratio: fs_mid → audio_rate ───────────────────────────────
        fs_mid_int = int(self._fs_mid)
        g = gcd(fs_mid_int, audio_rate)
        self._up = audio_rate // g
        self._down = fs_mid_int // g

        log.debug("NFMDemod: %.0f S/s → ÷%d → %.0f S/s → resample %d/%d → %d Hz",
                  sample_rate, d1, self._fs_mid, self._up, self._down, audio_rate)

    # ── public ─────────────────────────────────────────────────────────────────

    def demodulate(self, baseband_iq: np.ndarray) -> np.ndarray:
        """
        Demodulate baseband complex IQ → float32 audio samples at audio_rate.
        Maintains filter state across consecutive calls for seamless audio.
        """
        # 1. Channel isolation LPF (complex input, real taps → applied to each component)
        filtered, self._lpf_zi = ss.lfilter(self._lpf_taps, [1.0],
                                              baseband_iq, zi=self._lpf_zi)
        # 2. Decimate
        decimated = filtered[::self._d1].astype(np.complex64)

        # 3. FM discriminator: angle(conj(x[n-1]) * x[n])
        prev_col = np.empty_like(decimated)
        prev_col[0] = self._prev
        prev_col[1:] = decimated[:-1]
        self._prev = decimated[-1]

        disc = np.angle(np.conj(prev_col) * decimated).astype(np.float32)
        disc *= self._disc_gain

        # 4. De-emphasis
        disc, self._deemph_zi = ss.lfilter(self._deemph_b, self._deemph_a,
                                             disc, zi=self._deemph_zi)

        # 5. Audio LPF
        disc, self._audio_zi = ss.lfilter(self._audio_taps, [1.0],
                                            disc, zi=self._audio_zi)

        # 6. Resample to audio_rate
        audio = ss.resample_poly(disc, self._up, self._down)

        return np.clip(audio, -1.0, 1.0).astype(np.float32)

    def reset(self) -> None:
        """Reset all filter state. Call when switching to a new channel."""
        self._lpf_zi[:] = 0.0
        self._prev = np.complex64(0.0)
        self._deemph_zi = ss.lfilter_zi(self._deemph_b, self._deemph_a).astype(np.float32)
        self._audio_zi = ss.lfilter_zi(self._audio_taps, [1.0]).astype(np.float32)
