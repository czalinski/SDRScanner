"""Voice commands: "Hey radio, <command>" → the running scanner (control.py).

Listens to the USB voice mic, cuts the stream into utterances by loudness (the
mic's own noise suppression keeps the scanner's speaker audio out — measured
~60 dB below speech), transcribes each with Whisper (faster-whisper tiny.en,
offline), and acts only on utterances that start with the wake phrase.
"Hey radio" on its own beeps and takes the next utterance as the command.
Replies are spoken with Piper through the default speaker, and scanner
playback is paused (control "hold") while it speaks.

Run: python -m src.voice.voice_service    (systemd user unit voice-commands)
"""
import logging
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from src.scanner.control import send
from src.voice.commands import parse, split_wake

log = logging.getLogger(__name__)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)   # per-utterance chatter
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    datefmt="%H:%M:%S")

MIC_MATCH = os.environ.get("SDR_MIC_MATCH", "usb")   # substring of the PulseAudio source name
WHISPER_MODEL = os.environ.get("SDR_WHISPER_MODEL", "tiny.en")
PIPER_VOICE = Path.home() / ".local/share/sdrscanner/piper/en_US-lessac-medium.onnx"

RATE = 16000
FRAME = 320                    # 20 ms
START_DBFS = -45.0             # speech is ~-28 dBFS at the mic, room/speaker ~-75…-90
END_DBFS = -55.0
START_FRAMES = 3               # 60 ms above START_DBFS opens an utterance
END_SILENCE_S = 0.8            # this much quiet closes it
PRE_ROLL_S = 0.3
MAX_UTTERANCE_S = 10.0
ARMED_S = 6.0                  # after a bare "hey radio", the next utterance is the command
# Biases Whisper toward the vocabulary we expect
PROMPT = ("Hey radio, tune to 6180. Hey radio, go to 49 meters. Hey radio, mute railroad. "
          "Hey radio, what's playing? Hey radio, volume up. Hey radio, only marine.")


def find_mic() -> str:
    out = subprocess.run(["pactl", "list", "sources", "short"], capture_output=True,
                         text=True, check=True).stdout
    for line in out.splitlines():
        name = line.split("\t")[1]
        if ".monitor" not in name and MIC_MATCH.lower() in name.lower():
            return name
    raise RuntimeError(f"No PulseAudio input matching {MIC_MATCH!r}:\n{out}")


def _dbfs(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean((x / 32768.0) ** 2)) + 1e-9)


class Speaker:
    def __init__(self):
        from piper import PiperVoice
        self._voice = PiperVoice.load(str(PIPER_VOICE))
        self._dir = Path(tempfile.mkdtemp(prefix="sdr-voice-"))
        self._beep = self._dir / "beep.wav"
        t = np.arange(int(0.12 * 22050)) / 22050
        tone = (0.3 * np.sin(2 * np.pi * 880 * t) * np.hanning(len(t)) * 32767).astype(np.int16)
        self._write(self._beep, tone, 22050)
        self.busy_until = 0.0     # mic input before this is our own voice — ignore it

    @staticmethod
    def _write(path: Path, samples: np.ndarray, rate: int) -> None:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(samples.tobytes())

    def beep(self) -> None:
        self._play(self._beep, 0.2)

    def say(self, text: str) -> None:
        if not text:
            return
        path = self._dir / "say.wav"
        with wave.open(str(path), "wb") as w:
            self._voice.synthesize_wav(text, w)
        with wave.open(str(path)) as w:
            seconds = w.getnframes() / w.getframerate()
        self._play(path, seconds)

    def _play(self, path: Path, seconds: float) -> None:
        try:
            send({"cmd": "hold", "seconds": seconds + 0.5}, timeout=2)
        except OSError:
            pass                                   # scanner down — still answer
        self.busy_until = time.monotonic() + seconds + 0.3
        subprocess.run(["paplay", str(path)], check=False)
        self.busy_until = time.monotonic() + 0.3


def utterances(mic: str):
    """Yield (int16 audio, end time) for each stretch of speech."""
    proc = subprocess.Popen(["parecord", "--raw", "-d", mic, f"--rate={RATE}", "--channels=1",
                             "--format=s16le", "--latency-msec=40"], stdout=subprocess.PIPE)
    pre = int(PRE_ROLL_S * RATE / FRAME)
    end_frames = int(END_SILENCE_S * RATE / FRAME)
    max_frames = int(MAX_UTTERANCE_S * RATE / FRAME)
    history: list[np.ndarray] = []
    speech: list[np.ndarray] | None = None
    loud = quiet = 0
    try:
        while True:
            raw = proc.stdout.read(FRAME * 2)
            if len(raw) < FRAME * 2:
                raise RuntimeError("microphone stream ended")
            frame = np.frombuffer(raw, np.int16)
            level = _dbfs(frame)
            if speech is None:
                history = (history + [frame])[-pre:]
                loud = loud + 1 if level > START_DBFS else 0
                if loud >= START_FRAMES:
                    speech, quiet = list(history), 0
            else:
                speech.append(frame)
                quiet = quiet + 1 if level < END_DBFS else 0
                if quiet >= end_frames or len(speech) >= max_frames:
                    yield np.concatenate(speech), time.monotonic()
                    speech, history, loud = None, [], 0
    finally:
        proc.terminate()


def main() -> None:
    from faster_whisper import WhisperModel
    mic = find_mic()
    log.info("Microphone: %s", mic)
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=4)
    speaker = Speaker()
    log.info('Listening for "hey radio" (Whisper %s)', WHISPER_MODEL)

    armed_until = 0.0
    for audio, ended in utterances(mic):
        if ended - len(audio) / RATE < speaker.busy_until:
            continue                               # overlapped our own reply
        if len(audio) < 0.3 * RATE:
            continue
        segs, _ = model.transcribe(audio.astype(np.float32) / 32768.0, language="en",
                                   beam_size=1, initial_prompt=PROMPT, vad_filter=False,
                                   condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segs).strip()
        if not text:
            continue
        heard, rest = split_wake(text)
        if not heard and time.monotonic() < armed_until:
            heard, rest = True, text
        if not heard:
            # Room conversation — never logged (privacy); just note that it happened
            log.debug("Ignored an utterance without the wake phrase")
            continue
        log.info("Heard %r", text)
        armed_until = 0.0
        if not rest:
            speaker.beep()
            armed_until = time.monotonic() + ARMED_S
            continue
        req = parse(rest)
        if req is None:
            speaker.say(f"Sorry, I didn't understand: {rest}.")
            continue
        try:
            reply = send(req)
        except OSError:
            speaker.say("The scanner isn't running.")
            continue
        speaker.say(reply.get("say", ""))


if __name__ == "__main__":
    main()
