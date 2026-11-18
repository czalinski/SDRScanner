"""Kiosk audio panel — recording-name parsing, labels, playback history file.

Run: python3 -m tests.test_audio_panel
"""
import json
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, ".")

from src.display.audio_panel import _is_playing, describe
from src.scanner.playback_queue import PlaybackQueue, describe_recording

d = describe_recording("20261118_134104_marine_Ch_14_—_Vessel_Traffic_156700kHz.wav")
assert d == {"device": "marine", "channel": "Ch 14 — Vessel Traffic", "freq_khz": 156700}, d
assert describe(d)[:2] == ("Marine Ch 14", "Vessel Traffic")

d = describe_recording("20261118_132110_railroad_BNSF_Road_Ch_7_160470kHz.wav")
assert describe(d)[:2] == ("Rail BNSF Road Ch 7", "160.470 MHz"), describe(d)

d = describe_recording("20261118_134053_ham_19m_15140_15140kHz.wav")
assert describe(d)[:2] == ("HAM 15140 kHz", "19m band"), describe(d)
print("  labels: OK")

now = time.time()
assert _is_playing({"status": "playing", "started": now - 1, "duration_s": 5}, now)
assert not _is_playing({"status": "playing", "started": now - 60, "duration_s": 5}, now)
print("  stale 'playing' entry ignored: OK")

# PlaybackQueue writes the history file around a real (silent) playback
with tempfile.TemporaryDirectory() as tmp:
    day = Path(tmp) / time.strftime("%Y%m%d")
    day.mkdir()
    wav = day / f"{time.strftime('%Y%m%d_%H%M%S')}_marine_Ch_16_—_Distress_156800kHz.wav"
    with wave.open(str(wav), "w") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(48000)
        w.writeframes(b"\0\0" * 24000)
    hist = Path(tmp) / "playback.json"
    pb = PlaybackQueue(tmp, history_path=hist)
    pb.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        h = json.loads(hist.read_text())["history"] if hist.exists() else []
        if h and h[0]["status"] != "playing":
            break
        time.sleep(0.2)
    pb.stop()
    assert h and h[0]["channel"] == "Ch 16 — Distress" and h[0]["duration_s"] == 0.5, h
    assert h[0]["status"] in ("played", "interrupted"), h
print("  history file written: OK")
print("\nAll audio panel checks passed.")
