"""Quick sanity check for core scanner modules — no hardware required."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np

print("Importing modules...")
from src.scanner.channel_state import ChannelState, State
from src.scanner.config_loader import load_channel_config, load_devices
from src.scanner.fft_engine import Channel, FFTEngine, THRESHOLD_DB
from src.scanner.nfm_demod import AUDIO_RATE, NFMDemodulator
from src.scanner.recorder import Recorder, _shift_to_baseband

print("  All imports OK")

# ── Config ─────────────────────────────────────────────────────────────────────
devs = load_devices()
print("  Devices configured:", len(devs["devices"]))
rr_cfg = load_channel_config("railroad")
print("  Railroad channels:", len(rr_cfg["channels"]))

# ── ChannelState ───────────────────────────────────────────────────────────────
cs = ChannelState(0, "test")
assert cs.state is State.IDLE
cs.update(True)
assert cs.state is State.ACTIVE
cs.update(False)
assert cs.state is State.TAIL
cs._tail_start = time.monotonic() - 5   # fast-forward tail timer
cs.update(False)
assert cs.state is State.IDLE
print("  ChannelState: OK")

# ── FFTEngine ──────────────────────────────────────────────────────────────────
FS = 2.048e6
CENTER = 161.0e6
channels = [Channel("BNSF Ch7", 160.470e6), Channel("BNSF Ch8", 160.530e6)]
fft = FFTEngine(center_freq=CENTER, sample_rate=FS, channels=channels)

rng = np.random.default_rng(42)

def make_noise(n=32768, amplitude=0.01):
    return ((rng.standard_normal(n) + 1j * rng.standard_normal(n)) * amplitude).astype(np.complex64)

# Prime noise floor with several distinct quiet blocks
for _ in range(20):
    fft.process(make_noise())

active = fft.process(make_noise())
snrs = fft.channel_snrs()
snr_str = ", ".join("%.1f dB" % s for s in snrs)
print("  FFTEngine quiet: active=%s  snrs=[%s]" % (active, snr_str))
assert active == [], "Quiet noise should not trigger detection"
for s in snrs:
    assert s < THRESHOLD_DB, "Quiet SNR %.1f dB must be below threshold %.1f dB" % (s, THRESHOLD_DB)

# Inject a tone on Ch7 (160.470 MHz) on top of noise
t = np.arange(32768, dtype=np.float64) / FS
tone_offset = 160.470e6 - CENTER   # -530 000 Hz
# Use a realistic amplitude (much stronger than noise) plus background noise
tone_block = (np.exp(2j * np.pi * tone_offset * t) * 0.3).astype(np.complex64) + make_noise(amplitude=0.005)

# First block primes detection; second block (with same signal) should trigger
fft.process(tone_block)
active2 = fft.process(tone_block)
snrs2 = fft.channel_snrs()
snr_str2 = ", ".join("%.1f dB" % s for s in snrs2)
print("  FFTEngine tone injection: active=%s  snrs=[%s]" % (active2, snr_str2))
assert 0 in active2, "Tone on Ch7 should be detected (SNR was %.1f dB)" % snrs2[0]
assert 1 not in active2, "Ch8 (no signal) must stay idle"

# ── NFMDemodulator ─────────────────────────────────────────────────────────────
demod = NFMDemodulator(sample_rate=FS)
audio = demod.demodulate(make_noise())
assert audio.dtype == np.float32
expected = round(32768 / FS * 48000)
assert abs(len(audio) - expected) <= 2, \
    "Expected ~%d audio samples, got %d" % (expected, len(audio))
assert np.max(np.abs(audio)) <= 1.0, "Audio must be clipped to [-1, 1]"
print("  NFMDemodulator: OK  output %d samples @ 48 kHz" % len(audio))

demod.reset()
audio2 = demod.demodulate(make_noise())
assert len(audio2) == len(audio)
print("  NFMDemodulator reset: OK")

# ── Recorder — WAV write + _shift_to_baseband ─────────────────────────────────
FS = 2.048e6
CENTER = 161.0e6
t = np.arange(32768, dtype=np.float64) / FS
offset = 160.470e6 - CENTER
bb = _shift_to_baseband(
    (np.exp(2j * np.pi * offset * t) * 0.3).astype(np.complex64),
    offset, FS,
)
assert bb.dtype == np.complex64
assert abs(np.mean(np.angle(bb))) < 0.1, "Baseband shift should center near 0 Hz"

# Confirm Recorder writes a WAV file for a synthetic tone sequence
with tempfile.TemporaryDirectory() as tmpdir:
    ch = Channel("TestCh", 160.470e6)
    rec = Recorder(
        dev_id="test", serial="FAKE", center_freq=CENTER,
        sample_rate=FS, channels=[ch],
        recordings_dir=tmpdir,
    )
    # Directly exercise _flush by loading the buffer
    audio_chunk = NFMDemodulator(FS).demodulate(
        _shift_to_baseband(
            (np.exp(2j * np.pi * offset * t) * 0.3).astype(np.complex64),
            offset, FS,
        )
    )
    rec._buffers[0] = [audio_chunk]
    rec._flush(0, ch)
    wav_files = list(Path(tmpdir).rglob("*.wav"))
    assert len(wav_files) == 1, f"Expected 1 WAV file, got {len(wav_files)}"
    assert wav_files[0].stat().st_size > 44, "WAV file too small (header only?)"
    print("  Recorder WAV flush: OK → %s" % wav_files[0].name)

print("\nAll checks passed.")
