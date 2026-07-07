import yaml
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def load_devices() -> dict:
    with open(_CONFIG_DIR / "devices.yaml") as f:
        return yaml.safe_load(f)


def load_channel_config(name: str) -> dict:
    """Load a channel config by name (e.g. 'railroad', 'marine', 'p25', 'adsb')."""
    path = _CONFIG_DIR / "channels" / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def device_by_id(device_id: str) -> dict:
    devices = load_devices()
    for dev in devices["devices"]:
        if dev["id"] == device_id:
            return dev
    raise KeyError(f"No device with id '{device_id}' in devices.yaml")
