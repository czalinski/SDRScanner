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


_STORAGE_DEFAULTS = {
    "recordings_dir": "recordings",
    "require_mount": None,
    "retention_days": 7,
    "max_disk_used_pct": 90,
    "prune_interval_s": 600,
}


def load_storage() -> dict:
    """config/storage.yaml merged over defaults; recordings_dir made absolute
    (relative paths are relative to the repo root)."""
    cfg = dict(_STORAGE_DEFAULTS)
    path = _CONFIG_DIR / "storage.yaml"
    if path.exists():
        with open(path) as f:
            cfg.update(yaml.safe_load(f) or {})
    rec = Path(cfg["recordings_dir"])
    cfg["recordings_dir"] = rec if rec.is_absolute() else _CONFIG_DIR.parent / rec
    return cfg


def device_by_id(device_id: str) -> dict:
    devices = load_devices()
    for dev in devices["devices"]:
        if dev["id"] == device_id:
            return dev
    raise KeyError(f"No device with id '{device_id}' in devices.yaml")
