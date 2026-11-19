"""Shortwave station names from the EiBi broadcast schedule (eibispace.de).

EiBi publishes a free, seasonal list of every known shortwave broadcast:
frequency, UTC hours, days, station, language, target area. Seasons follow the
international schedule periods — "A" from the last Sunday of March, "B" from
the last Sunday of October — so the file for 2026-11 is sked-b26.csv.

The CSV is downloaded to CACHE_DIR and refreshed weekly (EiBi updates it
during the season). Without network the newest cached file is used; without
any file, lookups simply return nothing and the scanner shows frequencies.

    db = StationDB()
    db.lookup(15140)          # → [Entry(station="Radio Habana Cuba", ...)]
    db.label(15140)           # → "Radio Habana Cuba (Spanish)"
"""
import csv
import logging
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "sdrscanner" / "eibi"
URL = "http://www.eibispace.de/dx/sked-{season}.csv"
REFRESH_S = 7 * 86400
FREQ_TOLERANCE_KHZ = 2

LANGUAGES = {
    "A": "Arabic", "AM": "Amharic", "B": "Bengali", "BU": "Bulgarian", "C": "Chinese",
    "CA": "Cantonese", "CR": "Creole", "CZ": "Czech", "D": "German", "DA": "Danish",
    "E": "English", "EO": "Esperanto", "F": "French", "FA": "Farsi", "GR": "Greek",
    "HA": "Hausa", "HB": "Hebrew", "HI": "Hindi", "HU": "Hungarian", "I": "Italian",
    "IN": "Indonesian", "J": "Japanese", "K": "Korean", "KH": "Khmer", "M": "Mandarin",
    "NL": "Dutch", "P": "Portuguese", "PS": "Pashto", "PO": "Polish", "R": "Russian",
    "RO": "Romanian", "S": "Spanish", "SWA": "Swahili", "T": "Thai", "TB": "Tibetan",
    "TU": "Turkish", "UK": "Ukrainian", "UR": "Urdu", "VN": "Vietnamese",
    "-TS": "time signal", "-MX": "music", "-CW": "Morse",
}
_DAYS = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}


@dataclass(frozen=True)
class Entry:
    khz: float
    start: int          # minutes after 00:00 UTC
    end: int            # may be < start (runs past midnight); 1440 = 24:00
    days: str
    country: str
    station: str
    language: str       # EiBi code, e.g. "E"
    target: str         # e.g. "NAm"

    @property
    def language_name(self) -> str:
        return LANGUAGES.get(self.language, self.language)

    def on_air(self, when: datetime) -> bool:
        m = when.hour * 60 + when.minute
        if self.start <= self.end:
            in_time = self.start <= m < self.end
        else:
            in_time = m >= self.start or m < self.end
        # A broadcast that started before midnight belongs to the previous day
        day = (when - timedelta(days=1)) if (self.start > self.end and m < self.end) else when
        return in_time and _day_ok(self.days, day.weekday())


def _day_ok(days: str, weekday: int) -> bool:
    """EiBi day field: blank = daily; "Mo-Fr", "Sa,Su", "Su", or digits 1=Mon…7=Sun.
    Anything else (irregular, alternate weeks) counts as on — better a
    possibly-wrong name than none."""
    days = days.strip()
    if not days:
        return True
    if days.isdigit():
        return str(weekday + 1) in days
    for part in days.split(","):
        if "-" in part:
            a, _, b = part.partition("-")
            if a in _DAYS and b in _DAYS:
                lo, hi = _DAYS[a], _DAYS[b]
                if (lo <= weekday <= hi) if lo <= hi else (weekday >= lo or weekday <= hi):
                    return True
                continue
        if part in _DAYS:
            if _DAYS[part] == weekday:
                return True
            continue
        return True
    return False


