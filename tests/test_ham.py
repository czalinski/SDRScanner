"""HF/HAM checks — linear demodulator, mixer, playback priority, recorder
segments and upconverter offset. No hardware required.

Run: python3 tests/test_ham.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np

from src.scanner.dsp import Mixer
from src.scanner.fft_engine import Channel, FFTEngine
from src.scanner.linear_demod import AUDIO_RATE, CW_TONE_HZ, LinearDemodulator
from src.scanner.main import _build_channels, _check_window
from src.scanner.playback_queue import PlaybackQueue, device_id_from_filename
from src.scanner.recorder import Recorder

FS = 2.048e6
BLOCK = 32768
N_BLOCKS = 40                     # ~0.64 s
rng = np.random.default_rng(1)


def blocks(sig_fn, n_blocks=N_BLOCKS, noise=1e-4):
    """Yield consecutive IQ blocks of sig_fn(t) with continuous time."""
    for b in range(n_blocks):
        t = (np.arange(BLOCK) + b * BLOCK) / FS
        x = sig_fn(t) + noise * (rng.standard_normal(BLOCK) + 1j * rng.standard_normal(BLOCK))
        yield x.astype(np.complex64)


def run(demod, sig_fn, mixer=None):
    out = []
    for x in blocks(sig_fn):
        if mixer is not None:
            x = mixer.shift(x)
        out.append(demod.demodulate(x))
    audio = np.concatenate(out)
    return audio[len(audio) // 4:]          # skip AGC / filter settling


def tone_stats(audio, f):
    """(peak frequency, dB of energy at f relative to everything else)."""
    w = np.hanning(len(audio))
    spec = np.abs(np.fft.rfft(audio * w)) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1 / AUDIO_RATE)
    peak = freqs[np.argmax(spec)]
    band = np.abs(freqs - f) < 40
    sig, rest = spec[band].sum(), spec[~band].sum()
    return peak, 10 * np.log10(sig / (rest + 1e-30)), float(np.sqrt(np.mean(audio ** 2)))


def tone(f_hz, amp=0.05):
    return lambda t: amp * np.exp(2j * np.pi * f_hz * t)


# ── Decimating FIR equals filter-then-slice, across block boundaries ─────────
from scipy import signal as ss
from src.scanner.linear_demod import _DecimatingFIR
taps = ss.firwin(127, 16_000.0, fs=FS)
sig = (rng.standard_normal(4 * BLOCK) + 1j * rng.standard_normal(4 * BLOCK)).astype(np.complex64)
ref = ss.lfilter(taps, [1.0], sig)[::16]
dec = _DecimatingFIR(taps, 16)
got = np.concatenate([dec(sig[i:i + BLOCK]) for i in range(0, len(sig), BLOCK)])
assert np.allclose(got, ref, atol=1e-4), np.max(np.abs(got - ref))
print("  decimating FIR matches lfilter: OK")

# ── Output length matches the NFM path (768 samples / 16 ms block) ────────────
d = LinearDemodulator(FS, "usb")
assert len(d.demodulate(np.zeros(BLOCK, np.complex64))) == round(BLOCK / FS * AUDIO_RATE)
print("  output length: OK")

# ── USB: tone 1 kHz above dial → clean 1 kHz audio, LSB rejects it ───────────
peak, purity, usb_rms = tone_stats(run(LinearDemodulator(FS, "usb"), tone(1000)), 1000)
print(f"  USB +1 kHz tone: peak {peak:.0f} Hz, purity {purity:.1f} dB, rms {usb_rms:.3f}")
assert abs(peak - 1000) < 20 and purity > 25, "USB should give a clean 1 kHz tone"

# ── LSB: tone 1 kHz below dial → 1 kHz audio ─────────────────────────────────
peak, purity, _ = tone_stats(run(LinearDemodulator(FS, "lsb"), tone(-1000)), 1000)
print(f"  LSB −1 kHz tone: peak {peak:.0f} Hz, purity {purity:.1f} dB")
assert abs(peak - 1000) < 20 and purity > 25

# Sideband rejection: with no AGC the wrong-side tone would come out at the
# same level; check the band-pass itself attenuates it (AGC bypassed).
for mode, f in (("usb", -1000), ("lsb", 1000)):
    dm = LinearDemodulator(FS, mode)
    dm._agc = lambda x: x
    right = LinearDemodulator(FS, mode)
    right._agc = lambda x: x
    wrong_rms = tone_stats(run(dm, tone(f)), 1000)[2]
    right_rms = tone_stats(run(right, tone(-f)), 1000)[2]
    rej = 20 * np.log10(right_rms / max(wrong_rms, 1e-12))
    print(f"  {mode.upper()} opposite-sideband rejection: {rej:.0f} dB")
    assert rej > 30

# ── CW: carrier exactly on dial → 700 Hz beat note ──────────────────────────
peak, purity, _ = tone_stats(run(LinearDemodulator(FS, "cw"), tone(0)), CW_TONE_HZ)
print(f"  CW carrier: peak {peak:.0f} Hz, purity {purity:.1f} dB")
assert abs(peak - CW_TONE_HZ) < 20 and purity > 25

# ── AM: carrier with 30 % 1 kHz modulation → 1 kHz audio ─────────────────────
am = lambda t: 0.05 * (1 + 0.3 * np.cos(2 * np.pi * 1000 * t)) * np.exp(2j * np.pi * 200 * t)
peak, purity, _ = tone_stats(run(LinearDemodulator(FS, "am"), am), 1000)
print(f"  AM 1 kHz modulation: peak {peak:.0f} Hz, purity {purity:.1f} dB")
assert abs(peak - 1000) < 20 and purity > 25

# ── AGC: a 40 dB weaker signal comes out at a similar level ──────────────────
_, _, weak_rms = tone_stats(run(LinearDemodulator(FS, "usb"), tone(1000, amp=0.0005)), 1000)
print(f"  AGC: strong rms {usb_rms:.3f}, 40 dB weaker rms {weak_rms:.3f}")
assert 0.5 < weak_rms / usb_rms < 2.0

# ── Mixer is phase-continuous across blocks (no per-block buzz) ──────────────
# Signal at +250 kHz + 1 kHz, mixed down by 250 kHz in 16 ms blocks → 1 kHz USB.
peak, purity, _ = tone_stats(run(LinearDemodulator(FS, "usb"), tone(251_000), Mixer(250_000, FS)), 1000)
print(f"  Mixer + USB across blocks: peak {peak:.0f} Hz, purity {purity:.1f} dB")
assert abs(peak - 1000) < 20 and purity > 25

# ── FFT detection uses the SSB energy window, not the dial frequency ─────────
ch = Channel("40m test", 7.250e6, bandwidth_hz=2500, mode="lsb", detect_offset_hz=-1550)
fft = FFTEngine(7.40e6, FS, [ch])
quiet = lambda t: 0 * t
for x in blocks(quiet, 20, noise=0.01):
    fft.process(x)
voice = lambda t: 0.05 * np.exp(2j * np.pi * (7.250e6 - 1500 - 7.40e6) * t)
hits = [fft.process(x) for x in blocks(voice, 3, noise=0.01)]
assert [0] in hits, f"LSB energy below dial should be detected, got {hits}"
print("  FFT LSB detection window: OK")

# ── FFT detector holds a long carrier, and sees one already on at startup ────
from src.scanner.channel_state import ChannelState
def carrier_run(prime_quiet: bool, seconds=10.0):
    f = FFTEngine(161e6, FS, [Channel("c", 160.47e6)])    # VHF defaults
    cs = ChannelState(0, "c")
    car = lambda t: 0.3 * np.exp(2j * np.pi * (160.47e6 - 161e6) * t)
    if prime_quiet:
        for x in blocks(lambda t: 0 * t, 50, noise=0.01):
            f.process(x)
    n = int(seconds / (BLOCK / FS))
    states = []
    for b, x in enumerate(blocks(car, n, noise=0.01)):
        cs.update(0 in f.process(x), b * BLOCK / FS)
        states.append(cs.state.value)
    return states
st = carrier_run(prime_quiet=True)
assert all(s == "active" for s in st[1:]), f"carrier dropped: {sorted(set(st))}"
st = carrier_run(prime_quiet=False)      # station on air when the scanner starts
assert all(s == "active" for s in st[2:]), f"startup carrier missed: {sorted(set(st))}"
print("  FFT holds a 10 s carrier, incl. one present at startup: OK")

# Near-silent first block (tuner settling) must not leave every slot "active"
f = FFTEngine(14.55e6, FS, [Channel(f"s{i}", 13.7e6 + i * 5e3, bandwidth_hz=2000) for i in range(20)])
f.process(np.full(BLOCK, 1e-7, np.complex64))
for x in blocks(lambda t: 0 * t, 30, noise=0.01):
    act = f.process(x)
assert act == [], f"floor did not recover from a silent first block: {len(act)} active"
print("  FFT recovers from a near-silent first block: OK")

# ── Config: ham.yaml bands load and fit their windows ────────────────────────
from src.scanner.band_schedule import BandSwitcher, band_channels, is_daytime, sun_elevation_deg
from src.scanner.config_loader import load_channel_config
from src.scanner.linear_demod import DETECT_WINDOW
cfg = load_channel_config("ham")
for band in cfg["bands"]:
    chans = band_channels(band, cfg["default_mode"], DETECT_WINDOW)
    kept = _check_window("ham", band["center_mhz"] * 1e6, FS, chans)
    assert len(kept) == len(chans) > 20, (band["name"], len(kept), len(chans))
    assert all(c.mode == "am" for c in chans)
    assert all(abs(c.freq_hz - band["center_mhz"] * 1e6) > 10e3 for c in chans), "slot on DC spike"
    print(f"  {band['when']} band {band['name']}: {len(chans)} slots, all in window: OK")
out = _check_window("ham", 7.40e6, FS, [Channel("far", 14.2e6, mode="usb")])
assert out == []

# ── Sun elevation sanity (Tacoma 47.27 N, 122.44 W) ──────────────────────────
from datetime import datetime, timezone
LAT, LON = 47.2672, -122.44
ts = lambda *a: datetime(*a, tzinfo=timezone.utc).timestamp()
noon_june = sun_elevation_deg(LAT, LON, ts(2026, 6, 21, 20, 10))     # ~13:10 PDT
noon_dec = sun_elevation_deg(LAT, LON, ts(2026, 12, 21, 20, 10))     # ~12:10 PST
midnight = sun_elevation_deg(LAT, LON, ts(2026, 11, 7, 8, 0))        # 00:00 PST
print(f"  sun: June noon {noon_june:.1f}°, Dec noon {noon_dec:.1f}°, Nov midnight {midnight:.1f}°")
assert 64 < noon_june < 68 and 17 < noon_dec < 21 and midnight < -30
# Tacoma sunset 2026-11-06 is ~16:40 PST (00:40 UTC Nov 7)
assert is_daytime(LAT, LON, 0.0, ts(2026, 11, 7, 0, 15))
assert not is_daytime(LAT, LON, 0.0, ts(2026, 11, 7, 1, 10))
dev = {"id": "ham", "serial": "FAKE", "sample_rate": 2048000}
sw = BandSwitcher(dev, cfg, LAT, LON, "/tmp", None, None)
assert sw.wanted_band(ts(2026, 11, 6, 20, 0)) == "day" and sw.wanted_band(ts(2026, 11, 7, 6, 0)) == "night"
print("  sun elevation + day/night band choice: OK")

# ── max_active_channels=1: strongest station wins, and keeps its slot ────────
with tempfile.TemporaryDirectory() as tmp:
    chs = [Channel(f"s{i}", 6.0e6 + i * 5e3, mode="am", bandwidth_hz=2000) for i in range(3)]
    rec = Recorder("ham", "FAKE", 6.75e6, FS, chs, tmp, max_active_channels=1)
    for st_ in rec._states:
        st_.update(True)
    rec._fft._last_snrs = [15.0, 30.0, 20.0]
    assert rec._select_recording() == {1}
    rec._tx_start[1] = time.time()                 # now recording s1
    rec._fft._last_snrs = [40.0, 18.0, 20.0]       # s0 gets stronger
    assert rec._select_recording() == {1}, "must not hop away from a station mid-programme"
    rec._states[1].state = rec._states[1].state.__class__.IDLE
    assert rec._select_recording() == {0}
    rec._tx_start[1] = None
    rec._states[0].state = rec._states[0].state.__class__.TAIL   # signal just gone
    rec._states[2].state = rec._states[2].state.__class__.IDLE
    assert rec._select_recording() == set(), "a TAIL channel must not get a new slot"
print("  max_active_channels selection: OK")

# ── HF detector settings hold a station through a fade ───────────────────────
f = FFTEngine(14.55e6, FS, [Channel("bc", 13.87e6, mode="am", bandwidth_hz=2000)],
              hold_db=6.0, hold_alpha=0.0)
off = 13.87e6 - 14.55e6
for x in blocks(lambda t: 0 * t, 30, noise=0.01):
    f.process(x)
seq = [0.3] * 60 + [0.035] * 300 + [0.3] * 60           # strong, ~8 dB fade 5 s, strong
hits = []
for b, amp in enumerate(seq):
    t = (np.arange(BLOCK) + b * BLOCK) / FS
    x = (amp * np.exp(2j * np.pi * off * t) + 0.01 * (rng.standard_normal(BLOCK)
         + 1j * rng.standard_normal(BLOCK))).astype(np.complex64)
    hits.append(0 in f.process(x))
assert all(hits[-30:]), "station must be detected again after a fade"
# VHF defaults also re-detect it but the floor creeps ~36 dB during the fade
# (SNR 55 → 19 dB); a longer fade would lose the station entirely.
assert f.channel_snrs()[0] > 45, f"floor crept under the fade: SNR {f.channel_snrs()[0]:.0f} dB"
print(f"  HF detector after a 5 s fade: detected again, SNR {f.channel_snrs()[0]:.0f} dB: OK")

# ── Playback priority ordering ───────────────────────────────────────────────
assert device_id_from_filename("20261106_153000_marine_Ch_16_156800kHz.wav") == "marine"
with tempfile.TemporaryDirectory() as tmp:
    pb = PlaybackQueue(tmp, priorities={"marine": 0, "railroad": 1, "ham": 5})
    names = ["20261106_153000_ham_CHU_7850kHz.wav",
             "20261106_153001_railroad_Ch7_160470kHz.wav",
             "20261106_153002_marine_Ch16_156800kHz.wav",
             "20261106_153003_ham_40m_7200kHz.wav"]
    for i, n in enumerate(names):
        p = Path(tmp) / n
        p.write_bytes(b"x")
        import os
        os.utime(p, (time.time() + i, time.time() + i))
        pb.enqueue(p)
    order = [device_id_from_filename(pb._next()[1].name) for _ in names]
    assert order == ["marine", "railroad", "ham", "ham"], order
    pb.enqueue(Path(tmp) / names[2])          # marine waiting while ham plays
    assert pb._more_important_waiting(5) and not pb._more_important_waiting(0)
print("  PlaybackQueue priority + preemption check: OK")

# ── Recorder: upconverter offset reaches the tuner; long audio is segmented ──
with tempfile.TemporaryDirectory() as tmp:
    ch = Channel("CHU", 7.850e6, mode="am", bandwidth_hz=8000)
    rec = Recorder("ham", "FAKE", 7.40e6, FS, [ch], tmp,
                   lo_offset_hz=125e6, max_segment_s=0.2)
    assert rec._source.center_freq == 132.40e6, rec._source.center_freq
    assert isinstance(rec._demods[0], LinearDemodulator)

    rec._states[0].update(True)               # pretend detection fired
    sig = lambda t: 0.05 * np.exp(2j * np.pi * (7.850e6 - 7.40e6) * t)
    for x in blocks(sig, 30):                 # ~0.48 s → 2 full 0.2 s segments
        rec._buffers[0].append(rec._demods[0].demodulate(rec._mixers[0].shift(x)))
        rec._buffered[0] += 768
        if rec._buffered[0] >= rec._max_segment_samples:
            rec._flush(0, ch, reset_demod=False)
            time.sleep(1.05)                  # distinct per-second filenames
    wavs = sorted(Path(tmp).rglob("*.wav"))
    assert len(wavs) == 2, wavs
    assert all("_ham_CHU_7850kHz" in w.name for w in wavs)
print("  Recorder LO offset + segmenting: OK")

print("\nAll HAM checks passed.")
