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

from src.scanner.band_schedule import BandSwitcher, band_channels
from src.scanner.config_loader import load_channel_config, load_devices
from src.scanner.device_manager import list_connected_devices
from src.scanner.fft_engine import Channel
from src.scanner.linear_demod import DETECT_WINDOW
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
BAND_CHECK_S = 60.0       # how often band-scheduled devices check day/night


def _build_channels(channel_config: str) -> list[Channel]:
    """Channels from config/channels/<name>.yaml. `mode` defaults to the file's
    `default_mode`, then nfm. SSB/CW/AM detection windows come from the mode."""
    cfg = load_channel_config(channel_config)
    return band_channels({"name": channel_config, "channels": cfg.get("channels", [])},
                         cfg.get("default_mode", "nfm"), DETECT_WINDOW)


def _receiver_location() -> tuple[float, float]:
    """Receiver lat/lon — the exact position already recorded for ADS-B MLAT."""
    mlat = load_channel_config("adsb")["mlat"]
    return float(mlat["receiver_lat"]), float(mlat["receiver_lon"])


def _check_window(dev_id: str, center_hz: float, sample_rate: float,
                  channels: list[Channel]) -> list[Channel]:
    """Drop channels outside the dongle's usable window; warn on the DC spike."""
    usable = 0.45 * sample_rate
    kept = []
    for ch in channels:
        off = ch.freq_hz - center_hz
        if abs(off) > usable:
            log.warning("[%s] %s (%.3f MHz) is outside the %.3f MHz ±%.0f kHz window — skipped",
                        dev_id, ch.name, ch.freq_hz / 1e6, center_hz / 1e6, usable / 1e3)
            continue
        if abs(off + ch.detect_offset_hz) < 10e3:
            log.warning("[%s] %s is within 10 kHz of the centre frequency — the "
                        "dongle's DC spike may cause false triggers", dev_id, ch.name)
        kept.append(ch)
    return kept


def main() -> None:
    log.info("SDRScanner starting…")

    all_devices = load_devices()["devices"]
    connected_serials = {d["serial"] for d in list_connected_devices()}

    recorders: list[Recorder] = []
    switchers: list[BandSwitcher] = []

    for dev in all_devices:
        serial = dev["serial"]
        channel_config = dev.get("channel_config")
        center_mhz = dev.get("center_mhz")

        if channel_config is None:
            log.debug("Skipping %s (no channel_config)", dev["id"])
            continue

        if serial not in connected_serials:
            log.warning("Device %s (%s) not connected — skipping", dev["id"], serial)
            continue

        cfg = load_channel_config(channel_config)
        if cfg.get("bands"):
            lat, lon = _receiver_location()
            default_mode = cfg.get("default_mode", "nfm")
            switchers.append(BandSwitcher(
                dev, cfg, lat, lon, RECORDINGS_DIR,
                build_channels=lambda band, m=default_mode: band_channels(band, m, DETECT_WINDOW),
                check_window=_check_window,
            ))
            log.info("Configured %s: day/night band schedule (%s)", dev["id"],
                     ", ".join(f"{b['when']}={b['name']}" for b in cfg["bands"]))
            continue

        if center_mhz is None:
            log.warning("Skipping %s (no center_mhz and no bands)", dev["id"])
            continue

        channels = _check_window(dev["id"], center_mhz * 1e6, float(dev["sample_rate"]),
                                 _build_channels(channel_config))
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
            lo_offset_hz=float(dev.get("upconverter_offset_mhz") or 0.0) * 1e6,
            max_segment_s=dev.get("max_segment_s"),
        )
        recorders.append(rec)
        log.info("Configured %s: %.3f MHz center, %d channels",
                 dev["id"], center_mhz, len(channels))

    if not recorders and not switchers:
        log.error("No recorders could be started — check device serials and config.")
        sys.exit(1)

    priorities = {d["id"]: int(d["playback_priority"])
                  for d in all_devices if d.get("playback_priority") is not None}
    pb = PlaybackQueue(recordings_dir=RECORDINGS_DIR, max_latency_s=MAX_LATENCY_S,
                       priorities=priorities)

    pb.start()
    for rec in recorders:
        rec.start()
    for sw in switchers:
        sw.start()

    log.info("%d recorder(s), %d band-scheduled device(s) running. Recordings → %s/  "
             "Press Ctrl+C to stop.", len(recorders), len(switchers), RECORDINGS_DIR)

    stop_event = threading.Event()

    def _shutdown(sig, frame):
        log.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while not stop_event.wait(BAND_CHECK_S):
        for sw in switchers:
            try:
                sw.tick()
            except Exception:
                log.exception("Band switch failed")

    for sw in switchers:
        sw.stop()
    for rec in recorders:
        rec.stop()
    pb.stop()

    log.info("All recorders stopped. Goodbye.")


if __name__ == "__main__":
    main()