def season_code(when: datetime) -> str:
    """'a26' / 'b26' — A from the last Sunday of March, B from the last Sunday
    of October; Jan–Mar belongs to the previous year's B season."""
    def last_sunday(year: int, month: int) -> datetime:
        d = datetime(year, month, 31, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    y = when.year
    if when < last_sunday(y, 3):
        return f"b{(y - 1) % 100:02d}"
    if when < last_sunday(y, 10):
        return f"a{y % 100:02d}"
    return f"b{y % 100:02d}"


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[2:4])


def parse(path: Path) -> list[Entry]:
    out = []
    with open(path, encoding="latin-1", newline="") as f:
        rows = csv.reader(f, delimiter=";")
        next(rows, None)                                  # header
        for r in rows:
            try:
                start, end = r[1].split("-")
                out.append(Entry(float(r[0]), _minutes(start), _minutes(end), r[2],
                                 r[3], r[4].strip(), r[5].strip(), r[6].strip()))
            except (IndexError, ValueError):
                continue
    return out


class StationDB:
    def __init__(self, cache_dir: Path = CACHE_DIR, download: bool = True):
        self._dir = Path(cache_dir)
        self._download = download
        self._entries: list[Entry] = []
        self._loaded_from: Path | None = None
        self._lock = threading.Lock()
        self.refresh()

    def refresh(self) -> None:
        """Download this season's file if missing or a week old, then (re)load."""
        now = datetime.now(timezone.utc)
        path = self._dir / f"sked-{season_code(now)}.csv"
        stale = not path.exists() or time.time() - path.stat().st_mtime > REFRESH_S
        if self._download and stale:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                with urllib.request.urlopen(URL.format(season=season_code(now)), timeout=30) as r:
                    tmp.write_bytes(r.read())
                tmp.rename(path)
                log.info("Downloaded EiBi schedule %s", path.name)
            except OSError as e:
                log.warning("Could not download EiBi schedule: %s", e)
        if not path.exists():                             # fall back to the newest we have
            cached = sorted(self._dir.glob("sked-*.csv"), key=lambda p: p.stat().st_mtime)
            if not cached:
                return
            path = cached[-1]
        if path == self._loaded_from and not stale:
            return
        entries = parse(path)
        with self._lock:
            self._entries, self._loaded_from = entries, path
        log.info("EiBi schedule %s: %d entries", path.name, len(entries))

    def lookup(self, khz: float, when: datetime | None = None) -> list[Entry]:
        """Broadcasts on (or within 2 kHz of) khz at `when` (default now, UTC).
        Ones aimed at the Americas first — those are what we can hear."""
        when = when or datetime.now(timezone.utc)
        with self._lock:
            hits = [e for e in self._entries
                    if abs(e.khz - khz) <= FREQ_TOLERANCE_KHZ and e.on_air(when)]
        return sorted(hits, key=lambda e: (abs(e.khz - khz), not _americas(e.target)))

    def identify(self, khz: float, when: datetime | None = None) -> tuple[str, str] | None:
        """(station, language) — station is "A / B" if two share the slot."""
        hits = self.lookup(khz, when)
        if not hits:
            return None
        first = hits[0]
        others = [e.station for e in hits[1:] if e.station != first.station]
        station = f"{first.station} / {others[0]}" if others else first.station
        return station, first.language_name

    def label(self, khz: float, when: datetime | None = None) -> str | None:
        """'Radio Habana Cuba (Spanish)'."""
        ident = self.identify(khz, when)
        if not ident:
            return None
        station, language = ident
        return f"{station} ({language})" if language else station

    def on_air(self, lo_khz: float, hi_khz: float, when: datetime | None = None) -> list[Entry]:
        """Everything scheduled between lo and hi kHz right now — for tuning by
        station name ("hey radio, play Radio Habana Cuba")."""
        when = when or datetime.now(timezone.utc)
        with self._lock:
            return [e for e in self._entries if lo_khz <= e.khz <= hi_khz and e.on_air(when)]


def _americas(target: str) -> bool:
    return target in ("NAm", "Am", "CAm", "USA", "Car", "WNA", "ENA", "CNA", "ALS")
