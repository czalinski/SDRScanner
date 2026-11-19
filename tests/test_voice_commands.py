"""Voice command text parsing — wake phrase and command grammar.

Run: python3 -m tests.test_voice_commands
"""
import sys

sys.path.insert(0, ".")

from src.voice.commands import parse, split_wake

for text, rest in [
    ("Hey radio, tune to 6180.", "tune to 6180"),
    ("Hey, Radio. What's playing?", "what s playing"),
    ("Hay radio mute railroad", "mute railroad"),
    ("Hey Rodeo, volume up.", "volume up"),     # close enough to "radio"
    ("Uh, hey radio, automatic.", "automatic"),
    ("Hey radio.", ""),
    ("Radio, only marine.", "only marine"),     # Whisper dropped the "hey"
]:
    heard, got = split_wake(text)
    assert heard and got == rest, (text, heard, got)
for text in ("I'm talking right now.", "Hey Rachel, what's up?", "Hey, ready to go?", "Radio Habana Cuba is on", ""):
    assert not split_wake(text)[0], text
print("  wake phrase: OK")

cases = {
    "volume up": {"cmd": "volume", "delta": 10},
    "turn it down": {"cmd": "volume", "delta": -10},
    "volume 60": {"cmd": "volume", "set": 60},
    "volume sixty": {"cmd": "volume", "set": 60},
    "mute": {"cmd": "mute", "source": None},
    "mute railroad": {"cmd": "mute", "source": "railroad"},
    "mute the trains": {"cmd": "mute", "source": "railroad"},
    "unmute": {"cmd": "unmute", "source": None},
    "unmute marine": {"cmd": "unmute", "source": "marine"},
    "un mute everything": {"cmd": "unmute", "source": None},
    "only marine": {"cmd": "focus", "source": "marine"},
    "just shortwave": {"cmd": "focus", "source": "ham"},
    "marine only": {"cmd": "focus", "source": "marine"},
    "play marine only": {"cmd": "focus", "source": "marine"},
    "marine": {"cmd": "focus", "source": "marine"},
    "just the trains": {"cmd": "focus", "source": "railroad"},
    "switch to shortwave": {"cmd": "focus", "source": "ham"},
    "play everything": {"cmd": "focus", "source": None},
    "go to 49 meters": {"cmd": "ham", "band": "49m"},
    "forty one meter band": {"cmd": "ham", "band": "41m"},
    "tune to 6180": {"cmd": "ham", "freq_khz": 6180.0},
    "tune to 6,180 kilohertz": {"cmd": "ham", "freq_khz": 6180.0},
    "tune to 6.18": {"cmd": "ham", "freq_khz": 6180.0},
    "tune to 15.14 megahertz": {"cmd": "ham", "freq_khz": 15140.0},
    "tune to six thousand one hundred eighty": {"cmd": "ham", "freq_khz": 6180.0},
    "play radio habana cuba": {"cmd": "ham", "station": "radio habana cuba"},
    "listen to WBCQ": {"cmd": "ham", "station": "wbcq"},
    "play marine": {"cmd": "focus", "source": "marine"},
    "automatic": {"cmd": "ham", "mode": "auto"},
    "back to normal": {"cmd": "ham", "mode": "auto"},
    "what's playing": {"cmd": "status"},
    "what was that": {"cmd": "status"},
    "who is this": {"cmd": "status"},
    "make me a sandwich": None,
}
for text, want in cases.items():
    got = parse(text)
    assert got == want, (text, got, want)
print(f"  {len(cases)} commands: OK")
print("\nAll voice command checks passed.")
