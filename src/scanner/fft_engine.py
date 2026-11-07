"""
FFT-based wideband spectrum analyzer for simultaneous channel activity detection.

One FFTEngine instance per dongle. Each call to process() averages multiple FFTs
across the IQ block, then detects channels whose power exceeds the adaptive noise
floor by THRESHOLD_DB.

Design notes
------------
* Noise floor is tracked in LINEAR power (not dB) to avoid the dB-averaging
  artefact where averaging 14 noise bins and 1 tone bin in dB space buries the
  tone.  Per-channel SNR is computed as 10·log10(sig_lin / floor_lin).

* Detection uses the noise floor from BEFORE the current block, then the floor
  is updated.  This prevents a strong narrowband tone from dragging the floor of
  adjacent (empty) bins to near-zero on its first block.

* Asymmetric ALPHA:  floor falls toward minimum faster than it rises.  The 10×
  ratio is empirically safe for chi-squared(2) FFT noise: the floor settles at
  ~70 % of the true noise mean, giving a quiet SNR of ~1.5 dB — well below the
  12 dB detection threshold.

* Bins with a signal in them (≥ hold_db above the floor) raise the floor only
  at hold_alpha, not ALPHA_UP. Without this the floor climbed into any steady
  carrier within ~0.3 s, so a long transmission (an FM voice call, a
  shortwave broadcast) dropped out of detection and was cut off ~3 s in.
  Defaults suit VHF voice: a held carrier is absorbed only after roughly a
  minute (so a constant spur on a channel doesn't record forever). The HF
  broadcast config uses hold_alpha=0 (stations held indefinitely) and a lower
  hold_db so a fading station doesn't let the floor creep up under it.

* The initial floor is a median-filtered copy of the first spectrum, so a
  station already on the air at startup isn't mistaken for noise.

* Holding signal bins needs a safety net: if the floor starts too low (e.g. the
  first block after tuning is near-silent while the tuner settles), every bin
  looks like signal and would be held there forever. So each block the floor
  is kept at or above FLOOR_GUARD × the local median of the current spectrum.
  A narrowband signal barely moves a 65-bin median, so it's still detected;
  a floor that's wrong by more than that gets pulled back up at once.
"""
import logging
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import median_filter

log = logging.getLogger(__name__)

FFT_SIZE = 2048
THRESHOLD_DB = 12.0    # dB above noise floor required for detection
ALPHA_DOWN = 0.05      # floor falls at this rate (toward minimum)
ALPHA_UP = 0.005       # floor rises at this rate (slow so signals don't raise it)
HOLD_ALPHA_DEFAULT = 2e-5   # ~40–60 s to absorb a 25–30 dB steady carrier
_MEDIAN_BINS = 65      # local-median width for floor init/guard (~65 kHz at 2 MS/s)
FLOOR_GUARD = 0.4      # floor never below this × local median (quiet floor ≈ 0.7×)


@dataclass
class Channel:
    name: str
    freq_hz: float
    bandwidth_hz: float = 15_000   # half-power bandwidth used for averaging
    mode: str = "nfm"              # nfm | am | usb | lsb | cw — selects the demodulator
    # Where the signal's energy sits relative to freq_hz. Non-zero for SSB:
    # a USB voice signal occupies freq..freq+2.8 kHz, not a window centred on freq.
    detect_offset_hz: float = 0.0


class FFTEngine:
    def __init__(self, center_freq: float, sample_rate: float, channels: list[Channel],
                 hold_db: float = THRESHOLD_DB, hold_alpha: float = HOLD_ALPHA_DEFAULT):
        self._hold_lin = 10.0 ** (hold_db / 10.0)
        self._hold_alpha = hold_alpha
        self.center_freq = center_freq
        self.sample_rate = sample_rate
        self.channels = channels

        bin_width = sample_rate / FFT_SIZE
        self._window = np.hanning(FFT_SIZE).astype(np.float32)
        self._noise_floor_lin: np.ndarray | None = None   # shape (FFT_SIZE,), linear power
        self._last_snrs: list[float] = [0.0] * len(channels)

        # Pre-compute bin slice for each channel
        self._ch_slices: list[tuple[int, int]] = []
        for ch in channels:
            offset = ch.freq_hz + ch.detect_offset_hz - center_freq
            center_bin = FFT_SIZE // 2 + int(round(offset / bin_width))
            half = max(1, int(ch.bandwidth_hz / 2 / bin_width))
            lo = max(0, center_bin - half)
            hi = min(FFT_SIZE, center_bin + half + 1)
            self._ch_slices.append((lo, hi))
            log.debug("Channel %-30s  bins %d–%d  (%.3f MHz)",
                      ch.name, lo, hi, ch.freq_hz / 1e6)

    # ── public ─────────────────────────────────────────────────────────────────

    def process(self, iq_block: np.ndarray) -> list[int]:
        """
        Compute power spectrum from one IQ block and return active channel indices.
        Detection uses the noise floor from PREVIOUS blocks; the floor is then
        updated with this block's spectrum.
        """
        power_lin = self._mean_spectrum_lin(iq_block)

        # ── Detect using the PREVIOUS floor estimate ───────────────────────────
        active: list[int] = []
        if self._noise_floor_lin is not None:
            for idx, (lo, hi) in enumerate(self._ch_slices):
                sig   = float(np.mean(power_lin[lo:hi]))
                noise = float(np.mean(self._noise_floor_lin[lo:hi]))
                snr   = 10.0 * np.log10((sig + 1e-30) / (noise + 1e-30))
                self._last_snrs[idx] = snr
                if snr >= THRESHOLD_DB:
                    active.append(idx)

        # ── Update floor AFTER detection ───────────────────────────────────────
        self._update_floor(power_lin)

        return active

    def channel_snrs(self) -> list[float]:
        """Per-channel SNR (dB above noise floor) from the most recent process() call."""
        return list(self._last_snrs)

    # ── private ────────────────────────────────────────────────────────────────

    def _mean_spectrum_lin(self, iq_block: np.ndarray) -> np.ndarray:
        """Average |FFT|² (linear power) over all complete FFT_SIZE chunks."""
        n = len(iq_block)
        n_fft = max(1, n // FFT_SIZE)
        acc = np.zeros(FFT_SIZE, dtype=np.float64)

        for i in range(n_fft):
            chunk = iq_block[i * FFT_SIZE: (i + 1) * FFT_SIZE]
            if len(chunk) < FFT_SIZE:
                break
            spec = np.abs(np.fft.fftshift(np.fft.fft(chunk * self._window))) ** 2
            acc += spec

        return (acc / n_fft).astype(np.float32)

    def _update_floor(self, power_lin: np.ndarray) -> None:
        local = median_filter(power_lin, _MEDIAN_BINS, mode="nearest")
        if self._noise_floor_lin is None:
            self._noise_floor_lin = np.minimum(power_lin, local)
            return

        floor = self._noise_floor_lin
        diff = power_lin - floor
        alpha = np.where(diff > 0, ALPHA_UP, ALPHA_DOWN)
        alpha[power_lin >= floor * self._hold_lin] = self._hold_alpha   # signal: hold
        floor = floor + alpha * diff
        self._noise_floor_lin = np.maximum(floor, FLOOR_GUARD * local).astype(np.float32)
