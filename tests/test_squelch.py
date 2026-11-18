"""NFM noise-squelch checks — the hiss after a marine/railroad transmission
ends must be silenced and trimmed. No hardware required.

Run: python3 tests/test_squelch.py
"""
import sys

sys.path.insert(0, ".")

import numpy as np

from src.scanner.nfm_demod import AUDIO_RATE, NFMDemodulator
from src.scanner.recorder import _apply_squelch

FS = 2_048_000
BLOCK = 32768
rng = np.random.default_rng(1)


def fm_iq(n_blocks: int, cnr_db: float | None) -> np.ndarray:
    """FM voice-like signal at the given in-channel CNR; None = noise only."""
    t = np.arange(BLOCK * n_blocks) / FS
    # Unit carrier; white-noise power scaled so CNR is measured in a 25 kHz channel
    noise_pow = (FS / 25_000) * 10 ** (-(cnr_db or 0) / 10)
    noise = np.sqrt(noise_pow / 2) * (rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t)))
    if cnr_db is None:
        return noise.astype(np.complex64)
    msg = 0.6 * np.sin(2 * np.pi * 800 * t) + 0.3 * np.sin(2 * np.pi * 1900 * t)
    return (np.exp(2j * np.pi * 5000 * np.cumsum(msg) / FS) + noise).astype(np.complex64)


def run(iq: np.ndarray) -> tuple[list[np.ndarray], list[bool]]:
    d = NFMDemodulator(FS)
    chunks, gate = [], []
    for b in range(len(iq) // BLOCK):
        chunks.append(d.demodulate(iq[b * BLOCK:(b + 1) * BLOCK]))
        gate.append(d.squelch_open)
    return chunks, gate


def test_noise_only_discarded():
    chunks, gate = run(fm_iq(30, None))
    assert not any(gate), "squelch opened on pure noise"
    assert _apply_squelch(chunks, gate) is None


def test_strong_signal_open():
    _, gate = run(fm_iq(30, 20))
    assert all(gate[2:]), f"squelch closed on a 20 dB signal: {gate}"


def test_tail_trimmed():
    # 0.5 s noise, 1 s voice, 3 s noise tail — the reported problem.
    iq = np.concatenate([fm_iq(31, None), fm_iq(62, 15), fm_iq(188, None)])
    chunks, gate = run(iq)
    out = _apply_squelch(chunks, gate)
    voice_s = 62 * BLOCK / FS
    dur = len(out) / AUDIO_RATE
    assert abs(dur - voice_s) < 0.1, f"kept {dur:.2f}s, expected ~{voice_s:.2f}s"
    assert np.abs(out[-10:]).max() < 0.05, "no fade-out at the end"


def test_mid_gap_silenced_not_cut():
    gate = [True, False, False, True]
    chunks = [np.ones(768, np.float32)] * 4
    out = _apply_squelch(chunks, gate)
    assert len(out) == 4 * 768
    assert not out[768:3 * 768].any()


def test_short_clip_discarded():
    import tempfile
    from pathlib import Path
    from src.scanner.fft_engine import Channel
    from src.scanner.recorder import Recorder
    with tempfile.TemporaryDirectory() as tmp:
        ch = Channel("Ch 16", 156.8e6)
        rec = Recorder("marine", "FAKE", 156.75e6, FS, [ch], tmp)
        for seconds, n_files in ((0.5, 0), (1.5, 1)):
            n = int(seconds * AUDIO_RATE / 768)
            rec._buffers[0] = [np.full(768, 0.1, np.float32)] * n
            rec._gates[0] = [True] * n
            rec._buffered[0] = 768 * n
            rec._flush(0, ch)
            got = len(list(Path(tmp).rglob("*.wav")))
            assert got == n_files, (seconds, got)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
