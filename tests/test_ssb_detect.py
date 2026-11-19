"""Ham SSB voice: the detector picks the right 1 kHz slot, bands/commands map
to sideband. No hardware.

Run: python3 -m tests.test_ssb_detect
"""
import sys

import numpy as np

sys.path.insert(0, ".")

from src.scanner.band_schedule import band_channels
from src.scanner.control import band_for_freq, band_for_meters, spoken_description
from src.scanner.fft_engine import FFTEngine
from src.scanner.linear_demod import DETECT_WINDOW
from src.voice.commands import parse

FS = 2_048_000
rng = np.random.default_rng(1)

band = band_for_meters("40m")
channels = band_channels(band, "am", DETECT_WINDOW)
assert len(channels) == 176 and all(c.mode == "lsb" for c in channels)
center = band["center_mhz"] * 1e6


def lsb_voice(dial_hz: float, n: int, t0: int) -> np.ndarray:
    """Speech-like LSB signal: audio 300–2700 Hz below the dial, falling ~6 dB/octave
    above 500 Hz, with a transmitter's filter roll-off below ~400 Hz."""
    t = (np.arange(n) + t0) / FS
    x = np.zeros(n, np.complex128)
    for audio in np.arange(350, 2700, 150):
        amp = 300.0 / max(audio, 500) * min(1.0, (audio - 200) / 250)
        x += amp * np.exp(2j * np.pi * ((dial_hz - audio - center) * t + rng.random()))
    return x


def noise(n):
    return (rng.normal(size=n) + 1j * rng.normal(size=n)) * 0.05


def pick(dial_hz: float) -> float:
    fft = FFTEngine(center, FS, channels, fft_size=band["detector"]["fft_size"])
    n = 32768
    for i in range(20):
        fft.process(noise(n).astype(np.complex64))
    active = []
    for i in range(5):
        active = fft.process((noise(n) + 0.02 * lsb_voice(dial_hz, n, i * n)).astype(np.complex64))
    assert active, "not detected"
    snrs = fft.channel_snrs()
    best = max(active, key=lambda j: snrs[j])
    return channels[best].freq_hz


for dial in (7_188_000, 7_250_000, 7_131_000):
    got = pick(dial)
    assert got == dial, (dial, got)
for off in (-300, 200, 300):                    # off the raster → nearest slot
    assert pick(7_200_000 + off) == 7_200_000, (off, pick(7_200_000 + off))
print("  SSB station lands on its own 1 kHz slot: OK")

b = band_for_meters("75m")
assert b["scan_ranges"][0]["mode"] == "lsb" and b["detector"]["fft_size"] == 16384
assert band_for_freq(3873)["channels"][0]["mode"] == "lsb"
assert band_for_freq(14250)["channels"][0]["mode"] == "usb"
assert band_for_freq(6180)["channels"][0]["mode"] == "am" and "detector" not in band_for_freq(6180)
assert spoken_description({"device": "ham", "freq_khz": 3873, "channel": "75m 3873"}) \
    == "ham radio, 75 meters, 3873 kilohertz"
print("  ham bands → sideband: OK")

assert parse("go to forty meters") == {"cmd": "ham", "band": "40m"}
assert parse("seventy five meters") == {"cmd": "ham", "band": "75m"}
assert parse("tune to 3873") == {"cmd": "ham", "freq_khz": 3873.0}
assert parse("tune to 3.873") == {"cmd": "ham", "freq_khz": 3873.0}
print("  voice commands: OK")
print("\nAll SSB checks passed.")
