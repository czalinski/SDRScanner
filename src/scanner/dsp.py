"""Small shared DSP helpers."""
import numpy as np

_TWO_PI = 2.0 * np.pi


class Mixer:
    """
    Phase-continuous frequency shifter: shift(x) moves `offset_hz` to 0 Hz.

    The phase carries over between calls, so consecutive IQ blocks join
    seamlessly. Restarting the oscillator at phase 0 on each block (as
    recorder._shift_to_baseband does) puts a phase step at every block
    boundary — tolerable for FM, an audible buzz for SSB/CW.
    """

    def __init__(self, offset_hz: float, sample_rate: float):
        self._w = _TWO_PI * offset_hz / sample_rate
        self._phase = 0.0

    def shift(self, x: np.ndarray) -> np.ndarray:
        n = np.arange(len(x), dtype=np.float64)
        osc = np.exp(-1j * (self._phase + self._w * n)).astype(np.complex64)
        self._phase = (self._phase + self._w * len(x)) % _TWO_PI
        return x * osc

    def reset(self) -> None:
        self._phase = 0.0
