"""
Recording retention: delete old recordings so the data drive never fills.

Recorder writes recordings/YYYYMMDD/<file>.wav. prune():
  1. deletes whole day folders older than `retention_days` (by folder date);
  2. if the filesystem is still fuller than `max_used_pct`, deletes the oldest
     WAV files (by mtime) until it isn't — a safety net for heavy days.
Only YYYYMMDD folders and *.wav files are ever touched.
"""
import datetime as dt
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def _day_dirs(root: Path) -> list[tuple[dt.date, Path]]:
    out = []
    if not root.is_dir():
        return out
    for p in root.iterdir():
        if p.is_dir() and len(p.name) == 8 and p.name.isdigit():
            try:
                out.append((dt.datetime.strptime(p.name, "%Y%m%d").date(), p))
            except ValueError:
                pass
    return sorted(out)


def used_pct(path: Path) -> float:
    u = shutil.disk_usage(path)
    return 100.0 * u.used / u.total


def prune(root: str | Path, retention_days: float, max_used_pct: float | None = None,
          today: dt.date | None = None, usage=used_pct) -> dict:
    """Returns {"days": n day folders removed, "files": n extra files removed}."""
    root = Path(root)
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(days=retention_days)
    removed_days = removed_files = 0

    for day, path in _day_dirs(root):
        if day < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed_days += 1
            log.info("Retention: removed %s (older than %g days)", path, retention_days)

    if max_used_pct is not None and root.is_dir() and usage(root) > max_used_pct:
        files = sorted((f for _, d in _day_dirs(root) for f in d.glob("*.wav")),
                       key=lambda f: f.stat().st_mtime)
        for f in files:
            if usage(root) <= max_used_pct:
                break
            try:
                f.unlink()
                removed_files += 1
            except FileNotFoundError:
                pass
        for _, d in _day_dirs(root):
            if not any(d.iterdir()):
                d.rmdir()
        log.warning("Retention: disk over %g%% — removed %d oldest recordings",
                    max_used_pct, removed_files)

    return {"days": removed_days, "files": removed_files}


def check_mount(path: str | Path | None) -> bool:
    """True if no mount is required, or `path` is a mounted filesystem."""
    return path is None or os.path.ismount(path)
