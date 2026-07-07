"""SDRScanner — main entry point."""
import logging
import sys

from src.scanner.config_loader import load_devices
from src.scanner.device_manager import list_connected_devices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scanner.main")


def main() -> None:
    log.info("SDRScanner starting...")

    config = load_devices()
    connected = list_connected_devices()

    log.info("Configured devices: %d", len(config["devices"]))
    log.info("Connected dongles:  %d", len(connected))

    if not connected:
        log.error("No RTL-SDR dongles detected — check USB connections.")
        sys.exit(1)

    for dev in connected:
        log.info("  Found: serial=%-20s  %s", dev["serial"] or "(no serial)", dev["label"])

    for cfg in config["devices"]:
        match = next((d for d in connected if d["serial"] == cfg["serial"]), None)
        status = "READY" if match else "NOT CONNECTED"
        log.info("  %s → %s [%s]", cfg["id"].upper().ljust(10), cfg["role"], status)

    # TODO: launch per-device scan loops
    log.info("Scan loops not yet implemented — scaffolding complete.")


if __name__ == "__main__":
    main()
