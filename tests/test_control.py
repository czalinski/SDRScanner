"""Scanner control: commands, persistence across restarts, corrupt-file fallback,
playback gating, HAM band building. No hardware, no audio.

Run: python3 -m tests.test_control
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.scanner.control import (DEFAULTS, Control, band_for_freq, band_for_meters,
                                 load_state, send, serve, spoken_description)

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "control.json"

    c = Control(path, apply_volume=False)
    assert c.state == DEFAULTS and not path.exists()             # missing → defaults
    assert c.handle({"cmd": "volume", "delta": -30})["say"] == "Volume 50 percent."
    c.handle({"cmd": "mute", "source": "railroad"})
    assert not c.should_play("railroad") and c.should_play("marine")
    c.handle({"cmd": "focus", "source": "ham"})
    assert c.should_play("ham") and not c.should_play("marine")
    c.handle({"cmd": "ham", "band": "31"})
    assert c.ham_band()["name"] == "31m"

    # "Reboot": a new Control comes back in the same mode
    c2 = Control(path, apply_volume=False)
    assert c2.state["volume"] == 50 and c2.state["focus"] == "ham"
    assert c2.state["ham"] == {"band": "31m"} and "railroad" in c2.state["muted_sources"]
    print("  state survives restart: OK")

    c2.handle({"cmd": "unmute"})
    assert c2.should_play("marine") and c2.should_play("railroad")
    c2.handle({"cmd": "mute"})
    assert not any(c2.should_play(d) for d in ("marine", "railroad", "ham"))
    c2.handle({"cmd": "ham", "mode": "auto"})
    assert c2.ham_band() is None
    assert not c2.handle({"cmd": "ham", "freq_khz": 145000})["ok"]  # VHF, not shortwave
    assert not c2.handle({"cmd": "ham", "band": "30"})["ok"]        # CW/data only, no voice
    print("  commands: OK")

    for junk in ("{not json", "[1,2]", '{"volume": "loud", "focus": "kitchen", "ham": 7}'):
        path.write_text(junk)
        assert load_state(path) == DEFAULTS, junk
    path.write_text('{"volume": 30, "muted": "yes"}')                # keep the good parts
    assert load_state(path)["volume"] == 30 and load_state(path)["muted"] is False
    print("  corrupt/partial file → defaults: OK")

    # Socket round trip
    sock = Path(tmp) / "c.sock"
    serve(c2, sock)
    time.sleep(0.1)
    assert send({"cmd": "volume", "set": 70}, sock)["say"] == "Volume 70 percent."
    assert send({"cmd": "state"}, sock)["state"]["volume"] == 70
    assert json.loads(path.read_text())["volume"] == 70
    print("  socket: OK")

# Bands keep every listened frequency off the dongle's DC spike and inside its window
for name in ("49m", "31m", "19m", "120m", "11m"):
    b = band_for_meters(name)
    rng = b["scan_ranges"][0]
    assert rng["from_mhz"] - b["center_mhz"] >= 0.025, name
    assert rng["to_mhz"] - b["center_mhz"] <= 0.9, name
b = band_for_freq(6180)
assert b["channels"][0]["name"] == "49m 6180" and abs(b["center_mhz"] - 6.15) < 1e-9
print("  band windows clear of DC spike: OK")

assert spoken_description({"device": "marine", "channel": "Ch 14 — Vessel Traffic"}) \
    == "marine channel 14, Vessel Traffic"
assert spoken_description({"device": "ham", "freq_khz": 6180, "station": "Radio Nacional",
                           "language": "Portuguese"}) == "Radio Nacional, 6180 kilohertz, in Portuguese"
print("  spoken descriptions: OK")
print("\nAll control checks passed.")
