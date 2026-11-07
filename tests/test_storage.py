"""
Recording storage + retention checks. Run: python -m tests.test_storage
"""
import datetime as dt
import os
import tempfile
import time
from pathlib import Path

from src.scanner.config_loader import load_storage
from src.scanner.playback_queue import PlaybackQueue
from src.scanner.retention import check_mount, prune


def make_day(root: Path, day: dt.date, n_files: int, mtime: float) -> Path:
    d = root / day.strftime("%Y%m%d")
    d.mkdir(parents=True)
    for i in range(n_files):
        f = d / f"{day:%Y%m%d}_12000{i}_ham_x_{i}kHz.wav"
        f.write_bytes(b"RIFF")
        os.utime(f, (mtime + i, mtime + i))
    return d


def test_age_prune():
    today = dt.date(2026, 11, 7)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for age in range(10):                      # today .. 9 days ago
            make_day(root, today - dt.timedelta(days=age), 2, 0)
        (root / "notes").mkdir()                   # not a day folder: untouched
        (root / "README.wav").write_bytes(b"x")    # loose file: untouched
        r = prune(root, 7, None, today=today)
        left = sorted(p.name for p in root.iterdir())
        assert r["days"] == 2, r                   # 8 and 9 days old
        assert "20261031" in left and "20261030" not in left, left   # 7 days old kept
        assert "notes" in left and "README.wav" in left
    print("  age prune: keeps 7 days + today, removes older, ignores other files: OK")


def test_disk_full_prune():
    today = dt.date(2026, 11, 7)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_day(root, today - dt.timedelta(days=1), 3, 1000)
        make_day(root, today, 3, 2000)
        # Fake disk: 95% full, each deleted file frees 2%
        def usage(_):
            n = sum(1 for _ in root.rglob("*.wav"))
            return 95.0 - 2.0 * (6 - n)
        r = prune(root, 7, 90, today=today, usage=usage)
        names = sorted(f.name for f in root.rglob("*.wav"))
        assert r["files"] == 3, r                  # 95 → 93 → 91 → 89
        assert not (root / "20261106").exists(), "emptied day folder should be removed"
        assert len(names) == 3 and all(n.startswith("20261107") for n in names), names
    print("  disk-full prune: oldest files go first until under the limit: OK")


def test_mount_and_config():
    assert check_mount(None)
    assert check_mount("/")
    with tempfile.TemporaryDirectory() as tmp:
        assert not check_mount(tmp)
    cfg = load_storage()
    assert cfg["recordings_dir"].is_absolute()
    assert cfg["retention_days"] == 7
    print(f"  mount check + storage config ({cfg['recordings_dir']}, "
          f"mount={cfg['require_mount']}): OK")


def test_playback_watches_recent_days_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        today = dt.date.today()
        make_day(root, today, 1, time.time())
        make_day(root, today - dt.timedelta(days=5), 1, time.time())
        pb = PlaybackQueue(root)
        queued = []
        pb.enqueue = queued.append
        import threading
        t = threading.Thread(target=pb._watch, daemon=True)
        t.start()
        time.sleep(0.3)
        pb._stop.set()
        t.join(2)
        assert len(queued) == 1 and queued[0].parent.name == today.strftime("%Y%m%d"), queued
    print("  playback watcher only scans today/yesterday: OK")


if __name__ == "__main__":
    test_age_prune()
    test_disk_full_prune()
    test_mount_and_config()
    test_playback_watches_recent_days_only()
    print("\nAll storage checks passed.")
