"""Spoken text → wake word check → scanner control request (control.py).

    split_wake("Hey radio, tune to 6180.")  → (True, "tune to 6180")
    parse("tune to 6180")                   → {"cmd": "ham", "freq_khz": 6180.0}

Pure text handling, no audio — tested in tests/test_voice_commands.py.
"""
import difflib
import re

WAKE = ("hey", "radio")
# Whisper's usual spellings of "hey" at the start of an utterance
_HEY = {"hey", "hay", "hei", "heh", "hi", "a", "eh", "ay", "okay", "ok"}
# ...and of "radio" (anything else must be a near-exact spelling)
_RADIO = {"radio", "radios", "rodeo", "radeo", "raydio", "rado", "radial", "radi"}

SOURCES = {
    "marine": "marine", "boats": "marine", "boat": "marine", "vhf": "marine",
    "railroad": "railroad", "rail": "railroad", "railway": "railroad", "train": "railroad",
    "trains": "railroad", "bnsf": "railroad",
    "ham": "ham", "shortwave": "ham", "short wave": "ham", "hf": "ham", "am": "ham",
}

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def _normalise(text: str) -> str:
    text = text.lower().replace("-", " ")
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)            # 6,180 → 6180
    text = re.sub(r"[^\w\s.]", " ", text)
    text = re.sub(r"\.(?!\d)", " ", text)                    # keep 6.18
    return _words_to_numbers(" ".join(text.split()))


def _words_to_numbers(text: str) -> str:
    """'forty nine meters' → '49 meters', 'six thousand one hundred eighty' → '6180'."""
    out, total, cur, active = [], 0, 0, False
    for w in text.split() + ["\0"]:
        if w in _UNITS:
            cur += _UNITS[w]; active = True
        elif w in _TENS:
            cur += _TENS[w]; active = True
        elif w == "hundred" and active:
            cur *= 100
        elif w == "thousand" and active:
            total += cur * 1000; cur = 0
        elif w == "and" and active:
            continue
        else:
            if active:
                out.append(str(total + cur))
                total, cur, active = 0, 0, False
            if w != "\0":
                out.append(w)
    return " ".join(out)


def split_wake(text: str) -> tuple[bool, str]:
    """(heard the wake phrase, the rest of the utterance)."""
    words = _normalise(text).split()
    # Whisper sometimes drops a quick "hey": "Radio, only marine." The comma
    # (addressing someone) separates it from "Radio Habana Cuba is on".
    if re.match(r"\s*radio\s*,", text, re.IGNORECASE) and len(words) > 1:
        return True, " ".join(words[1:])
    for i in range(min(3, len(words) - 1)):        # allow a stray "uh"/"so" first
        first, second = words[i], words[i + 1]
        if first in _HEY and (second in _RADIO or
                              difflib.SequenceMatcher(None, second, "radio").ratio() >= 0.8):
            return True, " ".join(words[i + 2:])
        # "hey radio" run together, e.g. "heyradio" / "hayradio"
        if difflib.SequenceMatcher(None, first, "heyradio").ratio() >= 0.8:
            return True, " ".join(words[i + 1:])
    return False, ""


def _source(text: str) -> str | None:
    for word, src in SOURCES.items():
        if re.search(rf"\b{word}\b", text):
            return src
    return None


def parse(text: str) -> dict | None:
    """Control request for a command (wake phrase already removed), or None."""
    t = _normalise(text)
    if not t:
        return None

    if re.search(r"\b(what|who)\b.*\b(playing|that|this|station|on)\b", t) or t in ("status",):
        return {"cmd": "status"}

    # Volume
    m = re.search(r"\bvolume (?:to )?(\d+)", t)
    if m:
        return {"cmd": "volume", "set": int(m.group(1))}
    if re.search(r"\b(volume up|louder|turn it up|turn up)\b", t):
        return {"cmd": "volume", "delta": 10}
    if re.search(r"\b(volume down|quieter|softer|turn it down|turn down)\b", t):
        return {"cmd": "volume", "delta": -10}

    # Mute / unmute / focus — "unmute" before "mute"
    if re.search(r"\bun ?mute\b", t):
        return {"cmd": "unmute", "source": None if re.search(r"\b(everything|all)\b", t) else _source(t)}
    if re.search(r"\b(play|hear) (everything|all)\b|\beverything\b|\ball sources\b", t):
        return {"cmd": "focus", "source": None}
    if re.search(r"\bmute\b|\bbe quiet\b|\bsilence\b|\bshut up\b", t):
        return {"cmd": "mute", "source": None if re.search(r"\b(everything|all)\b", t) else _source(t)}
    # "only marine", "marine only", "play marine only", "just the trains", "marine"
    filler = r"\b(only|just|focus on|play|listen to|switch to|the|please|radio)\b"
    bare = " ".join(re.sub(filler, " ", t).split())
    if bare in SOURCES:
        return {"cmd": "focus", "source": SOURCES[bare]}

    # HAM / shortwave
    if re.search(r"\b(automatic|auto|normal|schedule|scan)\b", t) and not re.search(r"\bmeters?\b", t):
        return {"cmd": "ham", "mode": "auto"}
    m = re.search(r"\b(\d+) ?(?:meters?|metres?|m)\b(?: band)?", t)
    if m:
        return {"cmd": "ham", "band": f"{m.group(1)}m"}
    m = re.search(r"\b(?:tune|go|switch|change)(?: to)?(?: frequency)? (\d+(?:\.\d+)?)(?: (khz|kilohertz|mhz|megahertz))?", t)
    if m:
        value, unit = float(m.group(1)), m.group(2) or ""
        khz = value * 1000 if unit.startswith(("mhz", "mega")) or value < 100 else value
        return {"cmd": "ham", "freq_khz": khz}
    m = re.search(r"\b(?:play|tune to|listen to|put on|find)\b (.+)", t)
    if m:
        name = m.group(1).strip()
        src = SOURCES.get(name)
        if src:                                    # "play marine" means focus
            return {"cmd": "focus", "source": src}
        return {"cmd": "ham", "station": name}
    return None
