"""SDRScanner — main entry point.

Starts one Recorder per connected, configured device plus a shared PlaybackQueue.
Each transmission on any channel is written to recordings/YYYYMMDD/ as a WAV
file. The PlaybackQueue watches that directory and plays files in order, dropping
anything older than MAX_LATENCY_S to avoid stale-context playback.
"""
import logging
import signal
import sys
import threading
from pathlib import Path

from src.scanner.config_loader import load_channel_config, load_devices
from src.scanner.device_manager import list_connected_devices
from src.scanner.fft_engine import Channel
from src.scanner.playback_queue import PlaybackQueue
from src.scanner.recorder import Recorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scanner.main")

RECORDINGS_DIR = Path("recordings")
MAX_LATENCY_S = 30.0


def _build_channels(channel_config: str) -> list[Channel]:
    cfg = load_channel_config(channel_config)
    return [
        Channel(name=ch["name"], freq_hz=ch["freq_mhz"] * 1e6)
        for ch in cfg.get("channels", [])
    ]


def main() -> None:
    log.info("SDRScanner starting…")

    all_devices = load_devices()["devices"]
    connected_serials = {d["serial"] for d in list_connected_devices()}

    recorders: list[Recorder] = []

    for dev in all_devices:
        serial = dev["serial"]
        channel_config = dev.get("channel_config")
        center_mhz = dev.get("center_mhz")

        if channel_config is None or center_mhz is None:
            log.debug("Skipping %s (no channel_config or center_mhz)", dev["id"])
            continue

        if serial not in connected_serials:
            log.warning("Device %s (%s) not connected — skipping", dev["id"], serial)
            continue

        channels = _build_channels(channel_config)
        if not channels:
            log.warning("No channels found for %s — skipping", dev["id"])
            continue

        rec = Recorder(
            dev_id=dev["id"],
            serial=serial,
            center_freq=center_mhz * 1e6,
            sample_rate=float(dev["sample_rate"]),
            channels=channels,
            recordings_dir=RECORDINGS_DIR,
            gain=dev.get("gain"),
            ppm=int(dev.get("ppm", 0)),
        )
        recorders.append(rec)
        log.info("Configured %s: %.3f MHz center, %d channels",
                 dev["id"], center_mhz, len(channels))

    if not recorders:
        log.error("No recorders could be started — check device serials and config.")
        sys.exit(1)

    pb = PlaybackQueue(recordings_dir=RECORDINGS_DIR, max_latency_s=MAX_LATENCY_S)

    pb.start()
    for rec in recorders:
        rec.start()

    log.info("%d recorder(s) running. Recordings → %s/  Press Ctrl+C to stop.",
             len(recorders), RECORDINGS_DIR)

    stop_event = threading.Event()

    def _shutdown(sig, frame):
        log.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    stop_event.wait()

    for rec in recorders:
        rec.stop()
    pb.stop()

    log.info("All recorders stopped. Goodbye.")


if __name__ == "__main__":
    main()
