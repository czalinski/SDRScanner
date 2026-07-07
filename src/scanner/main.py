"""SDRScanner — main entry point. Starts one ScanLoop per connected, configured device."""
import logging
import signal
import sys
import threading

from src.scanner.config_loader import device_by_id, load_channel_config, load_devices
from src.scanner.device_manager import list_connected_devices
from src.scanner.fft_engine import Channel
from src.scanner.scan_loop import ScanLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scanner.main")


def _build_channels(channel_config: str) -> list[Channel]:
    cfg = load_channel_config(channel_config)
    channels: list[Channel] = []
    for ch in cfg.get("channels", []):
        channels.append(Channel(
            name=ch["name"],
            freq_hz=ch["freq_mhz"] * 1e6,
        ))
    return channels


def main() -> None:
    log.info("SDRScanner starting…")

    all_devices = load_devices()["devices"]
    connected_serials = {d["serial"] for d in list_connected_devices()}

    loops: list[ScanLoop] = []

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

        loop = ScanLoop(
            dev_id=dev["id"],
            serial=serial,
            center_freq=center_mhz * 1e6,
            sample_rate=float(dev["sample_rate"]),
            channels=channels,
            gain=dev.get("gain"),
            ppm=int(dev.get("ppm", 0)),
        )
        loops.append(loop)
        log.info("Configured %s: %.3f MHz center, %d channels",
                 dev["id"], center_mhz, len(channels))

    if not loops:
        log.error("No scan loops could be started — check device serials and config.")
        sys.exit(1)

    # ── Start all loops ────────────────────────────────────────────────────────
    for loop in loops:
        loop.start()

    log.info("%d scan loop(s) running. Press Ctrl+C to stop.", len(loops))

    stop_event = threading.Event()

    def _shutdown(sig, frame):
        log.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    stop_event.wait()

    for loop in loops:
        loop.stop()

    log.info("All scan loops stopped. Goodbye.")


if __name__ == "__main__":
    main()
